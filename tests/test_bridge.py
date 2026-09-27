import json
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from roblox_bridge.server import Broker, make_server


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.b = Broker()
        self.b.request("POST", "/v1/poll", {"session": "test"})

    def send(self):
        status, cmd = self.b.request("POST", "/v1/commands", {"op": "inspect", "path": ["Workspace"]})
        self.assertEqual(status, 201)
        return cmd

    def test_approval_lifecycle_and_idempotency(self):
        cmd = self.send()
        self.send()
        self.assertEqual(self.b.request("POST", "/v1/poll", {"session": "test"})[1]["command"]["id"], cmd["id"])
        self.assertIsNone(self.b.request("POST", "/v1/poll", {"session": "test"})[1]["command"])
        path = "/v1/commands/" + cmd["id"]
        self.assertEqual(self.b.request("POST", path, {"session": "other", "status": "succeeded"})[0], 409)
        result = {"session": "test", "status": "rejected", "result": {"message": "no"}}
        self.assertEqual(self.b.request("POST", path, result)[0], 200)
        self.assertEqual(self.b.request("POST", path, result)[0], 200)
        self.assertIsNotNone(self.b.request("POST", "/v1/poll", {"session": "test"})[1]["command"])

    def test_session_isolation(self):
        cmd = self.send()
        self.assertEqual(self.b.request("POST", "/v1/poll", {"session": "other"})[0], 409)
        self.b.last_seen = 0
        self.assertIsNone(self.b.request("POST", "/v1/poll", {"session": "other"})[1]["command"])
        self.assertEqual(cmd["status"], "unknown")

    def test_validation_and_offline(self):
        self.assertEqual(self.b.request("POST", "/v1/commands", {"op": "exec", "path": ["Workspace"]})[0], 400)
        self.assertEqual(self.b.request("POST", "/v1/commands", {"op": "inspect", "path": "Workspace"})[0], 400)
        self.assertEqual(Broker().request("POST", "/v1/commands", {})[0], 409)


class HTTPTests(unittest.TestCase):
    def test_auth_json_and_public_health(self):
        server = make_server("127.0.0.1", 0, "a" * 40)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = "http://127.0.0.1:" + str(server.server_port)
        try:
            with urlopen(base + "/") as response:
                self.assertEqual(response.status, 200)
            with self.assertRaises(HTTPError) as caught:
                urlopen(base + "/v1/status")
            self.assertEqual(caught.exception.code, 401)
            headers = {"Authorization": "Bearer " + "a" * 40}
            with urlopen(Request(base + "/v1/status", headers=headers)) as response:
                self.assertIsNone(json.load(response)["studio"])
            with self.assertRaises(HTTPError) as caught:
                urlopen(Request(base + "/v1/poll", data=b'[]', headers=headers))
            self.assertEqual(caught.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
