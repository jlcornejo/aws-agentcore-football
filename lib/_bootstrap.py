"""Path resolver — makes `lib/` importable from any agent folder."""

import os
import sys

# Add lib/ to sys.path so agents can `from state import ...` etc.
_lib_dir = os.path.dirname(os.path.abspath(__file__))
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)
