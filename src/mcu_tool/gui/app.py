"""GUI entry point."""

from __future__ import annotations

import sys


def main() -> None:
    from PySide6.QtWidgets import QApplication

    from mcu_tool.gui.main_window import MainWindow
    from mcu_tool.gui.theme import apply_theme

    app = QApplication(sys.argv)
    app.setApplicationName("MCU Workspace Tool")
    app.setOrganizationName("mcu-workspace-tool")
    apply_theme(app, dark=True)
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
