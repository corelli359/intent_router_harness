from __future__ import annotations

import json
import sys
from urllib.parse import urlsplit


def handle(payload: dict) -> dict:
    request = payload.get("request") or {}
    url = str(request.get("url") or "").strip()
    allowed_urls = set(payload.get("allowed_urls") or [])
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("api request url must be an absolute http(s) URL")
    if "/../" in parts.path or parts.path.endswith("/.."):
        raise ValueError("api request url is not a safe URL path")
    if url not in allowed_urls:
        raise ValueError(f"api request url is not allowed: {url}")
    return {"allowed": True}


if __name__ == "__main__":
    print(json.dumps(handle(json.load(sys.stdin)), ensure_ascii=False))
