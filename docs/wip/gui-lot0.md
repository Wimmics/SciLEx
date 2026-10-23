# WIP — GUI desktop, lot 0 (fondation)

Plan : `docs/superpowers/plans/2026-10-23-gui-lot0-foundation.md`
Branche : `feat/gui-desktop`, worktree `.claude/worktrees/gui-desktop`

## État

- [x] Étape 1 — squelette, extras `gui` (nicegui 3.18, pywebview 6.2, platformdirs) et `build` (pyinstaller 6.22)
- [x] Étape 2 — services/workspace.py
- [x] Étape 3 — services/jobs.py
- [x] Étape 4 — coquille NiceGUI
- [x] Étape 5 — --self-test
- [ ] Étape 6 — packaging PyInstaller
- [ ] Étape 7 — CI
- [ ] Étape 8 — docs, ADR 0004

## Notes

- Tests de pages : `nicegui.testing.user_simulation(root=…)` + `@pytest.mark.anyio` (plugin anyio déjà installé via httpx ; pas de pytest-asyncio).
- Création de revue : `init_templates.apply_template()` / `skeleton_text()` suffisent, pas d'extraction.

- Étape 3 : les briques partagées (états, capture de logs) sont dans `scilex/pipeline/jobs.py` (et non dans `scilex.gui`) pour que l'API web ne dépende pas de la GUI ; `webapi/scilex_api.py` garde des adaptateurs dict.
- Tests de pages : utiliser des marqueurs (`.mark(...)` + `user.find(marker=...)`) ; la recherche par contenu de NiceGUI est large et clique l'élément d'id le plus bas.
- `app.py` : garde `__name__ == "__main__"` seulement (pas `__mp_main__`, sinon chaque processus enfant relancerait l'app).
- Annulation : la collecte s'arrête à la requête suivante ; l'agrégation n'est pas interruptible (le job finit « annulé » après).

## Prochaine étape

Étape 6 (spec PyInstaller, build local macOS, self-test sur le bundle). Vérification manuelle de la fenêtre native à faire par l'utilisateur.
