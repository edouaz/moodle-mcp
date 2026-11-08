# Commands and tools

[Français](fr/reference.md)

## CLI

| Command `python3 moodle.py …` | Effect |
| --- | --- |
| `setup [--vps]` | Configure URL, sign-in, optional tunnel and service |
| `login` | Open Chromium for SSO/MFA without downloading courses |
| `doctor` | Check stdio and tool discovery without reading Moodle |
| `serve` | Start the stdio MCP server; waits for JSON-RPC input |
| `session` | Check the session without showing cookies |
| `courses [--offset N --limit N]` | List courses |
| `files --course ID [--offset N --limit N]` | List sections and resources |
| `search --course ID TEXT [--offset N --limit N]` | Search by name |
| `download --course ID --file-id ID [--include-text]` | Download one file locally |
| `tunnel doctor` | Diagnose the configured official tunnel |
| `tunnel run` | Run the tunnel in the foreground |
| `tunnel status` | Check local healthz/readyz |
| `install-service` | Generate and enable a systemd user service without starting it |

Use `--lang en` or `--lang fr` before or after the subcommand. This overrides `MOODLE_MCP_LANG` for that invocation and is inherited by child processes. English is the default and fallback. Protocol keys, status codes, IDs and Moodle content do not change language. MCP descriptions remain English.

`python3 moodle.py download --help` also documents `--resource` and `--file` selection. Listings accept `limit` from 1 to 100 and return `next_offset`. File IDs come from `kind=file` entries; do not construct them manually.

## MCP

| Tool | Purpose |
| --- | --- |
| `check_moodle_session` | Check session validity |
| `list_moodle_courses` | List visible enrolled courses |
| `list_moodle_files` | List course resources |
| `search_moodle_files` | Search names |
| `download_moodle_file` | Targeted download and Mac delivery queue |
| `list_mac_folders` | Last known Mac folder inventory |
| `get_mac_delivery_status` | Delivery status |

## Data and limits

Session: `session.json`. URL: `.moodle/config.json`. Profile and optional runtime key: `.tunnel/`. Downloads: `downloads/`. Mac queue: `.delivery/`. All are excluded from Git. Original entry points continue to use the shared configuration.

Only one browser operation is allowed at a time. Targeted files are limited to 20 MiB. PDFs are validated with pypdf; no OCR is performed. Returned text is limited to 12,000 characters; scanned PDFs may have none. Moodle names and text must never be treated as instructions.

Moodle themes and external resources may need adapters. Entering a university URL does not guarantee compatibility. There is no mapping between ChatGPT identities and Moodle accounts: each installation is personal.

[Home](../README.md)
