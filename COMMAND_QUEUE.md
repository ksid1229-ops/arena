# Roblox Studio command queue

This is the transport used when an Arena chat cannot call a PC-local HTTP server directly.

## Flow

1. An Arena session writes a request JSON file under `queue/pending/` and pushes it to this repository.
2. The Windows queue worker polls the public GitHub raw URL and submits new requests to the local bridge at `http://127.0.0.1:8765`.
3. The Studio plugin displays the request. Nothing changes until you approve it in Studio.
4. The plugin executes only the allow-listed operation and reports the result in Studio.

Requests must contain no passwords, API keys, bridge tokens, or private place data. The repository is public.

## Windows setup

Leave the bridge running in one terminal. In a second terminal, from the extracted repository folder, run:

```bat
py -m roblox_bridge.queue_worker --repo ksid1229-ops/arena --branch arena/01a0e05c-arena --bridge http://127.0.0.1:8765
```

The worker polls every five seconds. It needs outbound internet access, but the bridge remains bound to localhost. Do not expose port 8765 publicly.

If the downloaded package does not contain `roblox_bridge\queue_worker.py`, download the latest branch again after this feature is pushed.

## Request format

```json
{
  "id": "unique-request-id",
  "operation": "create_script",
  "target": "ServerScriptService/Example",
  "source": "print('Hello')",
  "reason": " 설명",
  "created_at": "2026-09-26T00:00:00Z"
}
```

Supported operations are intentionally narrow: `create_script`, `update_script`, `create_instance`, and `set_property`. Every request requires approval inside Studio.
