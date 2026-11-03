"""Keep shared test helpers importable with unittest's package-style loading.

Direct scripts and discovery with ``-s lobby/tests`` put this directory on
``sys.path``. Loading ``lobby/tests/test_*.py`` from the repository root does
not, so provide the same path for the suite's existing sibling imports.
"""
import os
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
