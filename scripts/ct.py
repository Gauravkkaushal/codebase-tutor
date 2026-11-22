#!/usr/bin/env python3
"""Codebase Tutor CLI launcher. Usage: python ct.py <command> [args]  (see `python ct.py -h`)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from codebase_tutor.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
