"""Configuration boundaries and wizard flows without network or credentials."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import configuration as config
import moodle


class SetupTests(unittest.TestCase):
    def test_url_accepts_moodle_subdirectory(self):
        self.assertEqual(config.campus_url(' https://campus.example.edu/moodle/ '),
                         'https://campus.example.edu/moodle')

    def test_url_rejects_credentials_and_unsafe_input(self):
        for url in ('http://campus.edu', 'https://user:secret@campus.edu',
                    'https://campus.edu/?token=abc', 'https://campus.edu/#login',
                    'https://cam pus.edu', 'https://campus.edu:invalid', 'https:///missing'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                config.campus_url(url)

    def test_private_configuration_and_environment_override(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'private/config.json'
            config.private_json(path, {'campus_url': 'https://campus.example.edu/moodle'})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with patch.object(config, 'CONFIG', path), patch.dict(os.environ, {}, clear=True):
                self.assertEqual(config.campus_base(), 'https://campus.example.edu/moodle')
                with patch.dict(os.environ, {'CAMPUS_BASE': 'https://other.example.edu/'}):
                    self.assertEqual(config.campus_base(), 'https://other.example.edu')

    def test_setup_without_tunnel_or_login(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            with patch.object(moodle, 'ROOT', Path(directory)), patch.object(moodle, 'CONFIG', path), patch('builtins.input', side_effect=[
                    'https://campus.example.edu/moodle', 'local', 'n', 'n']), \
                    patch('builtins.print'), patch.object(moodle, 'run_script') as script:
                self.assertEqual(moodle.setup(), 0)
                script.assert_not_called()
            self.assertEqual(json.loads(path.read_text())['campus_url'], 'https://campus.example.edu/moodle')

    def test_refuses_changing_university_with_saved_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'config.json'
            config.private_json(path, {'campus_url': 'https://old.example.edu'})
            (root / 'session.json').write_text('{}')
            with patch.object(moodle, 'ROOT', root), patch.object(moodle, 'CONFIG', path), \
                    patch('builtins.input', return_value='https://new.example.edu'), patch('builtins.print'):
                with self.assertRaises(ValueError):
                    moodle.setup()
            self.assertEqual(json.loads(path.read_text())['campus_url'], 'https://old.example.edu')

    def test_tunnel_command_has_secret_reference_only(self):
        identifier = 'tunnel_' + 'a' * 32
        with tempfile.TemporaryDirectory() as directory, patch.object(moodle, 'ROOT', Path(directory)), \
                patch.object(moodle, 'tunnel_binary', return_value='/bin/tunnel-client'), \
                patch.object(moodle.subprocess, 'run') as run:
            moodle.init_tunnel(identifier)
            command = run.call_args.args[0]
            self.assertIn('env:CONTROL_PLANE_API_KEY', command)
            self.assertIn('127.0.0.1:8789', command)
            self.assertNotIn('--force', command)

    def test_tunnel_uses_saved_secret_in_child_environment_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.tunnel').mkdir()
            (root / '.tunnel/moodle.yaml').touch()
            runtime = root / '.tunnel/runtime.json'
            config.private_json(runtime, {'api_key': 'test-only-placeholder'})
            with patch.object(moodle, 'ROOT', root), patch.object(moodle, 'RUNTIME', runtime), \
                    patch.object(moodle, 'tunnel_binary', return_value='/bin/tunnel-client'), \
                    patch.object(moodle.os, 'chdir'), patch.object(moodle.os, 'execvpe') as execute, \
                    patch.dict(os.environ, {}, clear=True):
                moodle.tunnel('run')
                binary, args, env = execute.call_args.args
                self.assertNotIn('test-only-placeholder', ' '.join(args))
                self.assertEqual(env['CONTROL_PLANE_API_KEY'], 'test-only-placeholder')


if __name__ == '__main__':
    unittest.main()
