"""Install the official tunnel-client release, verifying GitHub's SHA-256 digest."""
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import tempfile
import urllib.request
import zipfile


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'moodle-mcp-setup'})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def main():
    system = {'Linux': 'linux', 'Darwin': 'darwin'}.get(platform.system())
    architecture = {'x86_64': 'amd64', 'aarch64': 'arm64', 'arm64': 'arm64'}.get(platform.machine())
    if not system or not architecture:
        raise ValueError('macOS/Linux amd64 et arm64 uniquement. Voir les releases officielles.')
    release = json.loads(fetch('https://api.github.com/repos/openai/tunnel-client/releases/latest'))
    name = f"tunnel-client-{release['tag_name']}-{system}-{architecture}.zip"
    asset = next((a for a in release['assets'] if a['name'] == name), None)
    if not asset:
        raise ValueError('Aucun binaire pour cette plateforme dans la release officielle.')
    url = asset['browser_download_url']
    if not url.startswith('https://github.com/openai/tunnel-client/releases/download/'):
        raise ValueError('URL de release inattendue.')
    archive = fetch(url)
    if asset.get('digest') != 'sha256:' + hashlib.sha256(archive).hexdigest():
        raise ValueError('Empreinte SHA-256 absente ou incorrecte : installation refusee.')
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        binary = bundle.read('tunnel-client')
    destination = Path.home() / '.local/bin/tunnel-client'
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as output:
        temporary = Path(output.name)
        output.write(binary)
    try:
        temporary.chmod(0o700)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Client officiel {release['tag_name']} installe dans {destination}")


if __name__ == '__main__':
    os.umask(0o077)
    try:
        main()
    except Exception:
        raise SystemExit('Installation echouee. Voir https://github.com/openai/tunnel-client/releases/latest')
