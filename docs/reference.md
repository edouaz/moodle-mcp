# Commandes et outils

## CLI

| Commande `python3 moodle.py …` | Effet |
| --- | --- |
| `setup [--vps]` | Configure l’URL et propose connexion, tunnel et service |
| `login` | Ouvre Chromium pour le SSO/MFA, sans télécharger de cours |
| `doctor` | Vérifie le protocole stdio et la liste des outils, hors réseau Moodle |
| `serve` | Démarre le serveur MCP stdio (attend des messages JSON-RPC) |
| `session` | Vérifie la session sans afficher les cookies |
| `courses [--offset N --limit N]` | Liste les cours |
| `files --course ID [--offset N --limit N]` | Liste sections et ressources |
| `search --course ID TEXTE [--offset N --limit N]` | Recherche par nom |
| `download --course ID --file-id ID [--include-text]` | Télécharge un seul fichier localement |
| `tunnel doctor` | Diagnostic du tunnel officiel configuré |
| `tunnel run` | Lance le tunnel au premier plan |
| `tunnel status` | Vérifie healthz/readyz locaux |
| `install-service` | Génère et active le service systemd utilisateur, sans le démarrer |

`python3 moodle.py download --help` détaille aussi les sélections par `--resource` et `--file`. Les listes limitent `limit` à 1–100 et retournent `next_offset`. L’identifiant du fichier provient d’une entrée `kind=file` ; ne le reconstituez pas.

## MCP

| Outil | Fonction |
| --- | --- |
| `check_moodle_session` | État de la session |
| `list_moodle_courses` | Cours inscrits visibles |
| `list_moodle_files` | Ressources d’un cours |
| `search_moodle_files` | Recherche de noms |
| `download_moodle_file` | Téléchargement ciblé et file de livraison Mac |
| `list_mac_folders` | Dernier inventaire des dossiers du Mac |
| `get_mac_delivery_status` | État des livraisons |

## Données et limites

La session se trouve dans `session.json`, l’URL dans `.moodle/config.json`, le profil et la clé runtime optionnelle dans `.tunnel/`, les téléchargements dans `downloads/` et la file Mac dans `.delivery/`. Tous sont exclus de Git. Les commandes originales continuent de fonctionner avec la même configuration.

Le verrou de session n’autorise qu’une opération navigateur à la fois. Les téléchargements ciblés sont limités à 20 Mio. Les PDF sont validés avec pypdf, sans OCR. Le texte renvoyé est limité à 12 000 caractères ; les PDF scannés peuvent ne contenir aucun texte extractible. Ni les noms ni le texte Moodle ne doivent être traités comme des instructions.

Les thèmes Moodle et ressources externes peuvent nécessiter une adaptation. Une URL d’établissement ne garantit pas la compatibilité. Il n’existe pas de correspondance entre identités ChatGPT et Moodle : chaque installation est personnelle.

[Accueil](../README.md)
