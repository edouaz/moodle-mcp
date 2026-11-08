[English](../vps.md) · **Français**

# Installer sur un VPS

Utilisez un compte Linux dédié sans privilèges root, Python 3.11+ et un disque persistant. Ubuntu 24.04 ou Debian 12+ avec systemd sont les bases documentées. Prévoyez de la mémoire pour Chromium ; 2 Gio est un point de départ, à adapter aux cours consultés.

## 1. Installer via le terminal

```bash
sudo apt update
sudo apt install git python3 python3-venv ca-certificates
mkdir -p ~/project
cd ~/project
git clone https://github.com/edouaz/moodle-mcp.git
cd moodle-mcp
bash setup.sh --vps --lang fr
```

Le bootstrap installe les dépendances système du navigateur (avec `sudo` si nécessaire). Choisissez `vps`, renseignez l’URL Moodle et configurez le tunnel. La clé runtime peut être enregistrée dans `.tunnel/runtime.json`, en `600`, pour permettre le redémarrage automatique.

## 2. Se connecter à Moodle sur le VPS

Le setup détecte l’absence d’affichage et reporte la connexion. Un navigateur graphique est nécessaire pour terminer le SSO/MFA. Depuis un ordinateur disposant d’un serveur X, une possibilité est le transfert X11 via SSH :

```bash
ssh -X etudiant@vps.example.org
cd ~/project/moodle-mcp
python3 moodle.py login
```

Cela nécessite un serveur X sur l’ordinateur (par exemple XQuartz sur Mac), `xauth` côté VPS et X11 forwarding autorisé par SSH. Vous pouvez aussi utiliser un bureau distant accessible uniquement par SSH. Si Chromium ne démarre pas avec votre affichage, utilisez ce bureau sécurisé et relancez `login` dans son terminal.

Connectez-vous dans le navigateur ouvert sur le VPS, puis confirmez dans le terminal. Ne supposez pas qu’une session copiée d’une autre machine/IP sera acceptée par l’université. Le projet ne contourne pas ces restrictions et n’installe pas automatiquement un bureau distant.

```bash
python3 moodle.py session
python3 moodle.py courses
python3 moodle.py doctor
python3 moodle.py tunnel doctor
```

## 3. Garder le tunnel actif

Si vous ne l’avez pas installé dans le setup :

```bash
python3 moodle.py install-service
systemctl --user start moodle-tunnel
systemctl --user status moodle-tunnel
```

Le fichier est généré avec les chemins réels du checkout dans `~/.config/systemd/user/moodle-tunnel.service`. La clé doit être enregistrée par le setup. Le service est activé, mais la commande d’installation ne le démarre pas avant la connexion Moodle.

Pour démarrer au boot sans session SSH :

```bash
sudo loginctl enable-linger "$USER"
```

Le setup ne modifie pas ce réglage système lui-même. Gestion courante :

```bash
journalctl --user -u moodle-tunnel -n 50
systemctl --user restart moodle-tunnel
systemctl --user stop moodle-tunnel
python3 moodle.py tunnel status
```

La santé écoute sur `127.0.0.1:8789`. Aucun port entrant MCP n’est à ouvrir. Le tunnel doit pouvoir joindre OpenAI en HTTPS sortant. La disponibilité de la connexion ChatGPT dépend de votre compte et de ses permissions ; [guide tunnel](tunnel.md).

## 4. Renouveler une session expirée

Arrêtez le service, connectez-vous avec l’affichage sécurisé, vérifiez, puis redémarrez :

```bash
systemctl --user stop moodle-tunnel
python3 moodle.py login
python3 moodle.py session
systemctl --user start moodle-tunnel
```

Pour recevoir les fichiers sur votre Mac, suivez le [guide SSH](mac-sync.md). Sans ce client, le téléchargement MCP reste dans la file du serveur. Un chemin sur le VPS n’est pas un fichier reçu sur votre ordinateur.

## Mise à jour

Arrêtez le service, exécutez `git pull --ff-only`, puis `bash setup.sh --vps --lang fr` pour réinstaller les dépendances et revoir la configuration. Relancez `install-service` si le chemin du projet a changé. Vérifiez les diagnostics avant de redémarrer. Conservez les fichiers privés sur un stockage protégé ; ils ne font pas partie du dépôt.

[Accueil](README.md) · [Dépannage](troubleshooting.md)
