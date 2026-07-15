"""
_bootstrap.py — sys.path shim so the test suite runs standalone.

`python -m unittest discover -s tests` treats `tests/` as its own
top-level dir and imports `test_*.py` as plain top-level modules (not
as `tests.test_*`), so `tests/__init__.py` never executes and can't be
used to set up `sys.path`. Every test module instead starts with
`import _bootstrap` (a plain import — `tests/` is already on `sys.path`
because discover put it there), which inserts `src/` so
`import resilience_radar` works with no environment setup required.
This keeps `python3 -m unittest discover -s tests -v` runnable with
zero preconditions, while the Makefile's `PYTHONPATH=src` continues to
serve the `demo`/`dashboard` CLI targets consistently.
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
