# Copyright (c) 2026 VideoFree individual project author and contributors.
# Part of VideoFree: https://github.com/linpengishero/VideoFree
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

class JobCancelled(Exception):
    """Raised when a generation job is cancelled cooperatively."""


class AgentCollaborationCancelled(Exception):
    """Raised when an active director collaboration is cancelled."""


class GatewayError(Exception):
    """Protocol-neutral application error mapped by the outer interface."""

    def __init__(self, status_code: int, detail: str, *, headers: dict[str, str] | None = None) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.headers = headers or {}
