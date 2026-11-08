# Local installation

[Français](fr/local.md)

## Prepare

Install Git and Python 3.11+ on macOS or Linux, then:

```bash
git clone https://github.com/edouaz/moodle-mcp.git
cd moodle-mcp
bash setup.sh
```

The bootstrap creates `.venv`, installs `requirements.txt` and Chromium, then opens the wizard. On Debian/Ubuntu, install `python3-venv` if needed. If Chromium reports missing system libraries on Linux:

```bash
.venv/bin/python -m playwright install --with-deps chromium
```

Enter the Moodle base URL, keeping any `/moodle` subdirectory. Do not enter `/login/index.php` or a course URL. Choose `local`. In Chromium, complete university sign-in, open your course list, then return to the terminal and press Enter. Setup never reads your university password.

Configure the tunnel or skip that step. Settings are in `.moodle/config.json`. `CAMPUS_BASE` overrides the URL for a process; unset it to use the saved setting.

English is the default. Use `bash setup.sh --lang fr` for French, or `MOODLE_MCP_LANG=fr` for subsequent commands.

## Verify

```bash
python3 moodle.py doctor
python3 moodle.py session
python3 moodle.py courses
```

The first checks MCP without accessing Moodle. The others use your session. Pass `next_offset` back as `--offset` for the next page.

## Local MCP client

Adjust the absolute paths in your client’s configuration:

```json
{
  "mcpServers": {
    "moodle": {
      "command": "/absolute/path/to/moodle-mcp/.venv/bin/python",
      "args": ["/absolute/path/to/moodle-mcp/mcp_server.py"]
    }
  }
}
```

The exact configuration format depends on the client. The server reads the saved URL even when launched from another directory. Stdio requires neither a tunnel nor an OpenAI key. Set `MOODLE_MCP_LANG` in the client’s child-process environment for translated runtime messages; MCP tool descriptions remain English.

## Windows

Session locking uses `fcntl`, so native Windows is unsupported. Use WSL2 with Python and WSLg or an equivalent display, and install the project in the Linux filesystem. This path has not been validated on the development machine; macOS/Linux are the primary targets.

[Home](../README.md) · [VPS](vps.md) · [Troubleshooting](troubleshooting.md)
