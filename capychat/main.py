"""CapyChat client entrypoint."""

import sys
from PySide6.QtWidgets import QApplication
from views.login_ui import LoginWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("CapyChat")
    login_window = LoginWindow()
    login_window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
