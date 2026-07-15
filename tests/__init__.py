"""
Test package init — makes `src/` importable without requiring the caller
to pre-set PYTHONPATH. This runs before any test module is collected by
`unittest discover`, so `import resilience_radar` works whether the
suite is invoked via `python -m unittest discover -s tests` from the
repo root, or via `make test` (which also sets PYTHONPATH=src, so this
is a no-op duplicate insertion in that case — harmless either way).
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
