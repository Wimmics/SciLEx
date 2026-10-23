# WIP — GUI desktop, lot 0 (fondation)

Plan : `docs/superpowers/plans/2026-10-23-gui-lot0-foundation.md`
Branche : `feat/gui-desktop`, worktree `.claude/worktrees/gui-desktop`

## État

- [x] Étape 1 — squelette, extras `gui` (nicegui 3.18, pywebview 6.2, platformdirs) et `build` (pyinstaller 6.22)
- [ ] Étape 2 — services/workspace.py
- [ ] Étape 3 — services/jobs.py
- [ ] Étape 4 — coquille NiceGUI
- [ ] Étape 5 — --self-test
- [ ] Étape 6 — packaging PyInstaller
- [ ] Étape 7 — CI
- [ ] Étape 8 — docs, ADR 0004

## Notes

- Tests de pages : `nicegui.testing.user_simulation(root=…)` + `@pytest.mark.anyio` (plugin anyio déjà installé via httpx ; pas de pytest-asyncio).
- Création de revue : `init_templates.apply_template()` / `skeleton_text()` suffisent, pas d'extraction.

## Prochaine étape

Étape 2.
