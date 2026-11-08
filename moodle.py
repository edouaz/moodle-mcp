#!/usr/bin/env python3
"""Moodle MCP: guided setup and daily commands, on macOS and Linux."""
from i18n import translate as tr, SUPPORTED
import argparse
import getpass
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

from configuration import ROOT, CONFIG, RUNTIME, campus_url, private_json, read_json


def python():
    candidate = ROOT / '.venv/bin/python'
    return str(candidate) if candidate.exists() else sys.executable


def run_script(script, *args):
    return subprocess.run([python(), str(ROOT / script), *args], cwd=ROOT).returncode


def ask(label, default='', validate=None):
    while True:
        value = input(f'{label}' + (f' [{default}]' if default else '') + ' : ').strip() or default
        try:
            if not value:
                raise ValueError(tr('A value is required.'))
            return validate(value) if validate else value
        except ValueError as exc:
            print(exc)


def yes(label, default=False):
    return input(f'{label} [{tr("Y/n") if default else tr("y/N")}] : ').strip().lower() in (
        ('', 'o', 'oui', 'y', 'yes') if default else ('o', 'oui', 'y', 'yes'))


def tunnel_binary():
    candidate = shutil.which('tunnel-client')
    fallback = Path.home() / '.local/bin/tunnel-client'
    if not candidate and fallback.is_file():
        candidate = str(fallback)
    if not candidate:
        raise ValueError(tr('tunnel-client is missing. Run python3 install_tunnel.py or run setup again.'))
    return candidate


def tunnel_id(value):
    if not re.fullmatch(r'tunnel_([a-z0-9]{4}_)?[a-z0-9]{32}', value):
        raise ValueError(tr('Paste the actual tunnel_id returned by OpenAI Platform (tunnel_…).'))
    return value


def init_tunnel(identifier):
    command = [tunnel_binary(), 'init', '--sample', 'sample_mcp_stdio_local',
               '--profile', 'moodle', '--profile-dir', str(ROOT / '.tunnel'),
               '--tunnel-id', tunnel_id(identifier), '--control-plane-api-key-ref',
               'env:CONTROL_PLANE_API_KEY', '--health-listen-addr', '127.0.0.1:8789',
               '--mcp-command', shlex.join([python(), str(ROOT / 'mcp_server.py')])]
    if (ROOT / '.tunnel/moodle.yaml').exists():
        if not yes(tr('Replace the existing tunnel profile?')):
            raise ValueError(tr('Profile kept. Run setup again to change it.'))
        command.append('--force')
    subprocess.run(command, check=True)


def tunnel(action):
    if action == 'status':
        from urllib.request import urlopen
        for path in ('healthz', 'readyz'):
            with urlopen(f'http://127.0.0.1:8789/{path}', timeout=5) as response:
                print(path, response.status, response.read().decode())
        return 0
    if not (ROOT / '.tunnel/moodle.yaml').exists():
        raise ValueError(tr('Configure the tunnel with python3 moodle.py setup.'))
    env = os.environ.copy()
    env['CONTROL_PLANE_API_KEY'] = env.get('CONTROL_PLANE_API_KEY') or read_json(RUNTIME).get('api_key', '')
    if not env['CONTROL_PLANE_API_KEY']:
        if not sys.stdin.isatty():
            raise ValueError(tr('No runtime key. Run setup again in a terminal.'))
        env['CONTROL_PLANE_API_KEY'] = getpass.getpass(tr('OpenAI runtime key (hidden): ')).strip()
    if not env['CONTROL_PLANE_API_KEY']:
        raise ValueError(tr('No runtime key provided.'))
    command = [tunnel_binary(), action, '--profile-dir', str(ROOT / '.tunnel'), '--profile', 'moodle',
               '--mcp.stdio-send-initialized-notification', '--mcp.max-concurrent-requests', '1']
    if action == 'doctor':
        command.append('--explain')
    os.chdir(ROOT)
    os.execvpe(command[0], command, env)


def service_file():
    # systemd expands percent specifiers and environment variables; quote literal paths.
    def quote(value):
        return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('$', '$$') + '"'
    return '\n'.join([
        '[Unit]', 'Description=Moodle MCP private tunnel', 'StartLimitIntervalSec=0', '',
        '[Service]', 'Type=simple', f'WorkingDirectory={quote(ROOT)}',
        f'ExecStart={quote(python())} {quote(ROOT / "moodle.py")} tunnel run',
        'Restart=on-failure', 'RestartSec=10', 'TimeoutStopSec=30', 'UMask=0077',
        'NoNewPrivileges=true', '', '[Install]', 'WantedBy=default.target', ''])


def install_service():
    if sys.platform != 'linux' or not shutil.which('systemctl'):
        raise ValueError(tr('The user service requires Linux with systemd.'))
    if not read_json(RUNTIME).get('api_key') and not os.environ.get('CONTROL_PLANE_API_KEY'):
        raise ValueError(tr('Save the runtime key during setup before installing the service.'))
    if not read_json(RUNTIME).get('api_key'):
        raise ValueError(tr('A terminal environment key does not persist in systemd. Run setup and save it.'))
    if not (ROOT / '.tunnel/moodle.yaml').exists():
        raise ValueError(tr('Configure the tunnel with setup first.'))
    destination = Path.home() / '.config/systemd/user/moodle-tunnel.service'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(service_file())
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', '--user', 'enable', 'moodle-tunnel.service'], check=True)
    print(tr('Service installed and enabled for the next user session.'))
    print(tr('After signing in to Moodle: systemctl --user start moodle-tunnel'))
    print(tr('To start at boot without an SSH session: sudo loginctl enable-linger "$USER"'))


