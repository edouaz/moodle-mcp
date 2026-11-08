"""Language selection, safe fallback and real CLI propagation without accounts."""
import ast
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import i18n
import moodle
import configuration

ROOT = Path(__file__).resolve().parent


class LanguageTests(unittest.TestCase):
    def test_default_english_and_unknown_locale_fallback(self):
        for environment in ({}, {'MOODLE_MCP_LANG': 'unknown'}, {'LANG': 'fr_FR.UTF-8'}):
            with self.subTest(environment=environment), patch.dict(os.environ, environment, clear=True):
                self.assertEqual(i18n.language(), 'en')
                self.assertEqual(i18n.translate('A value is required.'), 'A value is required.')

    def test_french_regional_locale_and_missing_message_fallback(self):
        for locale in ('fr', 'fr_FR', 'fr-FR'):
            with self.subTest(locale=locale), patch.dict(os.environ, {'MOODLE_MCP_LANG': locale}):
                self.assertEqual(i18n.translate('A value is required.'), 'Une valeur est requise.')
                self.assertEqual(i18n.translate('New source message'), 'New source message')

    def test_runtime_catalog_covers_all_marked_messages(self):
        catalog = i18n.catalog('fr')
        for path in ROOT.glob('*.py'):
            if path.name.startswith('test_'):
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == 'tr' and node.args
                        and isinstance(node.args[0], ast.Constant)):
                    message = node.args[0].value
                    self.assertIn(message, catalog, f'{path.name}: {message}')
                    self.assertTrue(catalog[message])

    def test_language_flag_overrides_environment_and_reaches_child_cli(self):
        env = dict(os.environ, MOODLE_MCP_LANG='fr')
        english = subprocess.run([sys.executable, str(ROOT / 'moodle.py'), '--lang', 'en',
                                  'download', '--help'], env=env, capture_output=True, text=True, check=True)
        french = subprocess.run([sys.executable, str(ROOT / 'moodle.py'), 'download', '--help',
                                 '--lang', 'fr'], env=dict(os.environ, MOODLE_MCP_LANG='en'),
                                capture_output=True, text=True, check=True)
        self.assertIn('Exact filename within a folder', english.stdout)
        self.assertNotIn('Nom exact', english.stdout)
        self.assertIn('Nom exact du fichier', french.stdout)
        self.assertNotIn('MOODLE_MCP_LANG', english.stdout)

    def test_wizard_prompts_and_saved_schema_in_both_languages(self):
        for locale, welcome in (('en', 'Welcome!'), ('fr', 'Bienvenue !')):
            with self.subTest(locale=locale), tempfile.TemporaryDirectory() as directory:
                config = Path(directory) / 'config.json'
                output = io.StringIO()
                with patch.dict(os.environ, {'MOODLE_MCP_LANG': locale}), \
                        patch.object(moodle, 'ROOT', Path(directory)), patch.object(moodle, 'CONFIG', config), \
                        patch('builtins.input', side_effect=['https://campus.example.edu', 'local', 'n', 'n']), \
                        contextlib.redirect_stdout(output):
                    self.assertEqual(moodle.setup(), 0)
                self.assertIn(welcome, output.getvalue())
                self.assertEqual(json.loads(config.read_text()),
                                 {'campus_url': 'https://campus.example.edu', 'mode': 'local'})

    def test_tunnel_ids_and_error_codes_do_not_change_with_language(self):
        import moodle_service
        for locale in ('en', 'fr'):
            with patch.dict(os.environ, {'MOODLE_MCP_LANG': locale}):
                identifier = 'tunnel_' + 'a' * 32
                self.assertEqual(moodle.tunnel_id(identifier), identifier)
                with self.assertRaises(moodle_service.MoodleError) as caught:
                    moodle_service.paginate([], limit=101)
                self.assertEqual(caught.exception.code, 'INVALID_PAGE')
                with self.assertRaises(ValueError):
                    configuration.campus_url('http://campus.example.edu')


if __name__ == '__main__':
    unittest.main()
