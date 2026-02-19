# Contributing to SciLEx

## Setup

```bash
uv sync
cp scilex/api.config.yml.example scilex/api.config.yml
cp scilex/scilex.config.yml.example scilex/scilex.config.yml
uv run python -m pytest tests/
```

## Workflow

1. Branch off `main`: `git checkout -b feature/your-feature`
2. Make changes, add tests
3. Format and lint: `uvx ruff format . && uvx ruff check --fix .`
4. Open a pull request with a clear description

## Code Style

- `ruff` for formatting and linting (configured in `pyproject.toml`)
- Google-style docstrings
- Use `MISSING_VALUE` / `is_valid()` from `scilex/constants.py` — never hardcode `None` or `"NA"`
- Use `logging`, not `print`

## Commits

Follow [conventional commits](https://www.conventionalcommits.org/):

```
feat(collector): add OpenAlex collector
fix(aggregate): correct dedup for IEEE papers
docs: update installation guide
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

## Adding a New API Collector

See [`docs/developer-guides/adding-collectors.md`](docs/developer-guides/adding-collectors.md).

## Reporting Issues

Open a GitHub issue with: steps to reproduce, expected vs actual behavior, Python version, and full traceback.
