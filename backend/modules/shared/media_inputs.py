"""Shared parsing for trusted upload references and inline media."""

import base64
from pathlib import Path


def upload_path(uploads_path: Path, value: str) -> Path | None:
    if not isinstance(value, str) or not value.startswith("upload:"):
        return None
    upload_id = value.removeprefix("upload:")
    if not upload_id or any(char not in "0123456789abcdef" for char in upload_id):
        return None
    matches = list(uploads_path.glob(f"{upload_id}.*"))
    return matches[0] if len(matches) == 1 and matches[0].is_file() else None


def data_url_bytes(value: str) -> tuple[bytes, str]:
    header, encoded = value.split(",", 1)
    media_type = header[5:].split(";", 1)[0] if header.startswith("data:") else "application/octet-stream"
    try:
        return base64.b64decode(encoded, validate=True), media_type
    except ValueError as exc:
        raise ValueError("Base64 素材格式无效") from exc
