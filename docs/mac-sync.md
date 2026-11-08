# Recevoir les fichiers sur Mac

Le MCP met les téléchargements en attente dans `.delivery/` sur le serveur. Le client macOS récupère les fichiers via SSH, vérifie le SHA-256 et confirme leur réception. Le serveur nettoie ensuite les copies livrées. Ce client est optionnel ; la CLI `moodle.py download` télécharge localement sans utiliser cette file.

## Préparer SSH

Configurez une clé SSH vers votre serveur et effectuez une première connexion interactive pour vérifier son empreinte :

```bash
ssh etudiant@vps.example.org
```

Le client refuse les hôtes inconnus et fonctionne sans invite de mot de passe. Un alias dans `~/.ssh/config` peut simplifier le nom d’hôte. Le compte SSH doit accéder au checkout et à son répertoire `.delivery/`. Python 3.11+ doit être disponible via `python3` sur le serveur.

## Installer sur le Mac

Clonez le projet et créez un environnement Python comme décrit dans le [guide local](local.md). Il n’est pas nécessaire de configurer une deuxième session Moodle ni un deuxième tunnel. Dans le checkout du Mac :

```bash
.venv/bin/python sync_mac.py install \
  --host etudiant@vps.example.org \
  --remote-path project/moodle-mcp/downloads
```

`--remote-path` est le chemin des téléchargements sur le serveur, relatif au dossier personnel SSH ou absolu. Le helper `delivery.py` doit être dans son dossier parent. Adaptez-le si votre checkout est ailleurs. Le client teste une première synchronisation puis installe un LaunchAgent toutes les 30 secondes.

Le MCP peut choisir `Documents`, `Desktop` ou `Downloads`, puis un sous-dossier relatif. Le dépôt par défaut est `~/Downloads/Moodle/NOM.pdf`. Les doublons différents reçoivent un suffixe ; les chemins absolus et traversées de répertoires sont refusés. macOS peut demander l’accès aux dossiers concernés.

```bash
.venv/bin/python sync_mac.py status
.venv/bin/python sync_mac.py once --host etudiant@vps.example.org --remote-path project/moodle-mcp/downloads
.venv/bin/python sync_mac.py uninstall
```

L’ancien label LaunchAgent `fr.edouard.moodle-downloads` est conservé pour permettre les mises à jour. Ses journaux se trouvent dans `~/Library/Logs/fr.edouard.moodle-downloads.log`.

Seuls les noms de dossiers Documents/Desktop/Downloads sont publiés dans l’inventaire, jamais le contenu des documents. Le snapshot peut être ancien ou partiel. Seul `get_mac_delivery_status` avec `delivered` confirme la réception. Un Mac éteint conserve les fichiers en attente côté VPS.

[Accueil](../README.md) · [Référence](reference.md)
