# Copyright (c) 2026 VideoFree individual project author and contributors.
# Part of VideoFree: https://github.com/linpengishero/VideoFree
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

"""Compatibility alias for integrations using the pre-1.1 module path."""

import sys

from .interfaces.http import api_v1

sys.modules[__name__] = api_v1
