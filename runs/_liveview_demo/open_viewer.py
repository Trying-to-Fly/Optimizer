"""Open the live viewer on a frame directory, interactively.

    uv run python runs/_liveview_demo/open_viewer.py [frame-dir]

The app itself only offers the viewer for a RUNNING job or for a finished run
that has a `frames/` directory — there is no menu entry for a loose folder of
frames, which is what this demo directory is. This is the two-line stand-in.

Drag to orbit, wheel to zoom, shift- or middle-drag to pan, double-click to
reset. The slider scrubs; dragging it turns off "Follow latest".
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from planeopt.gui.liveview import LiveViewWindow
from planeopt.gui.window import STYLE

frames = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "frames")

app = QApplication(sys.argv)
app.setStyleSheet(STYLE)
window = LiveViewWindow()
# live=False: these frames are finished, so it scrubs them instead of polling
# the directory for more.
window.watch(frames, live=False)
window.resize(1180, 800)
window.show()
sys.exit(app.exec())
