#!/usr/bin/env python3
"""Moodle MCP: guided setup and daily commands, on macOS and Linux."""
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
                raise ValueError('Une valeur est requise.')
            return validate(value) if validate else value
        except ValueError as exc:
            print(exc)


def yes(label, default=False):
    return input(f'{label} [{"O/n" if default else "o/N"}] : ').strip().lower() in (
        ('', 'o', 'oui', 'y', 'yes') if default else ('o', 'oui', 'y', 'yes'))


def tunnel_binary():
    candidate = shutil.which('tunnel-client')
    fallback = Path.home() / '.local/bin/tunnel-client'
    if not candidate and fallback.is_file():
        candidate = str(fallback)
    if not candidate:
        raise ValueError('tunnel-client absent. Lancez python3 install_tunnel.py ou relancez le setup.')
    return candidate


def tunnel_id(value):
    if not re.fullmatch(r'tunnel_([a-z0-9]{4}_)?[a-z0-9]{32}', value):
        raise ValueError('Collez le vrai tunnel_id retourne par OpenAI Platform (tunnel_…).')
    return value


def init_tunnel(identifier):
    command = [tunnel_binary(), 'init', '--sample', 'sample_mcp_stdio_local',
               '--profile', 'moodle', '--profile-dir', str(ROOT / '.tunnel'),
               '--tunnel-id', tunnel_id(identifier), '--control-plane-api-key-ref',
               'env:CONTROL_PLANE_API_KEY', '--health-listen-addr', '127.0.0.1:8789',
               '--mcp-command', shlex.join([python(), str(ROOT / 'mcp_server.py')])]
    if (ROOT / '.tunnel/moodle.yaml').exists():
        if not yes('Remplacer le profil tunnel existant ?'):
            raise ValueError('Profil conserve. Relancez le setup pour le modifier.')
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
        raise ValueError('Configurez le tunnel avec python3 moodle.py setup.')
    env = os.environ.copy()
    env['CONTROL_PLANE_API_KEY'] = env.get('CONTROL_PLANE_API_KEY') or read_json(RUNTIME).get('api_key', '')
    if not env['CONTROL_PLANE_API_KEY']:
        if not sys.stdin.isatty():
            raise ValueError('Cle runtime absente. Relancez le setup depuis un terminal.')
        env['CONTROL_PLANE_API_KEY'] = getpass.getpass('Cle runtime OpenAI (masquee) : ').strip()
    if not env['CONTROL_PLANE_API_KEY']:
        raise ValueError('Cle runtime absente.')
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
        raise ValueError('Le service utilisateur exige Linux avec systemd.')
    if not read_json(RUNTIME).get('api_key') and not os.environ.get('CONTROL_PLANE_API_KEY'):
        raise ValueError('Enregistrez la cle runtime dans le setup avant d’installer le service.')
    if not read_json(RUNTIME).get('api_key'):
        raise ValueError('Une cle dans le terminal ne persiste pas dans systemd. Relancez setup et enregistrez-la.')
    if not (ROOT / '.tunnel/moodle.yaml').exists():
        raise ValueError('Configurez d’abord le tunnel avec setup.')
    destination = Path.home() / '.config/systemd/user/moodle-tunnel.service'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(service_file())
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', '--user', 'enable', 'moodle-tunnel.service'], check=True)
    print('Service installe et active au prochain demarrage de la session utilisateur.')
    print('Apres connexion Moodle : systemctl --user start moodle-tunnel')
    print('Pour demarrer au boot sans session SSH : sudo loginctl enable-linger "$USER"')


