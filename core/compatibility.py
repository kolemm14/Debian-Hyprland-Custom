#!/usr/bin/env python3
"""Legacy compatibility entry point; implementation lives in core.system."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).resolve().parent / "system" / "compatibility.py"), run_name="__main__")
