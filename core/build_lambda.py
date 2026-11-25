"""Gathers what the Lambdas run into .build/: seventy5, PortMax's package, the deps list.

Why a copy: SAM packages one folder, and PortMax lives beside core/ in this repository.
Not: PortMax's forge or mock portal at runtime -- they are copied but never imported.
"""

import shutil
from pathlib import Path

here = Path(__file__).resolve().parent
out = here / ".build"
shutil.rmtree(out, ignore_errors=True)
skip = shutil.ignore_patterns("__pycache__", "*.pyc", "web")
shutil.copytree(here / "seventy5", out / "seventy5", ignore=shutil.ignore_patterns("__pycache__"))
shutil.copytree(here.parent / "portmax" / "src" / "portmax", out / "portmax", ignore=skip)
shutil.copy(here / "requirements-lambda.txt", out / "requirements.txt")
print(f"built {out}")
