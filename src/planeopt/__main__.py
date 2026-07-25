"""`python -m planeopt` — same entry point as the console script.

The GUI launches runs as `python -m planeopt ...` child processes, which needs
this to exist in a source install (no reliance on a `planeopt` script being on
PATH).
"""

from .cli import main

main()
