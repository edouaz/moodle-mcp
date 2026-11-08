# Languages and translations

English is the source language. The site and documentation also have French editions. Runtime messages use a small standard-library-only catalog, with no translation service or extra dependency.

## Choose a language

```bash
bash setup.sh --lang fr
python3 moodle.py setup --lang fr
MOODLE_MCP_LANG=fr python3 moodle.py courses
python3 moodle.py --lang en courses
```

`--lang` overrides the environment for that process and its children. `MOODLE_MCP_LANG` defaults to `en`; regional values such as `fr_FR` or `fr-FR` resolve to French. Unsupported environment locales fall back to English. CLI flags accept supported language codes only, so typos are reported.

The website uses explicit URLs: `/moodle-mcp/` for English, `/moodle-mcp/fr/` for French. EN/FR links preserve the current page (home or guide), work without JavaScript and are shareable. No browser-language detection, translation API or cookies are needed.

## Add a CLI language

1. Copy `locales/fr.json` to `locales/CODE.json` and translate the values. Keys are English source messages. Preserve command names, URLs and formatting.
2. Add the code to `SUPPORTED` in `i18n.py`.
3. Wrap new runtime messages with `tr('English source message')`, imported as `from i18n import translate as tr`.
4. Run `.venv/bin/python -m unittest -v test_i18n test_setup` and the full suite. Add coverage for the new locale.

Missing catalog entries fall back to their English source. Runtime catalogs are loaded relative to the module path and cached per locale, so clients can start from any working directory. Do not translate protocol keys, error codes, filenames, resource IDs or university content. Tool descriptions remain English so their API documentation stays consistent. Dependency output, legacy browser progress messages and some formatted diagnostics remain English.

## Website and documentation

Copy `docs/fr/` as the starting point for another language, update `lang`, page copy and language links, and keep shared asset references relative to `../assets/`. Keep fragment IDs and commands stable. Add clipboard messages in `docs/assets/site.js` for the new locale. Translate the Markdown guides and keep relative repository links correct. Review both language editions when changing behavior; there is no automatic translation pipeline.

[Home](../README.md) · [Contributing](../CONTRIBUTING.md)
