"""Compatibility alias for integrations using the pre-1.1 module path."""

import sys

from .interfaces.http import api_v1

sys.modules[__name__] = api_v1
