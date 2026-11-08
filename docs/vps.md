# Install on a VPS

[Français](fr/vps.md)

Use a dedicated non-root Linux account, Python 3.11+ and persistent storage. Ubuntu 24.04 or Debian 12+ with systemd are the documented starting points. Allow enough memory for Chromium; 2 GiB is a starting point to adjust to your workload.

## 1. Install from the terminal

```bash
sudo apt update
sudo apt install git python3 python3-venv ca-certificates
mkdir -p ~/project
cd ~/project
git clone https://github.com/edouaz/moodle-mcp.git
cd moodle-mcp
bash setup.sh --vps
```

Bootstrap installs browser system dependencies, using `sudo` when needed. Choose `vps`, enter the Moodle URL and configure the tunnel. The runtime key can be stored in `.tunnel/runtime.json` with `600` permissions for automatic restarts. Add `--lang fr` to run the wizard in French.

## 2. Sign in to Moodle on the VPS

Setup detects a missing display and defers sign-in. SSO/MFA needs a graphical browser. From a computer with an X server, one option is X11 forwarding over SSH:

```bash
ssh -X student@vps.example.org
cd ~/project/moodle-mcp
python3 moodle.py login
```

This requires an X server on your computer (for example XQuartz on Mac), `xauth` on the VPS and X11 forwarding enabled in SSH. Alternatively, use a remote desktop accessible only over SSH. If Chromium cannot start with your forwarded display, use that secure desktop and run `login` in its terminal.

Sign in in the browser running on the VPS, then confirm in the terminal. A session copied from another machine or IP may be rejected by the university. The project does not bypass these restrictions or install a remote desktop automatically.

```bash
python3 moodle.py session
python3 moodle.py courses
python3 moodle.py doctor
python3 moodle.py tunnel doctor
```

## 3. Keep the tunnel running

If you did not install the service during setup:

```bash
python3 moodle.py install-service
systemctl --user start moodle-tunnel
systemctl --user status moodle-tunnel
```

The generated unit uses the actual checkout paths and lives in `~/.config/systemd/user/moodle-tunnel.service`. The runtime key must be saved during setup. Installation enables the service but does not start it before Moodle sign-in.

To start at boot without an SSH session:

```bash
sudo loginctl enable-linger "$USER"
```

Setup does not change this system setting automatically. Everyday management:

```bash
journalctl --user -u moodle-tunnel -n 50
systemctl --user restart moodle-tunnel
systemctl --user stop moodle-tunnel
python3 moodle.py tunnel status
```

Health checks listen on `127.0.0.1:8789`. No incoming MCP port needs opening. The tunnel requires outbound HTTPS to OpenAI. ChatGPT connection availability depends on your account and permissions; see the [tunnel guide](tunnel.md).

For French runtime messages in the service, add `Environment=MOODLE_MCP_LANG=fr` using `systemctl --user edit moodle-tunnel` under a `[Service]` section, then restart it. CLI `--lang` only applies to that invocation.

## 4. Renew an expired session

Stop the service, sign in using the secure display, verify, then restart:

```bash
systemctl --user stop moodle-tunnel
python3 moodle.py login
python3 moodle.py session
systemctl --user start moodle-tunnel
```

To receive files on your Mac, follow the [SSH guide](mac-sync.md). Without this client, MCP downloads remain queued on the server. A VPS path is not a file received on your computer.

## Update

Stop the service, run `git pull --ff-only`, then `bash setup.sh --vps` to update dependencies and review settings. Run `install-service` again if the checkout path changed. Check diagnostics before restarting. Keep private files on protected persistent storage; they are not in the repository.

[Home](../README.md) · [Troubleshooting](troubleshooting.md)
