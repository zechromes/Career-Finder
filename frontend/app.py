"""Compatibility entry point. New code should import backend.app."""

import sys
from backend import app as _implementation

# Keep the actual module identity for old imports and monkeypatching.
sys.modules[__name__] = _implementation
