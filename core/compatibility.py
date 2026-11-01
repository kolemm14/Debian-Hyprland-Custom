#!/usr/bin/env python3
"""Legacy compatibility API and CLI; implementation lives in core.system."""
from pathlib import Path
import importlib.util

_path = Path(__file__).resolve().parent / "system" / "compatibility.py"
_spec = importlib.util.spec_from_file_location("_deblestia_system_compatibility", _path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
globals().update({key: value for key, value in vars(_module).items() if not key.startswith("__")})

if __name__ == "__main__":
    _module.main()
