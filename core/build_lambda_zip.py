"""Builds dist/7even5ive-lambda.zip: the demo's code plus its Linux dependencies, for Lambda.

Used by the serverless demo (deploy/aws/7even5ive-serverless.yaml, handler
seventy5.lambda_demo.handler). The dependencies are the Linux x86_64 wheels for Python 3.12
whatever machine runs this, so the zip comes out the same from a laptop, CI or a container.

    python build_lambda_zip.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = HERE / ".build-lambda"
DIST = HERE / "dist"
ZIP = DIST / "7even5ive-lambda.zip"


def main() -> None:
    shutil.rmtree(BUILD, ignore_errors=True)
    skip = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(HERE / "seventy5", BUILD / "seventy5", ignore=skip)
    shutil.copytree(HERE.parent / "portmax" / "src" / "portmax", BUILD / "portmax", ignore=skip)
    subprocess.run(
        [
            sys.executable, "-m", "pip", "install", "--quiet", "--target", str(BUILD),
            # Lambda's python3.12 runs on Amazon Linux 2023 (glibc 2.34): either tag fits.
            "--platform", "manylinux2014_x86_64", "--platform", "manylinux_2_28_x86_64",
            "--implementation", "cp", "--python-version", "3.12", "--only-binary=:all:",
            "-r", str(HERE / "requirements-lambda.txt"),
        ],
        check=True,
    )  # fmt: skip
    for cache in BUILD.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)

    DIST.mkdir(exist_ok=True)
    ZIP.unlink(missing_ok=True)
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(BUILD.rglob("*")):
            if path.is_file():
                z.write(path, path.relative_to(BUILD).as_posix())
    unpacked = sum(p.stat().st_size for p in BUILD.rglob("*") if p.is_file())
    print(f"built {ZIP} ({ZIP.stat().st_size / 1e6:.1f} MB zipped, {unpacked / 1e6:.0f} MB unpacked)")


if __name__ == "__main__":
    main()
