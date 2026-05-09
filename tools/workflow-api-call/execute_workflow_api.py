from __future__ import annotations

import json
import sys
from urllib import error, request


def handle(payload: dict) -> dict:
    method = str(payload.get("method") or "").upper()
    if method != "POST":
        raise ValueError(f"unsupported workflow method: {method}")
    url = str(payload.get("url") or "")
    body = payload.get("body")
    timeout_seconds = float(payload.get("timeout_seconds") or 60)
    raw_body = json.dumps(body or {}, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=raw_body,
        method=method,
        headers={
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
            "Content-Type": "application/json",
        },
    )
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            return {
                "status_code": response.status,
                "response_type": "sse",
                "text": response.read().decode("utf-8"),
            }
    except error.HTTPError as exc:
        raw_error = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from workflow: {raw_error[:300]}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"workflow request failed: {exc.reason}") from exc


if __name__ == "__main__":
    print(json.dumps(handle(json.load(sys.stdin)), ensure_ascii=False))