def setup(vps=False):
    if os.name != 'posix':
        raise ValueError('Utilisez macOS, Linux ou WSL2 (voir documentation).')
    print('\n🎓 Moodle MCP · Bienvenue !\nVos cours, votre session, votre machine.\n')
    old = read_json(CONFIG)
    base = ask('1/4 · URL racine Moodle (ex. https://moodle.universite.fr)', old.get('campus_url', ''), campus_url)
    if old.get('campus_url', 'https://moodle.uclouvain.be') != base and (ROOT / 'session.json').exists():
        raise ValueError('Universite differente : supprimez explicitement session.json avant de changer l’URL.')
    mode = ask('2/4 · Installation : local ou vps', 'vps' if vps else old.get('mode', 'local'),
               lambda x: x if x in ('local', 'vps') else (_ for _ in ()).throw(ValueError('Choisissez local ou vps.')))
    private_json(CONFIG, {'campus_url': base, 'mode': mode})
    print('Configuration enregistree. Aucun mot de passe universitaire ne sera demande ici.')
    print('\n3/4 · Connexion Moodle : le navigateur gere votre SSO et votre MFA.')
    if mode == 'vps' and not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
        print('VPS sans affichage : voir docs/vps.md pour une connexion graphique securisee.')
        print('Puis lancez : python3 moodle.py login')
    elif yes('Ouvrir le navigateur pour se connecter maintenant ?', True):
        if run_script('scraper.py', '--login-only'):
            raise ValueError('Connexion interrompue. Reessayez avec python3 moodle.py login.')
    print('\n4/4 · Tunnel prive OpenAI (facultatif pour une CLI ou un client MCP stdio).')
    if yes('Configurer le tunnel ?', True):
        print('Creez votre tunnel : https://platform.openai.com/settings/organization/tunnels')
        print('Cle runtime de la meme organisation : https://platform.openai.com/settings/organization/api-keys')
        print('Acces personnel uniquement : toute personne autorisee sur le tunnel utilise votre session Moodle.')
        try:
            tunnel_binary()
        except ValueError:
            if yes('Installer le client officiel tunnel-client ?', True):
                if run_script('install_tunnel.py'):
                    raise ValueError('Installation du tunnel echouee. Voir docs/tunnel.md.')
            else:
                raise ValueError('Configuration Moodle conservee. Installez tunnel-client puis relancez setup.')
        identifier = ask('Identifiant du tunnel', old.get('tunnel_id', ''), tunnel_id)
        init_tunnel(identifier)
        private_json(CONFIG, {'campus_url': base, 'mode': mode, 'tunnel_id': identifier})
        key = getpass.getpass('Cle runtime OpenAI (masquee, Entree pour garder la cle existante) : ').strip()
        if key:
            if yes('Conserver la cle sur cette machine (fichier prive 600, necessaire au service VPS) ?', mode == 'vps'):
                private_json(RUNTIME, {'api_key': key})
            else:
                # An older persisted key must not silently win over the new key next time.
                RUNTIME.unlink(missing_ok=True)
                print('Cle non conservee. Elle sera redemandee au lancement du tunnel.')
        if mode == 'vps' and yes('Installer le service systemd utilisateur ?'):
            install_service()
    print('\n✓ Setup termine. Prochaines etapes :')
    print('  python3 moodle.py doctor       # diagnostic MCP local, sans lire Moodle')
    print('  python3 moodle.py courses      # verifier vos cours apres connexion')
    print('  python3 moodle.py tunnel run   # lancer le tunnel configure')
    print('  Documentation : https://edouaz.github.io/moodle-mcp/guide.html')
    return 0


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    wizard = commands.add_parser('setup', help='Assistant de configuration')
    wizard.add_argument('--vps', action='store_true')
    for name in ('login', 'doctor', 'serve', 'install-service'):
        commands.add_parser(name)
    transport = commands.add_parser('tunnel')
    transport.add_argument('action', choices=['run', 'doctor', 'status'])
    # Keep the existing, tested targeted parser as the single source of CLI options.
    if len(sys.argv) > 1 and sys.argv[1] in ('session', 'courses', 'files', 'search', 'download'):
        return run_script('targeted.py', *sys.argv[1:])
    for name in ('session', 'courses', 'files', 'search', 'download'):
        commands.add_parser(name, add_help=False, help='Voir python3 targeted.py --help')
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
        print('\nInterrompu. Relancez la commande pour continuer.', file=sys.stderr)
        sys.exit(130)
    except json.JSONDecodeError:
        print('Configuration JSON invalide. Corrigez les fichiers prives ou relancez setup.', file=sys.stderr)
        sys.exit(1)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except (OSError, subprocess.SubprocessError):
        # Do not print exceptions from tunnel subprocesses or malformed secret files.
        print('Commande en echec. Verifiez la configuration, les dependances et docs/troubleshooting.md.', file=sys.stderr)
        sys.exit(1)
