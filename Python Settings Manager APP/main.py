#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ATGMaster Controller — Application Entry Point (main.py)
Initializes Qt application, establishes modular dependencies,
and launches the main controller window.
All comments, docstrings, and symbols are strictly in English.
"""

import sys
from PyQt6.QtWidgets import QApplication

from transport import HardwareTransport
from librarian import PatchLibrarian
from ui import AT200MainWindow


def main() -> None:
    """Bootstraps the master controller application."""
    app = QApplication(sys.argv)

    transport = HardwareTransport()
    librarian = PatchLibrarian()
    window = AT200MainWindow(transport=transport, librarian=librarian)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()