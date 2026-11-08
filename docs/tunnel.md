# Connect an OpenAI tunnel

[Français](fr/tunnel.md)

The CLI and stdio MCP clients work without a tunnel. For compatible OpenAI products, the official client reaches your private server through outbound HTTPS connections. [Official guide](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).

## Prepare access

1. In [OpenAI Platform / Tunnels](https://platform.openai.com/settings/organization/tunnels), select your organization and create a personal tunnel. Keep its `tunnel_…` ID.
2. Verify tunnel creation/management permissions, then usage permissions for the operator and runtime key. Permission to add a connection in your client is separate.
3. Create a [runtime key](https://platform.openai.com/settings/organization/api-keys) in the same organization with the required tunnel permissions. Do not use an administration key for the service.

## Configure

```bash
python3 moodle.py setup
```

Setup offers to install the official client if missing. The installer verifies the archive’s published SHA-256 digest before replacing `~/.local/bin/tunnel-client`. You can also install it from the [official releases](https://github.com/openai/tunnel-client/releases/latest).

Enter the ID and key at the hidden prompt. `.tunnel/moodle.yaml` contains an `env:CONTROL_PLANE_API_KEY` reference. The key is either requested at startup or saved in `.tunnel/runtime.json` with `600` permissions if you agree. An existing `CONTROL_PLANE_API_KEY` environment variable takes priority over the saved file.

```bash
python3 moodle.py tunnel doctor
python3 moodle.py tunnel run
```

The tunnel runs in the foreground. Stop with Ctrl-C. In another terminal, run `python3 moodle.py tunnel status`. Port 8789 stays on loopback.

## Add the connection

In your compatible OpenAI product, add an MCP server, choose **Tunnel** and select the configured tunnel. In ChatGPT, the location and availability of custom MCP connections depend on your account and workspace. See the [official connection guide](https://developers.openai.com/api/docs/guides/custom-mcp-server).

The server adds no application-level authentication: access relies on the tunnel and personal connection. Anyone authorized to use it can access your university session. Do not share the tunnel or connection in a collective workspace.

Verify the seven tools and ask your assistant to list courses. A successful call confirms this connection. The local stdio diagnostic alone does not.

## Rotate a key

Stop the service/tunnel, rerun `setup` and enter the new key. If you decline storage, the older saved key is removed. Leave input empty to keep the existing key. Rerun the diagnostic, then restart the service.

[Home](../README.md) · [VPS](vps.md)
