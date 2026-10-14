import secrets

from fastapi import Header, HTTPException

from ...bootstrap import context


def auth(
    x_api_token: str | None = Header(default=None),
    x_workspace_id: str | None = Header(default=None),
) -> None:
    expected = context.config.api_token
    if expected and not secrets.compare_digest(x_api_token or "", expected):
        raise HTTPException(401, "invalid API token")
    from ...modules.projects import ProjectService
    context.current_workspace_id.set(ProjectService.normalize_workspace_id(x_workspace_id))
