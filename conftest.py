"""Allow running `pytest` without installing the package.

Adds ``src/`` to sys.path so tests can import ``gca`` directly.
"""
import sys
from pathlib import Path

_SRC = Path(__file__).parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
