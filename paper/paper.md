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
SciLEx (Science Literature Exploration) is a Python toolkit for systematic literature reviews. Crawl 9+ academic APIs, deduplicate papers, analyze citation networks, and push to Zotero with advanced quality filtering.

# Statement of need

SciLex answers to the growing need to being able to collect and quikly analyse the current state of art covering a given research topic. The software was designed to support systematic literature review methodology defined by[@kitchenham2007guidelines] and the important publication production growth [@10.1162/qss_a_00327]. Starting from a user-defined keyword list,  SciLEx automates the construction of relevant papers by generating and executing all possible combinations of queries derived from this keyword list across multiple digital libraries. This automation facilitates the paper collection process, ensures traceability, and supports the aggregation and deduplication of search result

SciLEx enriches the resulting corpus through the integration with external services such as PaperWithCode\footnote{available until may 2025 \url{https://paperswithcode.com} now redirects to Hugging Face}, CrossRef~\cite{hendricks_crossref_2020}, and Opencitation~\cite{peroni_opencitations_2020}. PaperWithCode, was intended for the Machine Learning community and aimed at connecting research articles to their corresponding methods, implemented code, evaluation results on standard datasets, and initial paper annotations. OpenCitation enables the retrieval of citations and references for a given paper, which can be used both to filter papers by impact and to expand the corpus through citation snowballing.
Finally, SciLEx exports all gathered information into a Zotero~\cite{mueen_ahmed_zotero_2011} collection[\href{https://www.zotero.org/groups/6070963/scilex_re_systlitreview/library}{\faClipboardList}], facilitating collaborative management, selection, and annotation of the corpus.


**Legal/Ethical Notice:** 
### Similar software
**1. PyPaperRetriever
PyPaperRetriever [@Turner2025] addresses these shortcomings through several key improvements. It integrates with three different APIs (Unpaywall, NIH's Entrez, and Crossref) to expand access to a wide range of sources, and prioritizes open‑access sources. The tool also supports PubMed ID searches and programmatic PubMed queries, while enabling module‑level imports for integration into Python workflows, unlike PyPaperBot's command‑line‑only functionality.
- **2. PyPaperBot**

PyPaperBot [@pypaperbot], while functional, has significant limitations that prompted the development of PyPaperRetriever. PyPaperBot relies primarily on Sci‑Hub, which is ethically controversial, may be unlawful to use in many jurisdictions, and is often blocked by academic institutions and in certain countries. Additionally, it lacks support for PubMed ID‑based searches, a critical feature for researchers in biomedical sciences.


- 
### Key Features
[SCHEMA]

- Multi-API collection with parallel processing (PubMed, SemanticScholar, OpenAlex, IEEE, Arxiv, Springer, HAL, DBLP, Istex, GoogleScholar)
-   Smart deduplication using DOI, URL, and fuzzy title matching
-   Parallel aggregation with configurable workers (default mode)
-   Citation network extraction via OpenCitations + Semantic Scholar with SQLite caching
-   Quality filtering pipeline with time-aware citation thresholds, relevance ranking, and itemType filtering
-   HuggingFace enrichment (NEW): Extract ML models, datasets, GitHub stats, and AI keywords
-   Bulk Zotero upload in batches of 50 items
-   Idempotent collections for safe re-runs (automatically skips completed queries)


# Software design

To support the potential growing number of digital APIs and the 
Scilex relies on four main components: 
1. Collection System
2. Aggregation Pipeline
3. Format Converters
4. Citation extractors
And relies on two configurations files that need to be filled by the user:
1. the first one gathers all the API key requiered to run a search
2. the second one allows to 
...
# Methods

SciLex is a Python‑based tool designed to search, retrieve, and analyze scientific papers using a structured, object‑oriented approach. The primary class, PaperRetriever, serves as the central interface and can be used both via the command line and as an importable module for integration into custom Python scripts or Jupyter notebooks. Supporting classes—PubMedSearcher, ImageExtractor, PaperTracker, and ReferenceRetriever—extend its capabilities, allowing for enhanced paper searching, citation tracking, and figure extraction.


### Object-Oriented Structure

The software is structured around the following classes:

### Command-Line vs. Programmatic Usage

- **Command-Line Interface (CLI)**: ?
- **Python Module Import**: ?
- 
# Similar Tools
/
# Ethical and legal note on Sci-Hub

/
# Availability

/
# Acknowledgements

/
# References
