# API Comparison Matrix

Reference guide comparing all supported academic APIs.

## Quick Comparison

| API | Coverage | API Key | Rate Limit | Abstracts | Citations | DOI | Best For |
|-----|----------|---------|------------|-----------|-----------|-----|----------|
| **Semantic Scholar** | 200M+ papers | Optional | 1 req/s | 95% | Yes | 85% | AI/CS research |
| **OpenAlex** | 250M+ works | No | 10 req/s | 60% | Yes | 90% | Broad coverage |
| **IEEE Xplore** | 5M+ docs | Required | 200/day | 100% | Limited | 95% | Engineering |
| **Elsevier** | 18M+ articles | Required | Varies | 80% | No | 100% | Life sciences |
| **Springer** | 13M+ docs | Required | 5000/day | 90% | No | 98% | Multidisciplinary |
| **arXiv** | 2M+ preprints | No | 3 req/s | 100% | No | 60% | Physics/Math/CS |
| **HAL** | 1M+ docs | No | 10 req/s | 70% | No | 40% | French research |
| **DBLP** | 6M+ CS papers | No | 10 req/s | 0% | No | 95% | CS bibliography |
| **Google Scholar** | Unknown | No | 2 req/s | Varies | Yes | 20% | Comprehensive |
| **ISTEX** | 25M+ docs | No | 10 req/s | 95% | No | 98% | French archives |

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

### Google Scholar

- **Strengths**: Broadest coverage, includes grey literature
- **Weaknesses**: Web scraping (slow), low DOI coverage (20%)
- **Use for**: Maximum coverage, finding obscure papers

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

### Rate Limits

Conservative defaults in `api.config.yml`:
```yaml
rate_limits:
  SemanticScholar: 1.0
  OpenAlex: 10.0
  IEEE: 10.0
  Elsevier: 6.0
  Springer: 1.5
  Arxiv: 3.0
  HAL: 10.0
  DBLP: 10.0
  GoogleScholar: 2.0
  Istex: 10.0
```

## Coverage by Field

- **Computer Science**: SemanticScholar, DBLP, Arxiv, IEEE
- **Life Sciences**: Elsevier, OpenAlex, Springer
- **Engineering**: IEEE, Springer, Arxiv
- **Physics/Math**: Arxiv, OpenAlex, Springer
- **Social Sciences**: OpenAlex, Google Scholar, Springer

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
- 60%: Arxiv
- 40%: HAL
- 20%: Google Scholar

### Citation Data Available
- Yes: Semantic Scholar, OpenAlex, Google Scholar
- No: All others