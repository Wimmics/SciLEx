---
title: 'SciLEx'
tags:
  - Python
  - scientific literature
  - literature research
  - paper retrival
authors:
  - name: Célian Ringwald
    orcid: 0000-0002-7302-9037
    affiliation: 1
  - name: Benjamin Navet
    orcid: 0000-0001-6643-431X
    affiliation: 1
affiliations:
 - name: INRIA, 3IA, CNRS, I3S, Université Côte d'Azur
   index: 1
 - name: Institut de Chimie de Nice (ICN/CNRS UMR7272)
   index: 2
date: 29 January 2025
bibliography: paper.bib

---
# Summary

SciLEx (Science Literature Exploration) is an open-source Python toolkit designed to support systematic literature reviews in research and academic contexts. Given one or two groups of keywords — which are combined with Boolean AND logic to form precise, compound queries — SciLEx concurrently collects papers from up to ten academic APIs: SemanticScholar, OpenAlex, IEEE, Arxiv, Springer, Elsevier, HAL, DBLP, Istex, and PubMed. The tool then deduplicates results across sources using DOI matching, URL matching, and fuzzy title comparison, ensuring that the same paper retrieved from multiple APIs is merged rather than counted multiple times. Beyond collection, SciLEx runs a configurable multi-stage filtering pipeline that scores papers on metadata completeness, enforces time-aware citation thresholds, and ranks results by a composite relevance score, reducing hundreds of thousands of raw results to a curated final set. It also extracts citation networks via OpenCitations[@peroni_opencitations_2020] and Semantic Scholar, and optionally enriches papers with HuggingFace metadata (linked models, datasets, and GitHub statistics), making it particularly useful for AI and machine learning literature reviews. Final outputs can be exported to BibTeX or pushed directly to a Zotero[@mueen_ahmed_zotero_2011] collection. All operations are idempotent: interrupted or repeated runs automatically skip already-completed queries, making SciLEx robust for use on standard personal hardware.

# Statement of need

Face to the important publication production growth [@10.1162/qss_a_00327], Researchers initiating a new project or conducting a systematic review[@kitchenham2007guidelines] must survey a large and fragmented literature spread across disciplinary databases with incompatible formats and access policies. Existing reference managers such as Zotero provide manual search interfaces and import functionality, but do not automate multi-API retrieval, cross-source deduplication, or quality-based filtering. SciLEx fills this gap by providing a fully automated, configurable, and locally executable pipeline that takes keyword inputs and produces a ranked, deduplicated, and enriched bibliography — requiring no subscription and no cloud dependency. It is designed for researchers and graduate students who need to efficiently scope a new research area or assemble a reproducible literature corpus.

