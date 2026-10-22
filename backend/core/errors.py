# Copyright (c) 2026 VideoFree Studio individual project author and contributors.
# Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
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


class SystemServiceError(GatewayError):
    """Credential-free error returned by the generic system-service boundary."""

    def __init__(self, status_code: int, service_id: str, provider_id: str, operation: str,
                 code: str, *, diagnostic: str = "") -> None:
        target = ".".join(part for part in (service_id, operation) if part) or "system-service"
        detail = f"System service {target} failed ({code})"
        if diagnostic:
            detail += f": {diagnostic}"
        super().__init__(status_code, detail)
        self.code = code
        self.service_id = service_id
        self.provider_id = provider_id
        self.operation = operation
