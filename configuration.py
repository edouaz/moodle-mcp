"""Small, dependency-free configuration shared by every entry point."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / '.moodle' / 'config.json'
RUNTIME = ROOT / '.tunnel' / 'runtime.json'


def read_json(path):
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def private_json(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def campus_url(value):
    value = value.strip()
    parts = urlsplit(value)
    if (parts.scheme != 'https' or not parts.hostname or parts.username is not None
            or parts.password is not None or parts.query or parts.fragment):
        raise ValueError('Utilisez une URL HTTPS sans identifiants, parametres ni fragment.')
    if any(c.isspace() or ord(c) < 32 for c in value) or '\\' in value:
        raise ValueError('URL Moodle invalide.')
    # Force validation of the optional port as well.
    parts.port
    return urlunsplit(parts._replace(path=parts.path.rstrip('/')))


def campus_base():
    return campus_url(os.environ.get('CAMPUS_BASE') or read_json(CONFIG).get(
        'campus_url', 'https://moodle.uclouvain.be'))
