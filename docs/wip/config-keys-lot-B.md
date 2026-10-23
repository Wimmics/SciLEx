# Clés de configuration du lot B

Lues via `config.get(clé, DEFAULT_<CLÉ>)` ; absentes de `QUALITY_FILTER_SCHEMA`.

| Clé | Type | Défaut | Rôle | Section suggérée |
|-----|------|--------|------|------------------|
| `generate_prisma_report` | bool | `true` | Écrit `prisma_report.md` (PRISMA 2020 + Mermaid) à la fin de `scilex-aggregate` (#49) | `output` / `aggregation` |