SciLEx enriches the resulting corpus through the integration with external services such as [PaperWithCode](https://paperswithcode.com) (available until may 2025) now redirects to Hugging Face, CrossRef[@hendricks_crossref_2020], and Opencitation[@peroni_opencitations_2020]. PaperWithCode, was intended for the Machine Learning community and aimed at connecting research articles to their corresponding methods, implemented code, evaluation results on standard datasets, and initial paper annotations. OpenCitation enables the retrieval of citations and references for a given paper, which can be used both to filter papers by impact and to expand the corpus through citation snowballing.
Finally, SciLEx exports all gathered information into a Zotero collection, facilitating collaborative management, selection, and annotation of the corpus.

### Key Features
[SCHEMA]

- Multi-API collection with parallel processing (PubMed, SemanticScholar, OpenAlex, IEEE, Arxiv, Springer, HAL, DBLP, Istex, PubMed)
- Complex queries requests: two options only use a list of keywords (that will create a query per keyword) or the definition of two keywords list that will be used to combine one by one each keyword of both list, and implictly allowing the define queries integrating both the logical OR and the logical AND
- Smart deduplication using DOI and title matching
- Citation network extraction via OpenCitations + Semantic Scholar with SQLite caching
- Quality filtering pipeline integrating:
   * time-aware citation thresholds
   * relevance ranking (based on keywords list and potential additionnal "bonus keywords"
   * itemType filtering
- HuggingFace enrichment (NEW): Extract ML models, datasets, GitHub stats, and AI keywords
- Bulk Zotero upload in batches of 50 items
- Idempotent collections for safe re-runs (automatically skips completed queries)
- BibTex extraction

# Software design

Scilex is mainly based on a pipeline approach: 
API Collection → Deduplication → ItemType Filter → Keyword Filter → Quality Filter → Citation Filter → Relevance Ranking → Output

1. Collection System: To support the potential growing number of digital APIs the library is firstly based on a collector abtract interface class that is used to define each APIs collector specificities. 
2. Aggregation Pipeline: 
3. Format Converters: All the metadata collected are then converted into a unified structure
4. Citation extractors
And relies on two configurations files that need to be filled by the user:
1. the first one gathers all the API key requiered to run a search
2. the second one allows to 


SciLex is a Python‑based tool designed to search, retrieve, and analyze scientific papers using a structured, object‑oriented approach. The primary class, PaperRetriever, serves as the central interface and can be used both via the command line and as an importable module for integration into custom Python scripts or Jupyter notebooks. Supporting classes—PubMedSearcher, ImageExtractor, PaperTracker, and ReferenceRetriever—extend its capabilities, allowing for enhanced paper searching, citation tracking, and figure extraction.


### Command-Line vs. Programmatic Usage

- **Command-Line Interface (CLI)**: ?
- **Python Module Import**: ?

# Research use / scholarly publications enabled

# Comparison with others existing software

**1. CoLRev (2026)**
A large project

**2.PyPaperRetriever (2025)**
PyPaperRetriever [@Turner2025] is a medical research oriented literrature exploration software. It first rely on a set of papers identified by a DOI or PubMed ID and queries three different APIs (Unpaywall, NIH's Entrez, and Crossref) to retrieve related papers based on the citation network drawn by the input articles. The software also propose the extraction of the PDF content of the resulting articles, which make it more adapted to conduct textmining. It digital library coverage is lower than SciLEx which is more general, and the the result of the extraction is more focus on the textual content of the similar articles retrieved than the bibliographic data of them.

**3. Pygetpapers (2022)** 
PygetPapers [@Garg2022] is also a medical/biology research oriented software which help to collect papers based on a simple list of keywords by requesting several digital libraries (arXiv, EuropePMC, bioRxiv, medRxiv). This software do not propose filtering strategies to digest the high amonth of paper that could be retrieved by the API used, and do not propose deduplication strategies. Moreover the resulting extraction of Pygetpapers are not related to a bibiolography that could be easily shared (pdf/xmls). This software also serve different purpose than SciLEx, notably by being more centred on textmining.

 **4. PyPaperBot (2020)**

PyPaperBot [@pypaperbot], while functional, has significant limitations that prompted the development of PyPaperRetriever. PyPaperBot relies primarily on Sci‑Hub, which is ethically controversial, may be unlawful to use in many jurisdictions, and is often blocked by academic institutions and in certain countries. Additionally, it lacks support for PubMed ID‑based searches, a critical feature for researchers in biomedical sciences.

**5. ResearchRabbit/ Litmaps / ConnectedPapers**

- 
# Acknowledgements

This work was supported by the French government through the France 2030 investment plan managed by the National Research Agency (ANR), as part of the Initiative of Excellence Université Côte d'Azur (ANR-15-IDEX-01). Additional support came from French Government's France 2030 investment plan (ANR-22-CPJ2-0048-01), through 3IA Côte d'Azur (ANR-23-IACL-0001).

## AI Usage Disclosure

Tools used: Claude Code CLI (Anthropic) with Claude Sonnet 4.5 and Claude Opus 4.5 models, used from October 2025 through February 2026. Prior to October 2025, no AI tools were used by any contributor (C. Ringwald, A. Ollagnier, F. Gandon).
Scope of assistance: 
  - Code development and refactoring : Claude Code was used to assist with implementing new features (PubMed collector, HuggingFace enrichment pipeline, BibTeX export, parallel aggregation, citation caching), refactoring the collector architecture (modular collector classes, multi-threading migration, state management removal), and bug fixing (API rate limiting, URL encoding, deduplication logic, metadata extraction).
  - Code quality : Automated linting, formatting (via Ruff), and code style improvements.
  - Documentation : Updating README, CLAUDE.md project instructions, documentation suite (docs/) and inline documentation.
 
/
# References
