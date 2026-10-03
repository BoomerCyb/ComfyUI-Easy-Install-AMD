import runpy
from pathlib import Path
import sys
sys.argv=[sys.argv[0], "update"]
runpy.run_path(str(Path(__file__).resolve().parent.parent / "amd/maintenance.py"), run_name="__main__")
