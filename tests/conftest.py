# conftest.py — make `src/` importable the same way Person 1's scripts do
# (see src/etl/write_curated.py: `sys.path.insert(0, str(ROOT / "src"))`), so test
# files can `import serving.router`, `import streaming.events`, etc. without
# reinserting the path in every module and without needing a package install.
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
