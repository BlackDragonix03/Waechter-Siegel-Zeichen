"""Programmstart."""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
import math

from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QPalette
from PySide6.QtWidgets import QApplication

from . import APP_NAME, __version__
from .gui import theme
from .gui.main_window import MainWindow


def make_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.BG2))
        p.drawRoundedRect(0, 0, size, size, size * 0.22, size * 0.22)
        c = size / 2
        r = size * 0.11
        pen = QPen(QColor(theme.ACCENT), max(1.0, size * 0.05))
        p.setPen(pen)
        for ang in (90, 210, 330):
            x = c + math.cos(math.radians(ang)) * size * 0.3
            y = c - math.sin(math.radians(ang)) * size * 0.3
            p.drawLine(int(c), int(c), int(x), int(y))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.ACCENT2))
        for ang in (90, 210, 330):
            x = c + math.cos(math.radians(ang)) * size * 0.3
            y = c - math.sin(math.radians(ang)) * size * 0.3
            p.drawEllipse(int(x - r), int(y - r), int(2 * r), int(2 * r))
        p.setBrush(QColor(theme.ACCENT))
        p.drawEllipse(int(c - r * 1.3), int(c - r * 1.3), int(2.6 * r), int(2.6 * r))
        p.end()
        icon.addPixmap(pm)
    return icon


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("NetGuard")
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(theme.BG))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(theme.TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(theme.BG2))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(theme.BG3))
    pal.setColor(QPalette.ColorRole.Text, QColor(theme.TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(theme.BG3))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(theme.TEXT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor("#1f3b4d"))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(theme.TEXT))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(theme.BG3))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(theme.TEXT))
    pal.setColor(QPalette.ColorRole.Link, QColor(theme.ACCENT2))
    app.setPalette(pal)
    app.setStyleSheet(theme.QSS)
    app.setWindowIcon(make_icon())
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
