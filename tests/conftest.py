import sys
from pathlib import Path


RUN_DIR = Path(__file__).resolve().parents[1] / "run"
if str(RUN_DIR) not in sys.path:
    sys.path.insert(0, str(RUN_DIR))