def setup(vps=False):
    if os.name != 'posix':
        raise ValueError(tr('Use macOS, Linux or WSL2 (see the documentation).'))
    print(tr('\n🎓 Moodle MCP · Welcome!\nYour courses, your session, your machine.\n'))
    old = read_json(CONFIG)
    base = ask(tr('1/4 · Moodle base URL (e.g. https://moodle.university.edu)'), old.get('campus_url', ''), campus_url)
    if old.get('campus_url', 'https://moodle.uclouvain.be') != base and (ROOT / 'session.json').exists():
        raise ValueError(tr('Different university: explicitly remove session.json before changing the URL.'))
    mode = ask(tr('2/4 · Installation: local or vps'), 'vps' if vps else old.get('mode', 'local'),
               lambda x: x if x in ('local', 'vps') else (_ for _ in ()).throw(ValueError(tr('Choose local or vps.'))))
    private_json(CONFIG, {'campus_url': base, 'mode': mode})
    print(tr('Configuration saved. No university password will be requested here.'))
    print(tr('\n3/4 · Moodle sign-in: the browser handles your SSO and MFA.'))
    if mode == 'vps' and not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
        print(tr('Headless VPS: see docs/vps.md for secure graphical sign-in.'))
        print(tr('Then run: python3 moodle.py login'))
    elif yes(tr('Open the browser to sign in now?'), True):
        if run_script('scraper.py', '--login-only'):
            raise ValueError(tr('Sign-in interrupted. Try again with python3 moodle.py login.'))
    print(tr('\n4/4 · Private OpenAI tunnel (optional for CLI or stdio MCP clients).'))
    if yes(tr('Configure the tunnel?'), True):
        print(tr('Create your tunnel: https://platform.openai.com/settings/organization/tunnels'))
        print(tr('Runtime key from the same organization: https://platform.openai.com/settings/organization/api-keys'))
        print(tr('Personal use only: anyone authorized on this tunnel can use your Moodle session.'))
        try:
            tunnel_binary()
        except ValueError:
            if yes(tr('Install the official tunnel-client?'), True):
                if run_script('install_tunnel.py'):
                    raise ValueError(tr('Tunnel installation failed. See docs/tunnel.md.'))
            else:
                raise ValueError(tr('Moodle configuration kept. Install tunnel-client and run setup again.'))
        identifier = ask(tr('Tunnel ID'), old.get('tunnel_id', ''), tunnel_id)
        init_tunnel(identifier)
        private_json(CONFIG, {'campus_url': base, 'mode': mode, 'tunnel_id': identifier})
        key = getpass.getpass(tr('OpenAI runtime key (hidden, Enter to keep the existing key): ')).strip()
        if key:
            if yes(tr('Save the key on this machine (private 600 file, required for the VPS service)?'), mode == 'vps'):
                private_json(RUNTIME, {'api_key': key})
            else:
                # An older persisted key must not silently win over the new key next time.
                RUNTIME.unlink(missing_ok=True)
                print(tr('Key not saved. You will be prompted when starting the tunnel.'))
        if mode == 'vps' and yes(tr('Install the systemd user service?')):
            install_service()
    print(tr('\n✓ Setup complete. Next steps:'))
    print(tr('  python3 moodle.py doctor       # local MCP check, without reading Moodle'))
    print(tr('  python3 moodle.py courses      # check your courses after signing in'))
    print(tr('  python3 moodle.py tunnel run   # start the configured tunnel'))
    print(tr('  Documentation: https://edouaz.github.io/moodle-mcp/guide.html'))
    return 0


def main():
    os.umask(0o077)
    # Accept --lang before or after the subcommand, and propagate it to children.
    language_parser = argparse.ArgumentParser(add_help=False)
    language_parser.add_argument('--lang', choices=SUPPORTED)
    locale_args, remaining = language_parser.parse_known_args()
    if locale_args.lang:
        os.environ['MOODLE_MCP_LANG'] = locale_args.lang
    sys.argv[1:] = remaining
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lang', choices=SUPPORTED, help='Interface language: en (default) or fr')
    commands = parser.add_subparsers(dest='command', required=True)
    wizard = commands.add_parser('setup', help=tr('Guided setup'))
    wizard.add_argument('--vps', action='store_true')
    for name in ('login', 'doctor', 'serve', 'install-service'):
        commands.add_parser(name)
    transport = commands.add_parser('tunnel')
    transport.add_argument('action', choices=['run', 'doctor', 'status'])
    # Keep the existing, tested targeted parser as the single source of CLI options.
    if len(sys.argv) > 1 and sys.argv[1] in ('session', 'courses', 'files', 'search', 'download'):
        return run_script('targeted.py', *sys.argv[1:])
    for name in ('session', 'courses', 'files', 'search', 'download'):
        commands.add_parser(name, add_help=False, help=tr('See python3 targeted.py --help'))
    args = parser.parse_args()
    if args.command == 'setup':
        return setup(args.vps)
    if args.command == 'tunnel':
        return tunnel(args.action)
    if args.command == 'install-service':
        install_service()
        return 0
    return run_script({'login': 'scraper.py', 'doctor': 'diagnose_mcp.py', 'serve': 'mcp_server.py'}[args.command],
                      *(['--login-only'] if args.command == 'login' else []))


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (KeyboardInterrupt, EOFError):
        print(tr('\nInterrupted. Run the command again to continue.'), file=sys.stderr)
        sys.exit(130)
    except json.JSONDecodeError:
        print(tr('Invalid JSON configuration. Fix the private files or run setup again.'), file=sys.stderr)
        sys.exit(1)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except (OSError, subprocess.SubprocessError):
        # Do not print exceptions from tunnel subprocesses or malformed secret files.
        print(tr('Command failed. Check your configuration, dependencies and docs/troubleshooting.md.'), file=sys.stderr)
        sys.exit(1)
