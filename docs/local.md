# Installation locale

## Préparer

Installez Git et Python 3.11+ (macOS ou Linux), puis :

```bash
git clone https://github.com/edouaz/moodle-mcp.git
cd moodle-mcp
bash setup.sh
```

Le bootstrap crée `.venv`, installe `requirements.txt` et Chromium, puis ouvre l’assistant. Sur Debian/Ubuntu, installez `python3-venv` si nécessaire. Si Chromium signale des bibliothèques manquantes sous Linux :

```bash
.venv/bin/python -m playwright install --with-deps chromium
```

Entrez l’URL racine de Moodle, en conservant un éventuel sous-dossier `/moodle`. N’entrez pas `/login/index.php` ou l’URL d’un cours. Choisissez `local`. Dans Chromium, terminez la connexion universitaire, affichez la liste de vos cours et revenez au terminal pour appuyer sur Entrée. Aucun mot de passe n’est lu par le setup.

Choisissez ensuite le tunnel ou passez cette étape. La configuration se trouve dans `.moodle/config.json`. `CAMPUS_BASE` peut remplacer l’URL pour un processus ; évitez de le laisser défini si vous souhaitez utiliser l’URL du setup.

## Vérifier

```bash
python3 moodle.py doctor
python3 moodle.py session
python3 moodle.py courses
```

Le premier vérifie le serveur MCP sans interroger Moodle. Les suivants utilisent votre session. `next_offset` indique la page suivante : transmettez-le avec `--offset`.

## Client MCP local

Dans la configuration de votre client, adaptez les chemins absolus :

```json
{
  "mcpServers": {
    "moodle": {
      "command": "/absolute/path/to/moodle-mcp/.venv/bin/python",
      "args": ["/absolute/path/to/moodle-mcp/mcp_server.py"]
    }
  }
}
```

La forme exacte du fichier dépend du client. Le serveur lit l’URL enregistrée même si le client démarre depuis un autre répertoire. Aucun tunnel ni clé OpenAI n’est nécessaire pour stdio.

## Windows

Le verrouillage de session utilise `fcntl` : Windows natif n’est pas pris en charge. Utilisez WSL2 avec Python et WSLg ou un affichage équivalent, et installez le projet dans le système de fichiers Linux. Ce chemin n’a pas été validé sur cette machine ; macOS/Linux sont les cibles principales.

[Accueil](../README.md) · [VPS](vps.md) · [Dépannage](troubleshooting.md)
