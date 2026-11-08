# Contributing

Fixes, adapters for other Moodle themes and documentation improvements are welcome. Describe your institution and theme without publishing personal data. Use synthetic fixtures for tests.

Install with `bash setup.sh` (you can skip sign-in and tunnel), then run:

```bash
.venv/bin/python -m unittest -v test_login_only test_targeted test_service test_mcp test_delivery test_sync_mac test_setup test_i18n
.venv/bin/python diagnose_mcp.py
```

Tests use no accounts or secrets. One parser test uses a local Chromium fixture. The diagnostic checks real stdio; it does not validate a ChatGPT connection. `diagnose_mcp.py --live` is a legacy course-specific diagnostic: adapt it before use and never run it in CI.

English is the default language. See [translations](docs/translating.md) for runtime catalogs and website languages. Keep French documentation in sync when changing behavior.

Keep changes focused. Exclude all new runtime data from Git. Never use `git add -f` for sessions, course files or keys. The static site lives in `docs/`, with no bundler, CDN or external service. Check links and mobile layout before changing presentation.

Contributions are distributed under the project’s MIT license.
