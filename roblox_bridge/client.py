"""Agent-side CLI. JSON payloads can come from files without shell quoting."""
import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--token-file", default=".bridge/token")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("status")
    send = sub.add_parser("send")
    send.add_argument("file", help="JSON command file")
    get = sub.add_parser("get")
    get.add_argument("id")
    args = parser.parse_args()
    path = "/v1/status"
    body = None
    if args.action == "send":
        path = "/v1/commands"
        body = json.dumps(json.loads(Path(args.file).read_text())).encode()
    elif args.action == "get":
        path = "/v1/commands/" + args.id
    request = Request(args.url.rstrip("/") + path, data=body, headers={
        "Authorization": "Bearer " + Path(args.token_file).read_text().strip(),
        "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=15) as response:
            print(json.dumps(json.load(response), indent=2))
    except HTTPError as error:
        parser.exit(1, error.read().decode() + "\n")


if __name__ == "__main__":
    main()
