# Contributing to SciLEx

Thank you for your interest in contributing to SciLEx! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [How to Contribute](#how-to-contribute)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Documentation](#documentation)
- [Pull Request Process](#pull-request-process)
- [Reporting Issues](#reporting-issues)

## Code of Conduct

We are committed to providing a welcoming and inclusive environment. Please:

- Be respectful and considerate
- Welcome newcomers and help them get started
- Focus on constructive criticism
- Respect differing viewpoints and experiences

## Getting Started

1. Create a new branch for your feature:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes following the coding standards below

3. Test your changes thoroughly

4. Submit a pull request with a clear description

## Development Setup

### Prerequisites

- Python 3.10 or higher
- uv package manager (recommended)
- Git

### Environment Setup

1. Install dependencies:
   ```bash
   uv sync
   ```

2. Set up pre-commit hooks (if available):
   ```bash
   pre-commit install
   ```

3. Copy configuration files:
   ```bash
   cp scilex/api.config.yml.example scilex/api.config.yml
   cp scilex/scilex.config.yml.example scilex/scilex.config.yml
   ```

4. Run tests to verify setup:
   ```bash
   python -m pytest tests/
   ```

## How to Contribute

### Types of Contributions

#### 1. Bug Fixes
- Check existing issues for known bugs
- Create a minimal reproducible example
- Write a test that demonstrates the bug
- Implement the fix
- Ensure all tests pass

#### 2. New Features
- Discuss the feature in an issue first
- Get consensus on the implementation approach
- Write tests for the new feature
- Implement the feature
- Update documentation

#### 3. New API Collectors
- Follow the [Adding API Collectors Guide](docs/developer-guides/adding-collectors.md)
- Ensure proper rate limiting
- Implement format converter
- Add configuration examples
- Write comprehensive tests

#### 4. Documentation
- Fix typos and clarify existing docs
- Add examples and use cases
- Improve API documentation
- Translate documentation

#### 5. Performance Improvements
- Profile the code first
- Benchmark improvements
- Ensure backwards compatibility
- Document performance gains

## Coding Standards

### Python Style Guide

We use `ruff` for formatting and linting:

```bash
# Format code
uvx ruff format .

# Lint code
uvx ruff check --fix .
```

### Code Style Requirements

1. **Docstrings**: Use Google-style docstrings
   ```python
   def function(param1: str, param2: int) -> dict:
       """
       Brief description of function.

       Args:
           param1: Description of param1
           param2: Description of param2

       Returns:
           Description of return value

       Raises:
           ValueError: When param1 is empty
       """
   ```

2. **Type Hints**: Use type hints where helpful
   ```python
   def process_papers(papers: List[Dict[str, Any]]) -> pd.DataFrame:
       pass
   ```

3. **Constants**: Use the centralized constants module
   ```python
   from scilex.constants import MISSING_VALUE, is_valid
   ```

4. **Error Handling**: Be specific with exceptions
   ```python
   # Good
   except requests.HTTPError as e:
       logger.error(f"HTTP error: {e}")

   # Bad
   except:
       pass
   ```

5. **Logging**: Use logging instead of print
   ```python
   import logging
   logger = logging.getLogger(__name__)

   logger.info("Processing %d papers", len(papers))
   ```

### Project Structure

```
scilex/
├── crawlers/           # Keep collector logic here
├── citations/          # Citation-related code
├── Zotero/            # Zotero integration
├── constants.py       # Shared constants
└── *.py              # Main scripts
```

### Git Commit Messages

Follow conventional commits format:

```
type(scope): brief description

Longer explanation if needed.

Fixes #123
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Code style changes
- `refactor`: Code refactoring
- `perf`: Performance improvement
- `test`: Adding tests
- `chore`: Maintenance tasks

Examples:
```bash
git commit -m "feat(collector): add PubMed API collector"
git commit -m "fix(aggregation): correct dual keyword logic for IEEE"
git commit -m "docs: update installation guide with Python 3.13"
```

## Testing

### Running Tests

```bash
# Run all tests
python -m pytest

# Run specific test file
python -m pytest tests/test_collectors.py

# Run with coverage
python -m pytest --cov=scilex --cov-report=html

# Run specific API test
python "src/API tests/SemanticScholarAPI.py"
```

### Writing Tests

1. **Unit Tests**: Test individual functions
   ```python
   def test_query_build():
       collector = SemanticScholar_collector()
       query = collector.query_build([["AI"], []], 2024, ["title"])
       assert "AI" in query
       assert "2024" in query
   ```

2. **Integration Tests**: Test component interaction
   ```python
   def test_collection_pipeline():
       # Test full collection → aggregation flow
       pass
   ```

3. **Mock External APIs**:
   ```python
   @patch('requests.get')
   def test_api_call(mock_get):
       mock_get.return_value.json.return_value = test_data
       # Test without hitting real API
   ```

### Test Coverage

Aim for:
- New features: 80%+ coverage
- Bug fixes: Include regression test
- API collectors: Mock API responses

## Documentation

### When to Update Documentation

Update docs when you:
- Add new features
- Change existing behavior
- Add new configuration options
- Fix bugs that users might encounter
- Add new API collectors

### Documentation Standards

1. **Clear Examples**: Provide working code examples
2. **Explain Why**: Don't just show how, explain why
3. **Keep Updated**: Update docs with code changes
4. **Cross-reference**: Link to related documentation

### Where to Document

- **Code**: Inline comments and docstrings
- **User Guides**: `docs/user-guides/`
- **Developer Guides**: `docs/developer-guides/`
- **API Reference**: `docs/reference/`
- **README.md**: Major feature additions only

## Pull Request Process

### Before Submitting

1. **Update from upstream**:
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Run tests**:
   ```bash
   python -m pytest
   ```

3. **Format and lint**:
   ```bash
   uvx ruff format .
   uvx ruff check --fix .
   ```

4. **Update documentation** if needed

5. **Write clear commit messages**

### PR Description Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Tests pass locally
- [ ] Added new tests
- [ ] Updated existing tests

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] No new warnings
```

### Review Process

1. Maintainers will review your PR
2. Address feedback constructively
3. Make requested changes in new commits
4. Squash commits if requested
5. PR will be merged when approved

## Reporting Issues

### Bug Reports

Include:
1. **Description**: Clear description of the bug
2. **Steps to Reproduce**:
   ```
   1. Configure X
   2. Run command Y
   3. See error Z
   ```
3. **Expected Behavior**: What should happen
4. **Actual Behavior**: What actually happens
5. **Environment**:
   - Python version
   - OS version
   - SciLEx version/commit
6. **Error Messages**: Full traceback
7. **Configuration**: Relevant config snippets

### Feature Requests

Include:
1. **Use Case**: Why is this needed?
2. **Proposed Solution**: How should it work?
3. **Alternatives**: Other approaches considered
4. **Examples**: Code or config examples

## Development Tips

### Performance Profiling

```python
# Use cProfile for performance analysis
python -m cProfile -o profile.stats -m scilex aggregate

# Analyze with snakeviz
pip install snakeviz
snakeviz profile.stats
```

### Memory Profiling

```python
# Use memory_profiler
pip install memory_profiler
python -m memory_profiler -m scilex collect
```

### Debugging Tips

1. **Enable debug logging**:
   ```bash
   LOG_LEVEL=DEBUG scilex-collect
   ```

2. **Save intermediate results**:
   ```python
   import json
   with open('debug_output.json', 'w') as f:
       json.dump(data, f, indent=2)
   ```

3. **Use debugger**:
   ```python
   import pdb; pdb.set_trace()
   ```

## Getting Help

- **GitHub Discussions**: Ask questions
- **Issue Tracker**: Report bugs

## Recognition

Contributors will be:
- Given credit in documentation
- Acknowledged for their contributions

---

Thank you for contributing to SciLEx!