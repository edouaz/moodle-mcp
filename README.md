<p align="center"><img src="docs/assets/logo.svg" width="112" alt="Moodle MCP, a little page wearing an orange graduation cap"></p>
<h1 align="center">Moodle MCP</h1>
<p align="center"><strong>Fewer clicks. More learning. 🎓</strong><br>Your Moodle resources in your assistant, with a session that stays on your machine.</p>
<p align="center"><strong>English</strong> · <a href="docs/fr/README.md">Français</a><br><a href="https://edouaz.github.io/moodle-mcp/">Website</a> · <a href="https://edouaz.github.io/moodle-mcp/guide.html">Getting started</a> · <a href="docs/vps.md">VPS guide</a></p>
<p align="center"><a href="https://github.com/edouaz/moodle-mcp/actions/workflows/ci.yml"><img src="https://github.com/edouaz/moodle-mcp/actions/workflows/ci.yml/badge.svg" alt="Tests"></a> <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB" alt="Python 3.11+"> <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-orange" alt="MIT license"></a></p>

Moodle MCP uses a real browser to access your courses, even when your university disables the mobile API. Sign in yourself through your institution’s SSO/MFA; the MCP server and CLI reuse that session to list, search and download the resources you choose.

## ✨ What you can do

- Find your courses and search for handouts by name.
- Download one selected file without collecting every course.
- Read up to 12,000 characters of extracted PDF text in your assistant.
- Run the server on your Mac, a Linux computer or a VPS.
- Receive files from your VPS on your Mac with the optional SSH client.

No tool modifies Moodle or submits assignments. The server stays private: local stdio, or an outbound OpenAI tunnel for compatible clients.

## 🚀 Get started

**Requirements:** Git, Python 3.11+ and macOS or Linux. On Windows, use WSL2 with a working graphical display. Ubuntu 24.04 or Debian 12+ with systemd are the documented VPS starting points.

```bash
git clone https://github.com/edouaz/moodle-mcp.git
cd moodle-mcp
bash setup.sh
```

Setup installs dependencies and Chromium, then walks you through:

1. Your Moodle **base URL**, such as `https://campus.example.edu/moodle`.
2. Local or VPS installation.
3. Browser sign-in with your university’s SSO/MFA.
4. An optional OpenAI tunnel: ID, hidden runtime key input and optional private storage.

**No Moodle token is required.** The key requested is only for the OpenAI tunnel. Skip that step for CLI use or a local stdio MCP client.

On a VPS, use `bash setup.sh --vps`. It also installs Chromium’s system dependencies and may request `sudo`. Moodle sign-in needs a secure graphical display; read the [VPS guide](docs/vps.md) before setting up a headless machine.

## 🌍 Languages

English is the default for the website, documentation, CLI and MCP tool descriptions. The website has an **EN / FR** switch; [French documentation](docs/fr/README.md) remains available.

```bash
bash setup.sh --lang fr
python3 moodle.py --lang fr setup
MOODLE_MCP_LANG=fr python3 moodle.py courses
```

`--lang` works before or after the subcommand and overrides `MOODLE_MCP_LANG` for that invocation. The language is inherited by child processes. Set the environment variable in your shell or service for a persistent preference. Upstream browser/install output and some diagnostic messages remain in English. Course titles, filenames, JSON keys and IDs are never translated.

Translations live in [`locales/fr.json`](locales/fr.json); see the [translation guide](docs/translating.md) to add a language.

## 🧭 Everyday commands

```bash
python3 moodle.py login          # sign in or renew your session
python3 moodle.py doctor         # check MCP without reading your courses
python3 moodle.py session        # check your Moodle session
python3 moodle.py courses        # list courses without downloading files
python3 moodle.py files --course 123 --limit 50
python3 moodle.py search --course 123 "Worksheet1"
python3 moodle.py download --course 123 --file-id "ID_FROM_THE_LISTING" --include-text
python3 moodle.py tunnel run     # foreground; Ctrl-C to stop
```

Replace `123` and the file ID with values from the listings. The CLI automatically uses `.venv` Python. The legacy `scraper.py` **without options downloads all courses**; use `moodle.py` for targeted operations.

## 💬 Connect your assistant

For a local MCP client, set the absolute command `…/moodle-mcp/.venv/bin/python` with the absolute argument `…/moodle-mcp/mcp_server.py`. See the [local guide](docs/local.md) for a full configuration example.

For a compatible OpenAI client, create a tunnel in [OpenAI Platform](https://platform.openai.com/settings/organization/tunnels), configure it through setup and run `python3 moodle.py tunnel run`. Add a **Tunnel** MCP connection in your client if your account/workspace supports it. Tunnel permissions are required; installing this project does not grant them. See the [tunnel guide](docs/tunnel.md) and [official OpenAI documentation](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).

Try “List my courses”, then “Find Worksheet1 in this course”. A successful call from your assistant confirms the connection; the local diagnostic alone does not.

## 🔒 Your session is personal

`session.json`, `.moodle/`, `.tunnel/`, downloads and delivery queues are excluded from Git through an explicit source allowlist. Saved sessions and keys have `600` permissions.

Anyone authorized to use your tunnel can access **your Moodle session**. Keep it personal. Selected PDF text is sent to your assistant; a complete PDF does not automatically become a ChatGPT attachment. Targeted downloads are limited to 20 MiB per file. The optional Mac delivery client requires macOS.

Compatibility depends on the Moodle theme and configuration. Other universities need verification; SSO/MFA and account restrictions are never bypassed.

## 📚 Documentation

| Need | Guide |
| --- | --- |
| Local installation and MCP client | [Local](docs/local.md) |
| Permanent server, VPS sign-in and service | [VPS](docs/vps.md) |
| Tunnel and runtime key | [OpenAI tunnel](docs/tunnel.md) |
| Receive files on your Mac | [SSH sync](docs/mac-sync.md) |
| Commands and seven MCP tools | [Reference](docs/reference.md) |
| Reconnect, troubleshoot and uninstall | [Troubleshooting](docs/troubleshooting.md) |
| Add another language | [Translations](docs/translating.md) |

## 🛠️ Contribute

```bash
.venv/bin/python -m unittest -v test_login_only test_targeted test_service test_mcp test_delivery test_sync_mac test_setup test_i18n
.venv/bin/python diagnose_mcp.py
```

Tests require neither a Moodle account nor an OpenAI key. See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) and the [changelog](CHANGELOG.md).

## License and credits

[MIT](LICENSE). Based on [moodle-browser-scraper](https://github.com/thntx/moodle-browser-scraper) by thntx; its copyright and [original README](README_UPSTREAM.md) are preserved. Moodle MCP is independent, with no affiliation to Moodle, Apple, OpenAI or a university. The logo is an original vector illustration.
