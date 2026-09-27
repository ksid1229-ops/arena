# Arena ↔ Roblox Studio bridge

A small, dependency-free bridge for agents working in this repository. An Arena-side Python broker queues requests; a local Roblox Studio plugin polls over HTTPS. **Every request, including reading scripts, needs a click in Studio.** This is a custom HTTP bridge, not an MCP server.

## What it can do

- Inspect an instance's class and immediate children (up to 200); read script source.
- Create allowlisted objects such as Parts, Models, GUI elements, and scripts.
- Modify allowlisted properties with vectors, colors, enums, and CFrames.
- Update script source using Studio's script editor API, with an expected-source conflict check.
- Delete non-service instances with approval; group edits into Studio Undo recordings.

No arbitrary Luau execution, shell access, publishing, automatic playtests, or unattended approval. New Script/LocalScript instances start disabled. ModuleScripts can still execute if your existing code requires them. Use a backup place and stop Play before approving requests.

## First-time setup

### 1. Start the broker in Arena

Python 3.10+; no packages needed:

```sh
python -m roblox_bridge.server --host 0.0.0.0 --port 8765
```

In an agent chat, ask the agent to run this via its **background process tool**, not a short-lived terminal command. Arena exposes the port as an HTTPS live preview. Copy the full preview origin (like `https://8765-SANDBOX-ID.e2b.app`), not the Arena chat URL. The preview root only shows a public health message; it is not a control panel.

A random token is generated in `.bridge/token`, excluded from Git. Open that file privately in your workspace/file viewer, or read it in your own terminal, and copy its contents to the plugin. **Do not paste it into chat, commit it, or include it in screenshots.** The agent should use the token file directly without printing it. Anyone with this token can submit requests and read their results.

### 2. Install the local plugin in Roblox Studio

1. On your computer, download `studio/ArenaBridge.plugin.lua` from this branch (or clone/pull this repository).
2. In Studio, open a backup place. Create a temporary **Script** in ServerStorage and paste the file's full contents into it. Do not run the script.
3. Right-click the Script in Explorer and choose **Save as Local Plugin** (the wording/location may differ between Studio versions). Name it Arena Bridge. Delete the temporary Script from your place after saving.
4. If the toolbar doesn't appear, restart Studio and check **Manage Plugins** that the local plugin is enabled.
5. Open **Arena Bridge → Bridge**. Paste the HTTPS preview origin and token, then click **Connect / Disconnect**. Allow Studio's plugin HTTP permission prompt for that host. If Studio reports HTTP is disabled, enable HTTP requests under your place's security settings. If script editing permission is requested, grant it only to this plugin you installed.
6. Tell the agent you've connected. It can now check `python -m roblox_bridge.client status` without seeing your token in chat.

Connection details are deliberately not saved by the plugin. Install the code only as a trusted local plugin, not as a runtime game script or public free model. The plugin connects outward; you don't need to expose a port on your computer.

### 3. Review a first request

The agent creates a JSON file, then submits it:

```sh
mkdir -p .bridge
printf '%s' '{"op":"inspect","path":["Workspace"]}' > .bridge/request.json
python -m roblox_bridge.client send .bridge/request.json
python -m roblox_bridge.client get COMMAND_ID
```

In Studio, review the request and click **Approve this request** or **Reject this request**. The review text box is selectable: copy long payloads into a local editor to read them fully before approving. Never approve an unread script. Approval applies the submitted payload, not any review-box text.

## Command examples

Paths are arrays of exact instance names, starting with an allowed service. Duplicate sibling names cause an error instead of choosing a random target. `create` uses the parent's path; other operations use the target's path.

```json
{"op":"create","path":["Workspace"],"args":{"class":"Part","name":"ArenaPlatform","properties":{"Anchored":true,"Size":{"type":"Vector3","value":[20,1,20]},"Position":{"type":"Vector3","value":[0,5,0]},"Color":{"type":"Color3","value":[0.2,0.6,1]}}}}
```

```json
{"op":"set_properties","path":["Workspace","ArenaPlatform"],"args":{"properties":{"Material":{"type":"Enum","value":["Material","Neon"]}}}}
```

```json
{"op":"create","path":["ServerScriptService"],"args":{"class":"Script","name":"ArenaHello"}}
```

Inspect a script first; copy the returned `source` exactly into `expected_source`:

```json
{"op":"set_script","path":["ServerScriptService","ArenaHello"],"args":{"expected_source":"","source":"print(\"Hello from Arena\")\n"}}
```

The example assumes the inspected source is empty; use the actual returned text. Enabling an executable script is a separate `set_properties` request with `{"Disabled":false}`. Test manually in Studio after reviewing the code.

```json
{"op":"delete","path":["Workspace","ArenaPlatform"]}
```

Typed values: `Vector2`, `Vector3`, `Color3` (0–1 channels), `UDim`, `UDim2`, `CFrame` (3 position numbers or 12 components), and `Enum` (`[enumType, member]`). Plain strings, numbers, and booleans are supported. See the plugin's `classes`, `properties`, and `roots` tables for exact allowlists. This intentionally doesn't expose every Studio API.

## Reconnect in future chats

The repository saves the bridge, **not a permanent connection or tool registration**. Future chats must have this branch/files and process tools available. Ask:

> Read AGENTS.md and start the Roblox bridge. I'll reconnect the local Studio plugin to the new HTTPS preview URL and token. Wait for my connection and approvals before editing.

Each new environment may have a new URL and token. If running outside Arena, the same broker works locally using `http://127.0.0.1:8765`. Never send a token over plain HTTP to a remote host.

## Reliability and security limits

- One Studio session per broker. A different session cannot take over until the old heartbeat has been absent for 30 seconds; takeover marks old unfinished commands `unknown`, never silently moves them to another place.
- Requests require a connected Studio heartbeat before submission. There is one in-flight request at a time. Mutations are never automatically retried. Result reporting is idempotent.
- Queue/results are memory-only, capped at 1,000 requests; restarting loses them. If Studio or the broker crashes after an edit, inspect the place before resubmitting. A delivered request may remain stuck after a crash; restart the broker and reconnect rather than assume it failed.
- Disconnect stops networking, not an already approved operation. Reject pending work before disconnecting. Closing the dock doesn't disconnect; use the button or disable the plugin.
- Undo is best-effort Studio recording, not a transaction. Failed property batches can partially apply; Undo and inspect before retrying. External script side effects are not undone.
- Read results can include proprietary script source. They travel through Arena's HTTPS preview infrastructure and live in broker memory; don't use this with places you aren't authorized to share.
- No CORS/browser control panel, token logging, or saved plugin credentials. Local token file permissions are restricted on POSIX. Restart with a new token to revoke access; stop the server when finished.
- The Python broker is tested here. Studio UI, permission prompts, Undo, and script editor integration **must be verified in your installed Studio**; this environment cannot run Roblox Studio.

## Development / verification

```sh
python -m unittest discover -s tests -v
python -m compileall -q roblox_bridge tests
```

Manual Studio smoke test: connect; approve inspect; reject create and verify nothing appears; approve create; Undo; create a disabled script; inspect and update its source; check stale `expected_source` fails; verify requests fail during Play; disconnect. Never claim Studio integration is verified until this has been run in Studio.
