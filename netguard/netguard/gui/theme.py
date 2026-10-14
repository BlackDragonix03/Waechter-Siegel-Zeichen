"""Dunkles, ruhiges Farbschema."""
from __future__ import annotations

BG = "#0f141a"
BG2 = "#161d26"
BG3 = "#1e2833"
BORDER = "#2b3845"
TEXT = "#e6edf3"
TEXT_DIM = "#8b9bab"
ACCENT = "#2ee6a6"
ACCENT2 = "#39c6ff"
WARN = "#ffb347"
ERROR = "#ff5c5c"
OK = "#2ee6a6"

QSS = f"""
* {{ font-family: "Segoe UI", "Inter", "Noto Sans", sans-serif; font-size: 10.5pt; }}
QMainWindow, QDialog, QWidget {{ background: {BG}; color: {TEXT}; }}
QToolBar {{ background: {BG2}; border-bottom: 1px solid {BORDER}; padding: 6px; spacing: 8px; }}
QToolBar QLabel {{ color: {TEXT_DIM}; padding: 0 4px; }}
QStatusBar {{ background: {BG2}; border-top: 1px solid {BORDER}; color: {TEXT_DIM}; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 6px; background: {BG}; top: -1px; }}
QTabBar::tab {{ background: {BG2}; color: {TEXT_DIM}; padding: 8px 18px; border: 1px solid {BORDER}; border-bottom: none;
                border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }}
QTabBar::tab:selected {{ background: {BG}; color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}
QPushButton, QToolButton {{ background: {BG3}; color: {TEXT}; border: 1px solid {BORDER}; border-radius: 6px; padding: 6px 12px; }}
QPushButton:hover, QToolButton:hover {{ background: #26323f; border-color: #3b4b5c; }}
QPushButton:pressed, QToolButton:pressed {{ background: #1a232d; }}
QPushButton:disabled, QToolButton:disabled {{ color: #5a6977; background: {BG2}; }}
QPushButton#primary {{ background: {ACCENT}; color: #06231a; font-weight: 600; border: none; }}
QPushButton#primary:hover {{ background: #4ff0b8; }}
QPushButton#primary:disabled {{ background: #1f5c47; color: #0b2e23; }}
QPushButton#danger {{ background: #3a1f24; color: {ERROR}; border: 1px solid #5a2b33; }}
QLineEdit, QComboBox, QSpinBox, QTextEdit, QPlainTextEdit {{ background: {BG2}; color: {TEXT}; border: 1px solid {BORDER}; border-radius: 6px; padding: 5px 8px;
                selection-background-color: {ACCENT2}; selection-color: #04141c; }}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{ border-color: {ACCENT2}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {BG2}; color: {TEXT}; border: 1px solid {BORDER}; selection-background-color: {BG3}; }}
QCheckBox {{ color: {TEXT}; spacing: 6px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {BORDER}; border-radius: 4px; background: {BG2}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QTableView, QTreeView, QListView {{ background: {BG}; alternate-background-color: {BG2}; color: {TEXT}; border: 1px solid {BORDER}; border-radius: 6px;
                gridline-color: {BORDER}; selection-background-color: #1f3b4d; selection-color: {TEXT}; }}
QHeaderView::section {{ background: {BG2}; color: {TEXT_DIM}; border: none; border-bottom: 1px solid {BORDER}; border-right: 1px solid {BORDER}; padding: 6px 8px; font-weight: 600; }}
QTableView::item {{ padding: 4px; }}
QScrollBar:vertical {{ background: {BG}; width: 12px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #2f3d4b; border-radius: 6px; min-height: 30px; margin: 2px; }}
QScrollBar::handle:vertical:hover {{ background: #3d4e5f; }}
QScrollBar:horizontal {{ background: {BG}; height: 12px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: #2f3d4b; border-radius: 6px; min-width: 30px; margin: 2px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QProgressBar {{ background: {BG2}; border: 1px solid {BORDER}; border-radius: 6px; text-align: center; color: {TEXT}; height: 16px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 5px; }}
QGroupBox {{ border: 1px solid {BORDER}; border-radius: 8px; margin-top: 12px; padding: 10px 8px 8px 8px; color: {TEXT_DIM}; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
QSplitter::handle {{ background: {BORDER}; }}
QSplitter::handle:horizontal {{ width: 2px; }}
QSplitter::handle:vertical {{ height: 2px; }}
QDockWidget {{ color: {TEXT}; titlebar-close-icon: none; }}
QDockWidget::title {{ background: {BG2}; padding: 6px; border-bottom: 1px solid {BORDER}; }}
QToolTip {{ background: {BG3}; color: {TEXT}; border: 1px solid {BORDER}; padding: 6px; border-radius: 4px; }}
QMenu {{ background: {BG2}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {BG3}; }}
QLabel#title {{ font-size: 15pt; font-weight: 700; color: {TEXT}; }}
QLabel#dim {{ color: {TEXT_DIM}; }}
QLabel#badge {{ background: {BG3}; border: 1px solid {BORDER}; border-radius: 10px; padding: 2px 10px; color: {TEXT_DIM}; }}
QFrame#card {{ background: {BG2}; border: 1px solid {BORDER}; border-radius: 10px; }}
QMessageBox {{ background: {BG2}; }}
"""
