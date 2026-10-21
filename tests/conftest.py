"""Make the Kit-independent `core` package importable without Kit.

Importing `visiontwin.factory` would run its __init__ (which imports omni.*),
so we put the package directory itself on sys.path and import `core` directly.
"""

import sys
from pathlib import Path

FACTORY_DIR = (Path(__file__).resolve().parents[1]
               / "source" / "extensions" / "visiontwin.factory" / "visiontwin" / "factory")
sys.path.insert(0, str(FACTORY_DIR))
