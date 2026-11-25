"""Single source of truth for repository paths (GUI runs from a copied folder)."""
import os, sys

GUI_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(GUI_DIR)
for sub in ('', 'bermuda_detector', 'simulator'):
    p = os.path.join(ROOT, sub) if sub else ROOT
    if p not in sys.path:
        sys.path.insert(0, p)

ICON_PNG = os.path.join(GUI_DIR, 'assets', 'icon.png')
