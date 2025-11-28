#!/usr/bin/env python
"""Clean coverage files and run pytest with coverage."""

import os
import sys
import glob
import subprocess


def clean_coverage_files():
    """Remove existing coverage files to prevent permission errors."""
    coverage_files = [".coverage"] + glob.glob(".coverage.*")
    for file in coverage_files:
        try:
            if os.path.exists(file):
                os.remove(file)
        except (OSError, PermissionError):
            # Ignore if we can't remove (file might be in use)
            pass


def main():
    """Clean coverage files and run pytest."""
    clean_coverage_files()

    # Run pytest with coverage
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "--cov=src",
        "--cov-report=term-missing",
        "--cov-fail-under=90",
    ]

    result = subprocess.run(cmd, cwd=os.getcwd())
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
