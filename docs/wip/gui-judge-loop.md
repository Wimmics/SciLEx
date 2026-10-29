# Boucle juge GUI — 2026-10-29

Mandat : boucle juge → corrections sur la GUI seule, au moins 10 itérations, arrêt quand le juge
ne trouve plus rien de majeur. Tout en local (aucun push), commits sur `dev`.

Majeur = bug, perte de données, utilisateur bloqué, ou résultat scientifiquement faux. Le reste est mineur.

## Méthode
- Juge = agent neuf à chaque itération ; il lance l'appli réelle (`scilex-gui --browser --no-open --port 8765`)
  avec un HOME isolé (registre neuf, pas de keys.yml) et une copie de `~/Memory` comme revue de démo,
  et la pilote avec Playwright headless (`uvx --from playwright python`).
- Script de lancement : `<scratchpad>/judge/start_gui.sh` (redémarre sur le code courant).

## Itérations
(voir ci-dessous, une section par itération : remarques majeures, corrections, commits)
