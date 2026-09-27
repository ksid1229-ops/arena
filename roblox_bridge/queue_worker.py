"""Poll the public GitHub command queue and submit requests to the local bridge.

Run on the Windows machine that is running Roblox Studio. This is deliberately
one-way: GitHub -> localhost. It never exposes the bridge or uploads secrets.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time
import urllib.error
import urllib.request


def get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "arena-roblox-queue/1"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.read()


def post(url: str, token: str, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "arena-roblox-queue/1",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status >= 300:
            raise RuntimeError(f"bridge returned HTTP {response.status}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--bridge", default="http://127.0.0.1:8765")
    parser.add_argument("--interval", type=int, default=5)
    args = parser.parse_args()

    root = pathlib.Path.cwd()
    token_path = root / ".bridge" / "token"
    if not token_path.exists():
        raise SystemExit(f"Token not found: {token_path}. Run this in the bridge folder.")
    token = token_path.read_text(encoding="utf-8").strip()
    if not token:
        raise SystemExit("The bridge token is empty.")

    base = f"https://raw.githubusercontent.com/{args.repo}/{args.branch}"
    index_url = f"{base}/queue/pending/index.json"
    state_path = root / ".bridge" / "queue-state.json"
    try:
        delivered = set(json.loads(state_path.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError):
        delivered = set()

    print(f"Queue worker watching {index_url}")
    print(f"Submitting approved-by-Studio requests to {args.bridge}")
    while True:
        try:
            index = json.loads(get(index_url).decode("utf-8"))
            for item in index.get("requests", []):
                request_id = item.get("id")
                path = item.get("path")
                if not request_id or not path or request_id in delivered:
                    continue
                payload = json.loads(get(f"{base}/{path}").decode("utf-8"))
                post(f"{args.bridge}/v1/requests", token, payload)
                delivered.add(request_id)
                state_path.write_text(json.dumps(sorted(delivered), indent=2), encoding="utf-8")
                print(f"Submitted {request_id}")
        except urllib.error.HTTPError as exc:
            print(f"Queue HTTP error: {exc.code}; retrying")
        except (urllib.error.URLError, TimeoutError, ValueError, OSError, RuntimeError) as exc:
            print(f"Queue unavailable: {exc}; retrying")
        time.sleep(max(1, args.interval))


if __name__ == "__main__":
    main()
