[English](../../README.md) · **Français**

<p align="center"><img src="../assets/logo.svg" width="112" alt="Moodle MCP, une petite page coiffée d’un mortier orange"></p>
<h1 align="center">Moodle MCP</h1>
<p align="center"><strong>Moins de clics. Plus de cours. 🎓</strong><br>Vos ressources Moodle dans votre assistant, avec une session qui reste chez vous.</p>
<p align="center"><a href="https://edouaz.github.io/moodle-mcp/fr/">Le site</a> · <a href="https://edouaz.github.io/moodle-mcp/fr/guide.html">Guide de démarrage</a> · <a href="vps.md">Installation VPS</a></p>
<p align="center"><a href="https://github.com/edouaz/moodle-mcp/actions/workflows/ci.yml"><img src="https://github.com/edouaz/moodle-mcp/actions/workflows/ci.yml/badge.svg" alt="Tests"></a> <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB" alt="Python 3.11+"> <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-orange" alt="Licence MIT"></a></p>

Moodle MCP utilise un vrai navigateur pour accéder à vos cours, même lorsque l’API mobile de l’université est désactivée. Connectez-vous vous-même via le SSO/MFA de votre établissement ; le serveur MCP et la CLI réutilisent cette session pour lister, rechercher et télécharger les ressources choisies.

## ✨ Ce que vous pouvez faire

- Retrouver vos cours et rechercher un support par son nom.
- Télécharger un fichier précis, sans collecter tous les cours.
- Lire jusqu’à 12 000 caractères de texte d’un PDF dans votre assistant.
- Faire fonctionner le serveur sur votre Mac, un ordinateur Linux ou un VPS.
- Recevoir les fichiers d’un VPS sur votre Mac avec le client SSH optionnel.

Aucun outil ne modifie Moodle ni ne soumet de devoir. Le serveur reste privé : transport stdio en local, ou tunnel OpenAI sortant pour les clients compatibles.

## 🚀 Démarrage

**Prérequis :** Git, Python 3.11+ et macOS ou Linux. Windows : utiliser WSL2 avec un affichage graphique fonctionnel. Pour un VPS, Ubuntu 24.04 ou Debian 12+ avec systemd sont les chemins documentés.

```bash
git clone https://github.com/edouaz/moodle-mcp.git
cd moodle-mcp
bash setup.sh --lang fr
```

L’assistant installe les dépendances et Chromium, puis vous guide :

1. URL **racine** de votre Moodle, par exemple `https://campus.example.edu/moodle`.
2. Installation locale ou VPS.
3. Connexion dans le navigateur de l’université, avec votre SSO/MFA.
4. Tunnel OpenAI optionnel : identifiant, clé runtime masquée et conservation locale au choix.

**Aucun token Moodle n’est nécessaire.** La clé demandée concerne uniquement le tunnel OpenAI. Vous pouvez passer cette étape pour utiliser la CLI ou un client MCP stdio.

Sur VPS : `bash setup.sh --vps` installe aussi les dépendances système de Chromium et peut demander `sudo`. La connexion Moodle exige un affichage sécurisé ; voir le [guide VPS](vps.md) avant de commencer sur une machine sans écran.

## 🧭 Au quotidien

```bash
python3 moodle.py login          # connexion ou renouvellement de la session
python3 moodle.py doctor         # vérifie le protocole MCP, sans lire vos cours
python3 moodle.py session        # vérifie la session Moodle
python3 moodle.py courses        # liste vos cours, sans téléchargement
python3 moodle.py files --course 123 --limit 50
python3 moodle.py search --course 123 "TP1"
python3 moodle.py download --course 123 --file-id "IDENTIFIANT_RETOURNE_PAR_LA_LISTE" --include-text
python3 moodle.py tunnel run     # reste au premier plan ; Ctrl-C pour arrêter
```

Remplacez `123` et l’identifiant de fichier par les valeurs obtenues dans les listes. La CLI utilise automatiquement le Python de `.venv`. Le script historique `scraper.py` **sans option télécharge tous les cours** ; utilisez `moodle.py` pour les opérations ciblées.

## 💬 Brancher votre assistant

Pour un client MCP local, configurez la commande absolue `…/moodle-mcp/.venv/bin/python` avec l’argument absolu `…/moodle-mcp/mcp_server.py`. Exemple complet dans le [guide local](local.md).

Pour un client OpenAI compatible : créez un tunnel dans [OpenAI Platform](https://platform.openai.com/settings/organization/tunnels), configurez-le dans l’assistant CLI puis lancez `python3 moodle.py tunnel run`. Ajoutez une connexion MCP de type **Tunnel** dans votre client, si votre compte/espace le permet. L’accès et les permissions du tunnel sont requis ; l’installation du projet ne les crée pas automatiquement. Voir le [guide tunnel](tunnel.md) et la [documentation officielle OpenAI](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).

Essayez : « Liste mes cours », puis « Cherche le TP1 dans ce cours ». La connexion est validée après un appel réussi depuis votre assistant ; le diagnostic local ne vérifie pas cet accès.

## 🔒 Votre session reste personnelle

`session.json`, `.moodle/`, `.tunnel/`, les téléchargements et les files de livraison sont exclus de Git par une liste explicite de sources publiables. La session et les clés enregistrées ont des permissions `600`.

Le tunnel donne accès à **votre session Moodle** à toute personne autorisée à l’utiliser. Gardez-le personnel. Le texte extrait d’un PDF sélectionné est envoyé à votre assistant ; le PDF complet n’est pas une pièce jointe automatique. Les fichiers sont limités à 20 Mio par téléchargement ciblé. Le client Mac est optionnel et réservé à macOS.

Le fonctionnement dépend du thème et de la configuration Moodle. Les autres universités doivent être vérifiées ; SSO/MFA et accès au compte ne sont jamais contournés.

## 📚 Documentation

| Besoin | Guide |
| --- | --- |
| Installation locale et client MCP | [Local](local.md) |
| Serveur permanent, SSO sur VPS et service | [VPS](vps.md) |
| Tunnel et clé runtime | [Tunnel OpenAI](tunnel.md) |
| Recevoir les fichiers sur Mac | [Synchronisation SSH](mac-sync.md) |
| Commandes et sept outils MCP | [Référence](reference.md) |
| Reconnexion, erreurs et désinstallation | [Dépannage](troubleshooting.md) |

## 🛠️ Contribuer

```bash
.venv/bin/python -m unittest -v test_login_only test_targeted test_service test_mcp test_delivery test_sync_mac test_setup
.venv/bin/python diagnose_mcp.py
```

Ces tests n’ont besoin ni de compte Moodle ni de clé OpenAI. Voir [CONTRIBUTING.md](../../CONTRIBUTING.md), la [politique de sécurité](../../SECURITY.md) et le [journal des changements](../../CHANGELOG.md).

## Licence et crédits

[MIT](../../LICENSE). Basé sur [moodle-browser-scraper](https://github.com/thntx/moodle-browser-scraper) de thntx ; son copyright et son [README d’origine](../../README_UPSTREAM.md) sont conservés. Moodle MCP est un projet indépendant, sans affiliation avec Moodle, Apple, OpenAI ou une université. Le logo est une création vectorielle propre au projet.

## Langue du CLI

Le CLI est en anglais par défaut. Utilisez `--lang fr` ou `MOODLE_MCP_LANG=fr` pour le français. [Guide des traductions](../translating.md).
