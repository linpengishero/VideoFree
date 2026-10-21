# Copyright (c) 2026 VideoFree Studio individual project author and contributors.
# Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

import secrets
import hashlib
import hmac
import time
from collections.abc import AsyncIterator

from fastapi import Header, HTTPException, Request, Response

from ...bootstrap import context
from ...modules.settings import SettingsService


SESSION_COOKIE = "videofree_session"
SESSION_AGE = 7 * 86400


def session_signature(token: str, issued: str) -> str:
    return hmac.new(token.encode(), ("browser-session:" + issued).encode(), hashlib.sha256).hexdigest()


def set_session(response: Response, request: Request, token: str) -> None:
    if not token:
        response.delete_cookie(SESSION_COOKIE, path="/")
        return
    issued = str(int(time.time()))
    response.set_cookie(SESSION_COOKIE, issued + "." + session_signature(token, issued),
                        httponly=True, secure=request.url.scheme == "https", samesite="strict",
                        max_age=SESSION_AGE, path="/")


async def auth(
    request: Request,
    x_api_token: str | None = Header(default=None),
) -> AsyncIterator[None]:
    expected = SettingsService.access_token(context)
    if expected:
        header_valid = x_api_token is not None and secrets.compare_digest(x_api_token.encode(), expected.encode())
        if not header_valid:
            issued, _, signature = request.cookies.get(SESSION_COOKIE, "").partition(".")
            valid = (x_api_token is None and len(issued) <= 10 and issued.isascii() and issued.isdigit()
                     and 0 <= time.time() - int(issued) < SESSION_AGE
                     and secrets.compare_digest(signature.encode(), session_signature(expected, issued).encode()))
            if not valid:
                raise HTTPException(401, "invalid API token")
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                origin = request.headers.get("origin")
                if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
                    raise HTTPException(403, "cross-origin session request denied")
    yield
