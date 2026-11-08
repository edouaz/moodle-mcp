# Connecter un tunnel OpenAI

La CLI et les clients MCP stdio fonctionnent sans tunnel. Pour les produits OpenAI compatibles, le client officiel permet de joindre le serveur privé via des connexions HTTPS sortantes. [Guide officiel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).

## Préparer les accès

1. Dans [OpenAI Platform / Tunnels](https://platform.openai.com/settings/organization/tunnels), choisissez votre organisation et créez un tunnel personnel. Conservez son identifiant `tunnel_…`.
2. Vérifiez les permissions de création/gestion du tunnel, puis les droits d’utilisation pour l’opérateur et la clé runtime. L’autorisation d’ajouter une connexion dans le client est distincte.
3. Créez une [clé runtime](https://platform.openai.com/settings/organization/api-keys) dans la même organisation, avec les droits nécessaires au tunnel. N’utilisez pas de clé d’administration pour le service.

## Configurer

```bash
python3 moodle.py setup
```

L’assistant propose d’installer le client officiel s’il manque. L’installateur vérifie le SHA-256 publié pour l’archive avant de remplacer le binaire dans `~/.local/bin/tunnel-client`. Vous pouvez aussi installer le client depuis ses [releases officielles](https://github.com/openai/tunnel-client/releases/latest).

Saisissez l’identifiant puis la clé dans l’invite masquée. Le profil `.tunnel/moodle.yaml` contient une référence `env:CONTROL_PLANE_API_KEY`. La clé est soit redemandée au démarrage, soit conservée dans `.tunnel/runtime.json` en `600`, si vous l’acceptez. Une variable `CONTROL_PLANE_API_KEY` existante a priorité sur le fichier enregistré.

```bash
python3 moodle.py tunnel doctor
python3 moodle.py tunnel run
```

Le tunnel reste au premier plan. Arrêt : Ctrl-C. Dans un autre terminal : `python3 moodle.py tunnel status`. Le port 8789 reste sur la boucle locale.

## Ajouter la connexion

Dans votre produit OpenAI compatible, ouvrez l’ajout de serveur MCP, choisissez **Tunnel** et sélectionnez le tunnel configuré. Dans ChatGPT, l’emplacement et la disponibilité de l’ajout de MCP personnalisé dépendent de votre compte et de votre espace. Consultez le [guide officiel d’ajout](https://developers.openai.com/api/docs/guides/custom-mcp-server).

Le serveur n’ajoute pas d’authentification applicative : le contrôle d’accès repose sur le tunnel et la connexion personnelle. Toute personne autorisée à l’utiliser accède à votre session universitaire. Ne partagez pas le tunnel ni la connexion dans un espace collectif.

Vérifiez les sept outils puis demandez de lister vos cours. Un résultat réussi depuis votre assistant valide cette connexion. Le diagnostic stdio local ne la prouve pas.

## Renouveler une clé

Arrêtez le service/tunnel, relancez `setup` et saisissez la nouvelle clé. Si vous refusez de la conserver, l’ancienne clé enregistrée est retirée. Si vous laissez la saisie vide, la clé existante reste en place. Relancez le diagnostic puis le service.

[Accueil](../README.md) · [VPS](vps.md)
