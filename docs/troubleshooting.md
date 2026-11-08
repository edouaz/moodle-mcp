# Troubleshooting

[Français](fr/troubleshooting.md)

| Symptom | Action |
| --- | --- |
| Missing or old `python3` | Install Python 3.11+ and rerun `bash setup.sh` |
| Cannot create venv | Debian/Ubuntu: `sudo apt install python3-venv` |
| Missing Chromium or libraries | On Linux: `.venv/bin/python -m playwright install --with-deps chromium` |
| Headless VPS | Use a secure display, then `python3 moodle.py login`; [guide](vps.md) |
| `SESSION_EXPIRED` | Stop tunnel/service, run `login`, check `session`, then restart |
| `MOODLE_BUSY` | Wait for the other browser operation to finish |
| Wrong university | Check `CAMPUS_BASE`; explicitly remove the old session before changing the setup URL |
| Tunnel missing or rejected | Check organization, ID, key and permissions; run `python3 moodle.py tunnel doctor` |
| Port 8789 already used | Stop the other tunnel instance; do not run the service and foreground mode together |
| `HTML_INSTEAD_OF_FILE` | Sign in again, then reselect the file |
| Mac files stay `queued` | Check SSH, LaunchAgent and macOS folder permissions |
| `systemctl --user` unavailable | Use a systemd user session, or run the foreground tunnel in your supervisor |
| Wrong interface language | Check `MOODLE_MCP_LANG`; use `--lang en` to override it for a CLI invocation |

## Update

Stop the tunnel, then:

```bash
git pull --ff-only
bash setup.sh
python3 moodle.py doctor
```

On VPS, use `bash setup.sh --vps`. Setup offers your existing URL and asks before replacing the profile. Private files stay local.

## Uninstall

On a VPS:

```bash
systemctl --user disable --now moodle-tunnel
rm ~/.config/systemd/user/moodle-tunnel.service
systemctl --user daemon-reload
```

On Mac, remove the optional client with `.venv/bin/python sync_mac.py uninstall`. Revoke the tunnel and key in OpenAI Platform when no longer needed. You can then delete the checkout and private data. Delivered documents remain in their destination folders. `~/.local/bin/tunnel-client` may serve other projects; check before removing it.

## Report a problem

Include Python version, OS and redacted diagnostic output. Never publish cookies, keys, sessions or course documents in an issue. See [SECURITY.md](../SECURITY.md).
