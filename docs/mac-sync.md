# Receive files on your Mac

[Français](fr/mac-sync.md)

MCP queues downloads in `.delivery/` on the server. The macOS client fetches files over SSH, verifies SHA-256 and acknowledges receipt. The server then cleans up delivered copies. This client is optional; `moodle.py download` saves locally without using this queue.

## Prepare SSH

Set up an SSH key and make an initial interactive connection to verify the host fingerprint:

```bash
ssh student@vps.example.org
```

The client rejects unknown hosts and runs without password prompts. An alias in `~/.ssh/config` can simplify the host name. The SSH account needs access to the checkout and `.delivery/`. Python 3.11+ must be available as `python3` on the server.

## Install on the Mac

Clone the project and create a Python environment as described in the [local guide](local.md). No second Moodle session or tunnel is needed. From the Mac checkout:

```bash
.venv/bin/python sync_mac.py install \
  --host student@vps.example.org \
  --remote-path project/moodle-mcp/downloads
```

`--remote-path` is the server downloads path, relative to the SSH home or absolute. `delivery.py` must live in its parent directory. Adjust the path to match your checkout. The client attempts an initial sync, then installs a LaunchAgent that runs every 30 seconds.

MCP can select `Documents`, `Desktop` or `Downloads` and a relative subfolder. The default is `~/Downloads/Moodle/NAME.pdf`. Different files with the same name get a suffix; absolute destinations and path traversal are rejected. macOS may request folder access.

```bash
.venv/bin/python sync_mac.py status
.venv/bin/python sync_mac.py once --host student@vps.example.org --remote-path project/moodle-mcp/downloads
.venv/bin/python sync_mac.py uninstall
```

The legacy LaunchAgent label `fr.edouard.moodle-downloads` is preserved for upgrades. Logs are in `~/Library/Logs/fr.edouard.moodle-downloads.log`.

Only folder names from Documents/Desktop/Downloads enter the inventory, never document contents. Snapshots can be stale or partial. Only `get_mac_delivery_status` with `delivered` confirms receipt. Files stay queued on the VPS while the Mac is off.

[Home](../README.md) · [Reference](reference.md)
