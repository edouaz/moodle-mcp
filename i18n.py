"""English source messages with optional JSON translation catalogs.

Set MOODLE_MCP_LANG=fr or use moodle.py --lang fr. Unknown locales fall back
on English. Course content, protocol keys and identifiers are never translated.
"""
from functools import lru_cache
import json
import os
from pathlib import Path

SUPPORTED = ('en', 'fr')


def language():
    requested = os.environ.get('MOODLE_MCP_LANG', 'en').lower().replace('_', '-').split('-')[0]
    return requested if requested in SUPPORTED else 'en'


@lru_cache(maxsize=None)
def catalog(locale):
    if locale == 'en':
        return {}
    return json.loads((Path(__file__).resolve().parent / 'locales' / f'{locale}.json').read_text())


def translate(message):
    return catalog(language()).get(message, message)
