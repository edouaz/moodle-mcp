# moodle-browser-scraper

Bulk-download your Moodle course materials via a real browser session (Playwright).
Works with institutional **SSO** login and even when the Moodle **mobile / web-services
API is disabled** — the case where [`moodle-dl`](https://github.com/C0D3D3V/Moodle-DL)
can't connect. Incremental downloads, files organized by course and section.

## Why this exists

Most Moodle downloaders (like the excellent `moodle-dl`) talk to the **Moodle Web
Services / mobile API**. If your university **disables that API**, or hides downloads
behind an **SSO login** (Shibboleth/OAuth) and JavaScript-rendered pages, those tools
stop working.

`moodle-browser-scraper` takes a different approach: it drives a **real browser**
(Chromium via Playwright). **You log in yourself**, exactly as you normally would, and
the script then walks your courses and downloads the files. Because a human does the
login in a real browser, SSO and JS just work, and no API token is needed.

> It is **not** meant to compete with `moodle-dl` when the API is available — `moodle-dl`
> is more capable there. This tool is for the cases where the API route is closed.

## Features

- 🔐 **Manual login in a real browser** — handles SSO/Shibboleth/OAuth, no API token.
- 💾 **Session reuse** — logs in once, saves the session, runs unattended afterwards.
- 🗂️ **Organized output** — files saved per **course** and **section**.
- ♻️ **Incremental** — skips files already downloaded; logs only what's new each run.
- 🪵 **Run log** — `_new_files_log.md` records new uploads (handy to spot fresh material).
- 🚫 **Skips** videos/audio and files over 300 MB (configurable).
- 🪟 **Windows long-path safe** (`\\?\` prefix, beyond the 260-char limit).

## Requirements

- Python 3.10+
- [Playwright](https://playwright.dev/python/)

## Install

```bash
pip install -r requirements.txt
playwright install chromium
```

## Usage

```bash
python scraper.py
```

- **First run:** a Chromium window opens. Log in with your own account. When you can
  see your course list, return to the terminal and press **Enter**. The session is
  saved to `session.json`.
- **Next runs:** it reuses `session.json` and goes straight to downloading.
- Files are saved in folders **next to the script**, grouped by course and section.

If your campus is **not** the default one, point it to your Moodle:

```bash
# Linux / macOS
CAMPUS_BASE=https://your.campus.edu python scraper.py
# Windows (PowerShell)
$env:CAMPUS_BASE="https://your.campus.edu"; python scraper.py
```

(or edit the `BASE` line at the top of `scraper.py`.)

## Output

```
scraper.py
<Course name>/
    <Section name>/
        lecture1.pdf
        slides.pptx
_new_files_log.md      # what was newly downloaded each run
_skipped_urls.txt      # URLs that failed (won't be retried)
session.json           # your login session — PERSONAL, never share it
```

## How it compares

| | This tool | `moodle-dl` | Moodle's built-in download |
|---|---|---|---|
| Method | Browser session (Playwright) | Web-services / mobile API | Server feature |
| Works with SSO / JS pages | ✅ | depends | ✅ |
| Works when the API is disabled | ✅ | ❌ | ✅ (if enabled by admin) |
| Needs admin to enable anything | ❌ | needs API/token | needs per-course toggle |
| Scope | Files & folder resources | Almost everything (assignments, forums, quizzes, external videos…) | File/Folder/Page/Label |

If `moodle-dl` works on your campus, prefer it. Use this when it doesn't.

## Notes

- Use it **only with your own account** and in line with your institution's terms of
  use. It downloads the materials **you already have access to** — Moodle enforces access
  control on the server.
- `session.json` contains your login session (cookies). **Never commit or share it.**

## License

[MIT](LICENSE) © 2026 thntx
