#!/usr/bin/env python3
"""Legacy hardware-report entry point; implementation lives in core.system."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).resolve().parent / "system" / "hardware.py"), run_name="__main__")
