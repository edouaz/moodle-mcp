# Dépannage

| Symptôme | Action |
| --- | --- |
| `python3` absent ou trop ancien | Installer Python 3.11+ puis relancer `bash setup.sh` |
| Échec de création du venv | Debian/Ubuntu : `sudo apt install python3-venv` |
| Chromium ou bibliothèques absents | `.venv/bin/python -m playwright install --with-deps chromium` sur Linux |
| Pas d’affichage sur VPS | Connexion via un affichage sécurisé, puis `python3 moodle.py login` ; [guide](vps.md) |
| `SESSION_EXPIRED` | Arrêter le tunnel/service, lancer `login`, vérifier `session`, puis redémarrer |
| `MOODLE_BUSY` | Attendre la fin de l’autre opération navigateur |
| Mauvaise université | Vérifier `CAMPUS_BASE` ; changer la config via `setup` après avoir retiré explicitement l’ancienne session |
| Tunnel absent ou refusé | Vérifier organisation, identifiant, clé runtime et permissions ; `python3 moodle.py tunnel doctor` |
| Port 8789 déjà utilisé | Arrêter l’autre instance du tunnel ; ne pas lancer le service et le mode premier plan ensemble |
| `HTML_INSTEAD_OF_FILE` | Reconnecter Moodle, puis sélectionner à nouveau le fichier |
| Mac : fichiers `queued` | Vérifier SSH, le LaunchAgent et les permissions de dossiers macOS |
| `systemctl --user` indisponible | Utiliser une session utilisateur systemd ; sinon lancer le tunnel au premier plan dans votre superviseur |

## Mettre à jour

Arrêtez le tunnel, puis :

```bash
git pull --ff-only
bash setup.sh
python3 moodle.py doctor
```

Sur VPS, utilisez `bash setup.sh --vps`. Le setup préserve l’URL proposée et demande avant de remplacer le profil existant. Les fichiers privés restent locaux.

## Désinstaller

Sur VPS :

```bash
systemctl --user disable --now moodle-tunnel
rm ~/.config/systemd/user/moodle-tunnel.service
systemctl --user daemon-reload
```

Sur Mac, retirez le client optionnel avec `.venv/bin/python sync_mac.py uninstall`. Révoquez le tunnel et sa clé dans OpenAI Platform si vous n’en avez plus besoin. Supprimez ensuite le checkout et ses données privées si vous le souhaitez. Les documents déjà livrés restent dans leurs dossiers de destination. Le binaire `~/.local/bin/tunnel-client` peut servir à d’autres projets : vérifiez avant de le retirer.

## Signaler un problème

Joignez la version Python, votre système et le résultat expurgé du diagnostic. Ne publiez ni cookies, ni clé, ni session, ni document de cours dans une issue. Voir [SECURITY.md](../SECURITY.md).
