# Contribuer

Les corrections, adaptations à d’autres thèmes Moodle et améliorations de documentation sont bienvenues. Décrivez l’établissement et le thème sans publier de données personnelles. Proposez des fixtures synthétiques pour les tests.

Installez le projet avec `bash setup.sh` (vous pouvez passer connexion et tunnel), puis lancez :

```bash
.venv/bin/python -m unittest -v test_login_only test_targeted test_service test_mcp test_delivery test_sync_mac test_setup
.venv/bin/python diagnose_mcp.py
```

Les tests sont hors ligne et ne nécessitent aucun secret. Le diagnostic teste réellement le transport stdio ; il ne valide pas une connexion ChatGPT. `diagnose_mcp.py --live` est un ancien diagnostic propre à un cours d’exemple, à adapter avant toute utilisation ; ne l’exécutez pas en CI.

Gardez les changements ciblés. Toute nouvelle donnée d’exécution doit rester exclue de Git. N’utilisez jamais `git add -f` pour les sessions, cours ou clés. Le site est statique dans `docs/` : aucun bundler, CDN ou service tiers n’est requis. Vérifiez ses liens et son affichage sur mobile avant une modification de présentation.

Vos contributions sont distribuées sous la licence MIT du projet.
