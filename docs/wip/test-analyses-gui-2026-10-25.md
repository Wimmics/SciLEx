# Test réel du pipeline Analyses (GUI) — 2026-10-25

Base : `dev` @ c0e240e7 (worktree, sans le travail non commité d'une autre session).
Méthode : simulateur NiceGUI (`user_simulation`) sur une copie de la revue `~/Memory` (500 articles),
vrais appels réseau, `keys.yml` réel (sans clé Semantic Scholar). Onglets dans l'ordre :
Charts → Citations (limit 60) → Snowball (dry run puis réel) → Graph (both) → Keywords → Summaries → HuggingFace (dry run, limit 15).

## OK
- Prérequis : Snowball/Graph/Keywords/Summaries désactivés avec le bon message au départ, levés après Citations/Graph.
- Charts 1 s (6 images affichées) ; Citations 742 s pour 60 articles, 2 caches ; Snowball dry run 200 candidats ;
  Graph both (4 fichiers) ; Keywords 30 suggestions ; Summaries écrit ; HF dry run termine.

## Défauts trouvés
1. **DOI non normalisés en casse** (`snowball/candidates.py`, `graph_analysis/graphs.py`) : `10.9/X` et `10.9/x`
   comptés séparément (fréquences divisées, liens de couplage perdus) et un article du corpus cité en majuscules
   est proposé comme candidat Snowball. Vu dans les vraies données (`10.18653/V1/2021.NAACL-MAIN.45`).
2. **Snowball sans clé : 429 avalé** (`snowball/fetcher.py:131`, pas de retry) → message « No paper passed the
   quality filters » alors que 0 métadonnée n'a été récupérée.
3. **Summaries : aucun mot-clé par cluster** (`summarize/stats.py:82` cherche `tags/keywords/keyword`, le CSV a
   `collect_keywords`/`bonus_keyword_tags`) → mindmap « Cluster 0: Cluster 0 » ×468.
4. Summaries : 468 « communautés » dont ~460 singletons listées dans le rapport (141 Ko) ; filtrer taille 1.
5. **HF avec `limit`** : progression et message sur le total du CSV (« 13/500 », « 2 of 500 papers matched »
   pour 15 traités) (`enrichment_hf.py:277,321,408`).
6. `scipy` absent des dépendances : Graph retombe sur la centralité de degré (aussi dans l'app packagée).
7. Citations : progression mise à jour par lot de 20 seulement (~2 min sans changement) — corrigé par le travail
   en cours sur `reference_fetcher.py` (progression par article).
8. Keywords : en-tête « Suggested keywords for scilex.config.yml » (nom legacy) ; suggestions bruitées
   (« term memory », « models knowledge », « graphs large », pluriel de mots-clés existants).
9. Keywords/Summaries prennent toujours `clusters_cocitation.csv` quand Graph = both, sans choix dans l'UI.

## Prochaine étape
Corriger 1-5 (+ tests), puis 6, 8, 9 selon arbitrage.
