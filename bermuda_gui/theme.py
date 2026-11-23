"""Design system: color tokens + QSS for the whole application.

Single source of truth so paint code (chart) and stylesheets agree.
"""

# ---- color tokens (hex) ------------------------------------------------
BG          = '#0b0e14'   # window background
PANEL       = '#10141d'   # card background
PANEL_2     = '#151a26'   # elevated card
PANEL_3     = '#1a2030'   # buttons / inputs
LINE        = '#222a3d'   # borders
LINE_SOFT   = '#1b2233'
TEXT        = '#e8ecf6'
MUTED       = '#8b94ad'
MUTED_2     = '#5d667f'
GOLD        = '#e5b95c'   # accent
GOLD_DEEP   = '#d9a844'
UP          = '#22ab94'
DOWN        = '#f23645'
CLOUD_UP    = (34, 171, 148)
CLOUD_DOWN  = (242, 54, 69)
WINDOW_C    = (255, 159, 28)
ZONE_EDGE   = '#ff5a5a'
ZONE_TIMED  = '#ff9f1c'
SUPPORT     = '#60a5fa'
RESISTANCE  = '#fb7185'
GRID        = (148, 163, 184, 22)
GRID_TEXT   = '#69738f'

QSS = f"""
QMainWindow, QWidget {{
    background: {BG}; color: {TEXT};
    font-family: 'Segoe UI', Tahoma, 'Noto Naskh Arabic', sans-serif; font-size: 12px;
}}
QToolTip {{
    background: #0d1119; color: {TEXT}; border: 1px solid {LINE};
    border-radius: 6px; padding: 5px 8px;
}}

/* ---------- panels (cards) ---------- */
QFrame#Card {{
    background: {PANEL}; border: 1px solid {LINE_SOFT}; border-radius: 14px;
}}
QLabel#CardTitle {{
    color: #c9cfe4; font-size: 11px; font-weight: 700; letter-spacing: .4px;
}}
QLabel#DateGold {{ color: {GOLD}; font-size: 15px; font-weight: 800; }}
QLabel#Muted {{ color: {MUTED}; }}
QLabel#MutedSmall {{ color: {MUTED_2}; font-size: 10px; }}
QLabel#Count {{
    background: rgba(229,185,92,.15); color: {GOLD}; border: 1px solid rgba(229,185,92,.4);
    border-radius: 10px; padding: 2px 10px; font-weight: 800; font-size: 11px;
}}
QLabel#Up {{ color: {UP}; font-weight: 700; }}
QLabel#Down {{ color: {DOWN}; font-weight: 700; }}

/* ---------- buttons ---------- */
QPushButton {{
    background: {PANEL_3}; border: 1px solid {LINE}; border-radius: 10px;
    padding: 8px 13px; color: {TEXT}; font-size: 13px;
}}
QPushButton:hover {{ border-color: {GOLD}; color: {GOLD}; }}
QPushButton:pressed {{ background: #20283c; }}
QPushButton:disabled {{ color: {MUTED_2}; border-color: {LINE_SOFT}; }}
QPushButton#PlayButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f3cd7d, stop:1 {GOLD_DEEP});
    color: #221a08; font-weight: 900; font-size: 15px; border: none; border-radius: 12px;
    padding: 8px 22px;
}}
QPushButton#PlayButton:hover {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffd98a, stop:1 #e0b353); }}
QPushButton#Ghost {{ background: transparent; }}
QPushButton#Tiny {{ padding: 4px 10px; font-size: 10px; border-radius: 8px; }}

/* ---------- inputs ---------- */
QComboBox {{
    background: {PANEL_2}; border: 1px solid {LINE}; border-radius: 10px;
    padding: 7px 10px; min-width: 180px; selection-background-color: {GOLD};
    selection-color: #221a08;
}}
QComboBox:hover {{ border-color: {GOLD}; }}
QComboBox QAbstractItemView {{
    background: {PANEL_2}; border: 1px solid {LINE}; border-radius: 8px;
    selection-background-color: rgba(229,185,92,.25); selection-color: {TEXT}; outline: none;
}}
QSlider::groove:horizontal {{
    height: 5px; background: {LINE}; border-radius: 2px;
}}
QSlider::sub-page:horizontal {{ background: {GOLD}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    width: 15px; height: 15px; margin: -6px 0; border-radius: 8px;
    background: {GOLD}; border: 2px solid #4d3c12;
}}
QSlider::handle:horizontal:hover {{ background: #ffd98a; }}
QCheckBox {{ spacing: 7px; color: #c9cfe4; }}
QCheckBox::indicator {{
    width: 15px; height: 15px; border-radius: 4px;
    border: 1px solid {LINE}; background: {PANEL_3};
}}
QCheckBox::indicator:checked {{
    background: {GOLD}; border-color: {GOLD};
    image: none;   /* flat gold fill */
}}

/* ---------- scroll area ---------- */
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{
    background: transparent; width: 9px; margin: 4px 2px;
}}
QScrollBar::handle:vertical {{ background: {LINE}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {MUTED_2}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}

/* ---------- progress bar ---------- */
QProgressBar {{
    background: {PANEL_3}; border: none; border-radius: 4px; height: 6px; max-height: 6px;
    text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background: {GOLD}; border-radius: 4px; }}

/* ---------- status bar ---------- */
QStatusBar {{ background: {PANEL}; color: {MUTED}; font-size: 10px; border-top: 1px solid {LINE_SOFT}; }}
"""


def build_qss() -> str:
    return QSS
