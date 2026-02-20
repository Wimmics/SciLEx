# API Comparison Matrix

Reference guide comparing all supported academic APIs.

## Quick Comparison

Rate limits use a dual-value system (without_key / with_key) auto-selected based on whether an API key is configured. See `scilex/config_defaults.py` for all defaults.

| API | Coverage | API Key | Rate Limit (no key / with key) | Abstracts | Citations | DOI | Best For |
|-----|----------|---------|-------------------------------|-----------|-----------|-----|----------|
| **Semantic Scholar** | 200M+ papers | Optional | 1.0 / 1.0 req/s | 95% | Yes | 85% | AI/CS research |
| **OpenAlex** | 250M+ works | Optional | 10.0 / 10.0 req/s | 60% | Yes | 90% | Broad coverage |
| **IEEE Xplore** | 5M+ docs | Required | 2.0 / 2.0 req/s | 100% | Limited | 95% | Engineering |
| **Elsevier** | 18M+ articles | Required | 2.0 / 9.0 req/s | 80% | No | 100% | Life sciences |
| **Springer** | 13M+ docs | Required | 1.67 / 1.67 req/s | 90% | No | 98% | Multidisciplinary |
| **arXiv** | 2M+ preprints | No | 0.33 / 0.33 req/s | 100% | No | 60% | Physics/Math/CS |
| **PubMed** | 35M+ papers | Optional | 3.0 / 10.0 req/s | 90% | No | 80% | Biomedical |
| **HAL** | 1M+ docs | No | 10.0 / 10.0 req/s | 70% | No | 40% | French research |
| **DBLP** | 6M+ CS papers | No | 1.0 / 1.0 req/s | 0% | No | 95% | CS bibliography |
| **ISTEX** | 25M+ docs | No | 5.0 / 5.0 req/s | 95% | No | 98% | French archives |

## API Details

### Semantic Scholar

- **Strengths**: Excellent citations, AI/ML coverage, free API
- **Weaknesses**: CS-biased, limited pre-1990 papers
- **Use for**: AI/ML/CS research, citation networks

### OpenAlex

- **Strengths**: Massive coverage, no key required, institutional data
- **Weaknesses**: 60% abstract coverage, may lag on citations
- **Use for**: Broad multidisciplinary searches

### IEEE Xplore

- **Strengths**: Complete abstracts, engineering focus, standards
- **Weaknesses**: Daily quota limit (200), API key required
- **Use for**: Engineering and technology papers

### Elsevier

- **Strengths**: High-quality journals, life sciences, medical
- **Weaknesses**: API key required, no citations, complex auth
- **Use for**: Biomedical research

### Springer

- **Strengths**: Books and chapters, European content
- **Weaknesses**: API key required, no citations
- **Use for**: Book chapters, multidisciplinary

### arXiv

- **Strengths**: 100% abstracts, free, latest preprints
- **Weaknesses**: Not peer-reviewed, no citations
- **Use for**: Cutting-edge physics/math/CS

### HAL

- **Strengths**: French research, open access
- **Weaknesses**: Low DOI coverage (40%), French-focused
- **Use for**: French and European research

### DBLP

- **Strengths**: Complete CS bibliography, high DOI rate (95%)
- **Weaknesses**: No abstracts (copyright policy), CS-only
- **Use for**: CS conference papers, bibliographic data

### PubMed

- **Strengths**: 35M+ biomedical papers, MeSH subject headings, PMC landing page URLs
- **Weaknesses**: Biomedical focus only, no citation data
- **Use for**: Biomedical and life sciences research, systematic reviews

### ISTEX

- **Strengths**: Historical archives, 95% abstracts
- **Weaknesses**: French interface, may need institutional access
- **Use for**: Historical papers, French archives

## API Selection Guide

### For AI/CS Research
```yaml
apis:
  - SemanticScholar
  - DBLP
  - Arxiv
```

### For Biomedical Research
```yaml
apis:
  - PubMed
  - Elsevier
  - OpenAlex
  - Springer
```

### For Engineering
```yaml
apis:
  - IEEE
  - Arxiv
  - SemanticScholar
```

### For Broad Coverage (No Keys)
```yaml
apis:
  - OpenAlex
  - Arxiv
  - DBLP
  - HAL
```

## Configuration

### API Keys

Get keys from:
- [Semantic Scholar](https://www.semanticscholar.org/product/api)
- [IEEE](https://developer.ieee.org/getting_started)
- [Elsevier](https://dev.elsevier.com/)
- [Springer](https://dev.springernature.com/)
- [PubMed / NCBI](https://www.ncbi.nlm.nih.gov/account/settings/) (optional, 3x rate boost)
- [OpenAlex](https://openalex.org/settings/api) (optional, 1000x daily quota boost)

### Rate Limits

Defaults are in `scilex/config_defaults.py` with dual-value system (without_key / with_key).
Override in `api.config.yml` only if you have special access:
```yaml
rate_limits:
  SemanticScholar: 1.0   # Same with or without key
  OpenAlex: 10.0          # Same with or without key
  Arxiv: 0.33             # 1 request per 3 seconds
  IEEE: 2.0
  Elsevier: 9.0           # 9 req/sec with key (2 without)
  Springer: 1.67          # 100 req/min
  PubMed: 10.0            # 10 req/sec with key (3 without)
  HAL: 10.0
  DBLP: 1.0
  Istex: 5.0
```

## Coverage by Field

- **Computer Science**: SemanticScholar, DBLP, Arxiv, IEEE
- **Life Sciences**: PubMed, Elsevier, OpenAlex, Springer
- **Engineering**: IEEE, Springer, Arxiv
- **Physics/Math**: Arxiv, OpenAlex, Springer
- **Social Sciences**: OpenAlex, Springer

## Known Limitations

### Abstract Availability
- 100%: IEEE, Arxiv
- 95%: Semantic Scholar, ISTEX
- 90%: Springer
- 80%: Elsevier
- 70%: HAL
- 60%: OpenAlex
- 0%: DBLP (by policy)

### DOI Coverage
- 100%: Elsevier
- 98%: Springer, ISTEX
- 95%: IEEE, DBLP
- 90%: OpenAlex
- 85%: Semantic Scholar
- 80%: PubMed
- 60%: Arxiv
- 40%: HAL

### Citation Data Available
- Yes: Semantic Scholar, OpenAlex
- Citation counts only: CrossRef (used during aggregation for per-DOI citation lookup)
- No: All others