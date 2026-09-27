"""Dependency-free, ephemeral command broker. Run with python -m roblox_bridge.server."""
import argparse
import hmac
import json
import os
from pathlib import Path
import secrets
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY = 1_000_000
OPERATIONS = {"inspect", "create", "set_properties", "set_script", "delete"}


class Broker:
    def __init__(self):
        self.lock = threading.Lock()
        self.commands = {}
        self.last_seen = None
        self.session = None

    def request(self, method, path, data):
        with self.lock:
            if method == "GET" and path == "/v1/status":
                return 200, {"studio": self.session, "last_seen": self.last_seen,
                             "commands": len(self.commands)}
            if method == "POST" and path == "/v1/poll":
                session = data.get("session")
                if not isinstance(session, str) or not session or len(session) > 300:
                    return 400, {"error": "session required"}
                now = time.time()
                if self.session and self.session != session and now - (self.last_seen or 0) < 30:
                    return 409, {"error": "Another Studio session is connected"}
                if self.session != session:
                    # Never transfer a delivered command to another place/session.
                    for command in self.commands.values():
                        if command["status"] in {"queued", "delivered"}:
                            command.update(status="unknown", result={"error": "Studio disconnected; inspect before retrying"})
                self.session, self.last_seen = session, now
                if any(c["status"] == "delivered" for c in self.commands.values()):
                    return 200, {"command": None}
                for command in self.commands.values():
                    if command["status"] == "queued":
                        command.update(status="delivered", session=session)
                        return 200, {"command": command}
                return 200, {"command": None}
            if method == "POST" and path == "/v1/commands":
                if not self.session or time.time() - (self.last_seen or 0) >= 30:
                    return 409, {"error": "Connect Studio before submitting commands"}
                if data.get("op") not in OPERATIONS:
                    return 400, {"error": "Unsupported operation"}
                target = data.get("path")
                if not isinstance(target, list) or not target or any(not isinstance(x, str) or not x for x in target):
                    return 400, {"error": "path must be a nonempty array of instance names"}
                if len(self.commands) >= 1000:
                    return 429, {"error": "Session command limit reached; restart broker"}
                cid = uuid.uuid4().hex
                command = {"id": cid, "op": data["op"], "path": target,
                           "args": data.get("args", {}), "status": "queued", "created": time.time()}
                if not isinstance(command["args"], dict):
                    return 400, {"error": "args must be an object"}
                self.commands[cid] = command
                return 201, command
            if path.startswith("/v1/commands/"):
                cid = path.removeprefix("/v1/commands/")
                command = self.commands.get(cid)
                if not command:
                    return 404, {"error": "Unknown command"}
                if method == "GET":
                    return 200, command
                if method == "POST":
                    if command.get("session") == data.get("session") and command["status"] == data.get("status") and command.get("result") == data.get("result"):
                        return 200, command
                    if command["status"] != "delivered" or command.get("session") != data.get("session"):
                        return 409, {"error": "Command not owned by this session or already completed"}
                    if data.get("status") not in {"succeeded", "failed", "rejected"}:
                        return 400, {"error": "Invalid result status"}
                    command.update(status=data["status"], result=data.get("result"))
                    return 200, command
            return 404, {"error": "Not found"}


def make_server(host, port, token, broker=None):
    broker = broker or Broker()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Don't log tokens, source code, or payloads.

        def do_GET(self):
            self.handle_request()

        def do_POST(self):
            self.handle_request()

        def handle_request(self):
            if self.path == "/" and self.command == "GET":
                return self.reply(200, {"service": "Roblox Studio bridge", "authenticated_api": "/v1/status"})
            auth = self.headers.get("Authorization", "")
            if not hmac.compare_digest(auth.encode(), ("Bearer " + token).encode()):
                return self.reply(401, {"error": "Unauthorized"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size < 0 or size > MAX_BODY:
                    return self.reply(413, {"error": "Body too large"})
                self.connection.settimeout(10)
                data = json.loads(self.rfile.read(size)) if size else {}
                if not isinstance(data, dict):
                    raise ValueError("Expected an object")
            except (ValueError, OSError):
                return self.reply(400, {"error": "Invalid JSON request"})
            status, result = broker.request(self.command, self.path, data)
            self.reply(status, result)

        def reply(self, status, data):
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return ThreadingHTTPServer((host, port), Handler)


def load_token(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_urlsafe(32))
    token = path.read_text().strip()
    if len(token) < 32:
        raise ValueError("Token must contain at least 32 characters")
    return token


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--token-file", default=".bridge/token")
    args = parser.parse_args()
    server = make_server(args.host, args.port, load_token(args.token_file))
    print(f"Bridge listening on {args.host}:{args.port}; token in {args.token_file} (keep private)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
