"""Frozen-bundle entry point.

PyInstaller freezes a script, not a console-script entry point, so this is the
one-line stand-in for the `planeopt` command declared in pyproject.toml. All of
the real work — including multiprocessing.freeze_support() — lives in cli.main.
"""

from planeopt.cli import main

if __name__ == "__main__":
    main()
