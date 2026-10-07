"""Main window: workspace sidebar + project tabs + log."""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QAction, QColor, QTextCharFormat
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from mcu_tool.adapters import serial_mon
from mcu_tool.events import Event, EventBus
from mcu_tool.models import ProbeType, Project
from mcu_tool.service import CoreService
from mcu_tool.workspace import WorkspaceError


class JobWorker(QThread):
    finished_ok = Signal(bool, int, str)

    def __init__(self, fn, *args, **kwargs) -> None:  # noqa: ANN001
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:
        try:
            result = self._fn(*self._args, **self._kwargs)
            self.finished_ok.emit(result.ok, result.exit_code, result.message)
        except Exception as e:  # noqa: BLE001
            self.finished_ok.emit(False, 5, str(e))


class ProjectTab(QWidget):
    def __init__(self, project: Project, service: CoreService, parent=None) -> None:
        super().__init__(parent)
        self.project = project
        self.service = service
        self._worker: JobWorker | None = None
        self._serial: serial_mon.SerialMonitor | None = None

        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self.btn_build = QPushButton("Build")
        self.btn_flash = QPushButton("Flash")
        self.btn_clean = QPushButton("Clean")
        self.env_combo = QComboBox()
        self.env_combo.setMinimumWidth(120)
        self.probe_combo = QComboBox()
        self.probe_combo.addItems(["auto", "uf2", "jlink", "stlink"])
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(140)
        self.port_combo.setEditable(True)

        toolbar.addWidget(self.btn_build)
        toolbar.addWidget(self.btn_flash)
        toolbar.addWidget(self.btn_clean)
        toolbar.addWidget(QLabel("Env"))
        toolbar.addWidget(self.env_combo)
        toolbar.addWidget(QLabel("Probe"))
        toolbar.addWidget(self.probe_combo)
        toolbar.addWidget(QLabel("Port"))
        toolbar.addWidget(self.port_combo)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        split = QSplitter(Qt.Orientation.Vertical)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Build / flash log…")
        split.addWidget(self.log)

        serial_box = QWidget()
        s_layout = QVBoxLayout(serial_box)
        s_bar = QHBoxLayout()
        self.btn_serial = QPushButton("Connect serial")
        self.btn_serial_clear = QPushButton("Clear")
        s_bar.addWidget(QLabel("Serial"))
        s_bar.addWidget(self.btn_serial)
        s_bar.addWidget(self.btn_serial_clear)
        s_bar.addStretch()
        s_layout.addLayout(s_bar)
        self.serial_view = QPlainTextEdit()
        self.serial_view.setReadOnly(True)
        s_layout.addWidget(self.serial_view)
        split.addWidget(serial_box)
        split.setSizes([400, 160])
        layout.addWidget(split)

        self.btn_build.clicked.connect(lambda: self._run_job("build"))
        self.btn_flash.clicked.connect(lambda: self._run_job("flash"))
        self.btn_clean.clicked.connect(lambda: self._run_job("clean"))
        self.btn_serial.clicked.connect(self._toggle_serial)
        self.btn_serial_clear.clicked.connect(self.serial_view.clear)

        self._reload_envs()
        self._reload_ports()
        if project.lastEnv:
            idx = self.env_combo.findText(project.lastEnv)
            if idx >= 0:
                self.env_combo.setCurrentIndex(idx)
        if project.lastPort:
            self.port_combo.setCurrentText(project.lastPort)
        if project.lastProbe:
            idx = self.probe_combo.findText(project.lastProbe)
            if idx >= 0:
                self.probe_combo.setCurrentIndex(idx)

    def _reload_envs(self) -> None:
        self.env_combo.clear()
        try:
            envs = self.service.project_envs(self.project.id)
        except WorkspaceError:
            envs = []
        if not envs:
            envs = ["default"]
        self.env_combo.addItems(envs)

    def _reload_ports(self) -> None:
        current = self.port_combo.currentText()
        self.port_combo.clear()
        ports = serial_mon.list_serial_ports()
        for p in ports:
            self.port_combo.addItem(p.device)
        if current:
            self.port_combo.setCurrentText(current)

    def append_log(self, line: str, stream: str = "stdout") -> None:
        fmt = QTextCharFormat()
        if stream == "stderr":
            fmt.setForeground(QColor("#c44"))
        elif stream == "system":
            fmt.setForeground(QColor("#888"))
        else:
            fmt.setForeground(QColor("#ddd"))
        cursor = self.log.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(line + "\n", fmt)
        self.log.setTextCursor(cursor)
        self.log.ensureCursorVisible()

    def append_serial(self, line: str) -> None:
        self.serial_view.appendPlainText(line)

    def _set_busy(self, busy: bool) -> None:
        for b in (self.btn_build, self.btn_flash, self.btn_clean):
            b.setEnabled(not busy)

    def _run_job(self, action: str) -> None:
        if self._worker and self._worker.isRunning():
            return
        env = self.env_combo.currentText() or None
        port = self.port_combo.currentText() or None
        probe = ProbeType(self.probe_combo.currentText())

        def pause() -> None:
            if self._serial:
                self._serial.pause()

        def resume() -> None:
            if self._serial:
                self._serial.resume()

        if action == "build":
            fn = lambda: self.service.build(self.project.id, env=env)  # noqa: E731
        elif action == "flash":
            fn = lambda: self.service.flash(  # noqa: E731
                self.project.id,
                env=env,
                probe=probe,
                port=port,
                pause_serial=pause,
                resume_serial=resume,
            )
        else:
            fn = lambda: self.service.clean(self.project.id, env=env)  # noqa: E731

        self._set_busy(True)
        self.append_log(f"—— {action} ——", "system")
        self._worker = JobWorker(fn)
        self._worker.finished_ok.connect(self._on_job_done)
        self._worker.start()

    @Slot(bool, int, str)
    def _on_job_done(self, ok: bool, code: int, message: str) -> None:
        self._set_busy(False)
        self.append_log(message, "stdout" if ok else "stderr")
        self._reload_ports()

    def _toggle_serial(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()
            self._serial = None
            self.btn_serial.setText("Connect serial")
            return
        port = self.port_combo.currentText().strip()
        if not port:
            QMessageBox.warning(self, "Serial", "Select or enter a serial port.")
            return
        mon = serial_mon.SerialMonitor(port, 115200, bus=self.service.bus)
        mon.on_line = self.append_serial
        try:
            mon.open()
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Serial", f"Failed to open {port}:\n{e}")
            return
        self._serial = mon
        self.btn_serial.setText("Disconnect")
        self.service.save_project_prefs(self.project, port=port)

    def close_resources(self) -> None:
        if self._serial:
            self._serial.close()
            self._serial = None


class MainWindow(QMainWindow):
    log_event = Signal(object)

    def __init__(self, service: CoreService | None = None) -> None:
        super().__init__()
        self.setWindowTitle("MCU Workspace Tool")
        self.resize(1100, 720)

        self.bus = EventBus()
        self.service = service or CoreService(self.bus)
        self.service.bus = self.bus
        self.bus.subscribe(self._on_bus_event)
        self.log_event.connect(self._handle_event)

        try:
            self.service.ensure_workspace()
        except Exception:  # noqa: BLE001
            self.service.init_workspace()

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.addWidget(QLabel("Projects"))
        self.project_list = QListWidget()
        side_layout.addWidget(self.project_list)
        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("Add…")
        self.btn_remove = QPushButton("Remove")
        self.btn_doctor = QPushButton("Doctor")
        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_remove)
        btn_row.addWidget(self.btn_doctor)
        side_layout.addLayout(btn_row)
        splitter.addWidget(side)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        splitter.addWidget(self.tabs)
        splitter.setSizes([260, 840])

        self.setStatusBar(QStatusBar())
        self._refresh_doctor_status()

        toolbar = QToolBar("Main")
        self.addToolBar(toolbar)
        act_refresh = QAction("Refresh", self)
        act_refresh.triggered.connect(self.refresh_projects)
        toolbar.addAction(act_refresh)

        self.btn_add.clicked.connect(self._add_project)
        self.btn_remove.clicked.connect(self._remove_project)
        self.btn_doctor.clicked.connect(self._show_doctor)
        self.project_list.itemDoubleClicked.connect(self._open_selected)

        self.refresh_projects()

    def _on_bus_event(self, event: Event) -> None:
        # Marshal to GUI thread
        self.log_event.emit(event)

    @Slot(object)
    def _handle_event(self, event: Event) -> None:
        if event.type != "log.line":
            return
        tab = self.tabs.currentWidget()
        if isinstance(tab, ProjectTab):
            tab.append_log(event.payload.get("line", ""), event.payload.get("stream", "stdout"))

    def refresh_projects(self) -> None:
        self.project_list.clear()
        try:
            projects = self.service.list_projects()
        except WorkspaceError:
            projects = []
        for p in projects:
            item = QListWidgetItem(f"{p.displayName}  [{p.kind.value}]")
            item.setData(Qt.ItemDataRole.UserRole, p.id)
            item.setToolTip(p.path)
            self.project_list.addItem(item)
        name = self.service.workspace.name if self.service.workspace else "Workspace"
        self.setWindowTitle(f"MCU Workspace Tool — {name}")

    def _add_project(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Add MCU project")
        if not path:
            return
        try:
            project = self.service.add_project(path, yes=True)
        except WorkspaceError as e:
            QMessageBox.warning(self, "Add project", str(e))
            return
        self.refresh_projects()
        self._open_project(project)

    def _remove_project(self) -> None:
        item = self.project_list.currentItem()
        if not item:
            return
        pid = item.data(Qt.ItemDataRole.UserRole)
        try:
            self.service.remove_project(pid)
        except WorkspaceError as e:
            QMessageBox.warning(self, "Remove", str(e))
            return
        # Close matching tab
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, ProjectTab) and w.project.id == pid:
                w.close_resources()
                self.tabs.removeTab(i)
                break
        self.refresh_projects()

    def _open_selected(self, item: QListWidgetItem) -> None:
        pid = item.data(Qt.ItemDataRole.UserRole)
        try:
            project = self.service.get_project(pid)
        except WorkspaceError as e:
            QMessageBox.warning(self, "Open", str(e))
            return
        self._open_project(project)

    def _open_project(self, project: Project) -> None:
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, ProjectTab) and w.project.id == project.id:
                self.tabs.setCurrentIndex(i)
                return
        tab = ProjectTab(project, self.service)
        self.tabs.addTab(tab, project.displayName)
        self.tabs.setCurrentWidget(tab)
        self._refresh_doctor_status()

    def _close_tab(self, index: int) -> None:
        w = self.tabs.widget(index)
        if isinstance(w, ProjectTab):
            w.close_resources()
        self.tabs.removeTab(index)

    def _show_doctor(self) -> None:
        tools = self.service.tools_doctor()
        lines = []
        for t in tools:
            loc = t.path or "—"
            hint = f"\n    {t.hint}" if t.hint and t.status == "missing" else ""
            lines.append(f"{t.name}: {t.status}  {loc}{hint}")
        QMessageBox.information(self, "Toolchain doctor", "\n".join(lines))
        self._refresh_doctor_status()

    def _refresh_doctor_status(self) -> None:
        tools = self.service.tools_doctor()
        missing = [t.name for t in tools if t.status == "missing"]
        if missing:
            self.statusBar().showMessage("Missing tools: " + ", ".join(missing[:6]))
        else:
            self.statusBar().showMessage("Toolchains OK")

    def closeEvent(self, event) -> None:  # noqa: N802, ANN001
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, ProjectTab):
                w.close_resources()
        super().closeEvent(event)
