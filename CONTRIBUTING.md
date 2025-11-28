# Contributing to OTEL API Scraper

Thank you for your interest in contributing to the OTEL API Scraper! This document outlines our development standards, processes, and requirements to ensure high-quality, consistent contributions.

## 🚀 Quick Start for Contributors

### 1. Development Environment Setup

```bash
# Clone the repository
git clone https://github.com/your-org/otel-api-scraper.git
cd otel-api-scraper

# Install dependencies (requires Python 3.10+)
uv sync --dev

# Install pre-commit hooks (REQUIRED)
uv run pre-commit install
uv run pre-commit install --hook-type commit-msg
```

### 2. Verify Setup

```bash
# Test pre-commit hooks
uv run pre-commit run --all-files

# Run tests
uv run pytest --cov=src --cov-report=term-missing

# Test local stack (for core changes)
cd "LOCAL TESTING"
docker-compose up -d
```

## 📝 Development Guidelines

### Commit Message Requirements

**ALL commit messages MUST follow [Conventional Commits](https://www.conventionalcommits.org/) format:**

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

#### Allowed Types
- `feat`: New features
- `fix`: Bug fixes
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `test`: Adding or modifying tests
- `build`: Build system changes
- `ci`: CI configuration changes
- `chore`: Maintenance tasks
- `revert`: Reverting previous commits

#### Common Scopes
- `auth`: Authentication related changes
- `scraper`: Core scraping functionality
- `config`: Configuration handling
- `telemetry`: Metrics and logging
- `pipeline`: Data processing pipeline
- `http`: HTTP client functionality
- `fingerprints`: Delta detection and storage
- `admin`: Admin API functionality
- `scheduler`: Job scheduling
- `docs`: Documentation
- `tests`: Test-related changes

#### Examples of Valid Commit Messages

```bash
# Features
git commit -m "feat(auth): add Azure AD authentication support"
git commit -m "feat(scraper): implement parallel window processing"
git commit -m "feat(telemetry): add custom histogram bucket support"

# Bug fixes
git commit -m "fix(http): handle connection timeouts properly"
git commit -m "fix(config): validate required authentication fields"
git commit -m "fix(pipeline): resolve fingerprint collision edge case"

# Documentation
git commit -m "docs(readme): update Docker Compose setup instructions"
git commit -m "docs(config): add OAuth configuration examples"
git commit -m "docs(auth): document Azure AD setup process"

# Tests
git commit -m "test(runner): increase coverage to 95%"
git commit -m "test(config): add edge case validation tests"
git commit -m "test(integration): add end-to-end scraping tests"

# Refactoring
git commit -m "refactor(telemetry): simplify metric emission logic"
git commit -m "refactor(auth): extract token management to separate class"

# Performance
git commit -m "perf(fingerprints): optimize database queries with indexes"
git commit -m "perf(http): implement connection pooling"

# Chores
git commit -m "chore(deps): update OpenTelemetry to v1.38.0"
git commit -m "chore(ci): add automated testing workflow"
```

## 🔧 Pre-commit Hook Pipeline

Our pre-commit hooks run automatically on every commit in this order:

### 1. Conventional Commit Validation (commit-msg stage)
- **When**: Before commit message is accepted
- **Purpose**: Ensures all commit messages follow conventional commit format
- **Failure**: Commit is rejected with helpful error message

### 2. Code Linting (pre-commit stage)
- **Tool**: Ruff with `--fix` flag
- **Purpose**: Auto-fixes code style issues
- **Includes**: Import sorting, formatting, basic linting

### 3. Code Formatting (pre-commit stage)  
- **Tool**: Ruff formatter
- **Purpose**: Ensures consistent code formatting

### 4. Test Coverage (pre-commit stage)
- **Requirement**: ≥90% test coverage
- **Command**: `pytest --cov=src --cov-report=term-missing --cov-fail-under=90`
- **Failure**: Commit rejected if coverage falls below 90%

## 🧪 Testing Requirements

### Test Coverage Standards
- **Minimum**: 90% overall coverage (enforced by CI)
- **Target**: 95%+ for core modules (`runner.py`, `scraper_engine.py`, `telemetry.py`)
- **Files to prioritize**: Any module handling data processing, authentication, or configuration

### Running Tests

```bash
# Run all tests with coverage
uv run pytest --cov=src --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_runner.py -v

# Run tests for specific module
uv run pytest --cov=src/otel_api_scraper/runner --cov-report=term-missing

# Generate HTML coverage report
uv run pytest --cov=src --cov-report=html
# Open htmlcov/index.html in browser
```

### Test Organization
- Place tests in `tests/` directory
- Name test files as `test_<module_name>.py`
- Use descriptive test class and method names
- Include both unit tests and integration tests where appropriate

## 📚 Documentation Requirements

### Docstring Standards
**ALL functions and classes MUST have docstrings** following Google style:

```python
def scrape_api_endpoint(url: str, auth_config: AuthConfig) -> List[Dict[str, Any]]:
    """Scrape data from an API endpoint with authentication.
    
    Args:
        url: The API endpoint URL to scrape
        auth_config: Authentication configuration for the request
        
    Returns:
        List of records extracted from the API response
        
    Raises:
        HTTPError: If the API request fails
        ConfigError: If authentication configuration is invalid
    """
    # Implementation here
    pass

class ScraperEngine:
    """Core scraping engine that orchestrates API calls and data processing.
    
    This class handles window computation, HTTP requests, and coordinates
    the record processing pipeline for configured sources.
    
    Attributes:
        config: Application configuration
        http_client: Async HTTP client for API requests  
        pipeline: Record processing pipeline
    """
    
    def __init__(self, config: AppConfig):
        """Initialize the scraper engine.
        
        Args:
            config: Application configuration containing sources and global settings
        """
        pass
```

### Documentation Updates Required

When making changes that affect configuration or functionality, update:

1. **Configuration Template** (`config.yaml.template`)
   - Add new configuration options with comments
   - Update examples and default values
   - Document any breaking changes

2. **README Files**
   - Main `README.md` for user-facing changes
   - `CONFIGURATION/README.md` for config changes
   - Relevant sub-directory READMEs in `CONFIGURATION/sources/`

3. **Example Configurations**
   - Update examples in `CONFIGURATION/sources/auth/`
   - Update examples in `CONFIGURATION/sources/scrape-types/`
   - Update examples in `CONFIGURATION/sources/measurements/`

### Local Stack Testing

**REQUIRED for core changes**: Test against the full local stack before submitting PRs that affect:
- Core scraping functionality (`scraper_engine.py`, `pipeline.py`)
- Telemetry emission (`telemetry.py`)
- Authentication (`http_client.py`, auth strategies)
- Configuration loading (`config.py`)

```bash
# Start local testing environment
cd "LOCAL TESTING"
docker-compose up -d

# Test your changes
# Modify config.yaml to test your feature
docker-compose restart scraper

# View logs
docker-compose logs -f scraper

# Access dashboards
open http://localhost:3000  # Grafana (admin/admin)
open http://localhost:9090  # Prometheus  
open http://localhost:3100  # Loki

# Stop when done
docker-compose down -v
```

## 🔄 Development Workflow

### 1. Feature Development

```bash
# Create feature branch
git checkout -b feat/add-saml-auth

# Make changes with proper commits
git commit -m "feat(auth): add SAML authentication strategy"
git commit -m "test(auth): add SAML authentication tests" 
git commit -m "docs(auth): add SAML configuration examples"
```

### 2. Pre-submission Checklist

- [ ] All commits follow conventional commit format
- [ ] Pre-commit hooks pass (`uv run pre-commit run --all-files`)
- [ ] Test coverage ≥90% (`uv run pytest --cov=src --cov-fail-under=90`)
- [ ] All functions/classes have docstrings
- [ ] Documentation updated (if applicable)
- [ ] Local stack testing completed (for core changes)
- [ ] Ready to squash commits before PR

### 3. Pull Request Requirements

#### Before Submitting:
```bash
# Ensure your branch is up to date
git fetch origin main
git rebase origin/main

# Squash commits into logical units
git rebase -i origin/main
# or use GitHub's squash merge option

# Final pre-commit check
uv run pre-commit run --all-files

# Push to your fork/branch
git push origin feat/add-saml-auth
```

#### PR Title and Description:
- **Title**: Must follow conventional commit format
  ```
  feat(auth): add SAML authentication support
  ```
- **Description**: Include:
  - What was changed and why
  - Testing approach taken
  - Documentation updates made
  - Breaking changes (if any)


## 🛠️ Manual Commands Reference

### Pre-commit Operations
```bash
# Run all hooks manually
uv run pre-commit run --all-files

# Run specific hook
uv run pre-commit run ruff --all-files
uv run pre-commit run conventional-pre-commit --all-files

# Update hook versions
uv run pre-commit autoupdate

# Bypass hooks (emergency only - NOT recommended)
git commit --no-verify
```

### Linting and Formatting
```bash
# Check for issues (no fixes)
uv run ruff check .

# Fix auto-fixable issues
uv run ruff check . --fix

# Format code
uv run ruff format .

# Check specific file
uv run ruff check src/otel_api_scraper/runner.py
```

### Testing and Coverage
```bash
# Basic test run
uv run pytest

# With coverage report
uv run pytest --cov=src --cov-report=term-missing

# HTML coverage report
uv run pytest --cov=src --cov-report=html

# Test specific file
uv run pytest tests/test_config.py -v

# Run tests matching pattern
uv run pytest -k "test_auth" -v

# Stop on first failure
uv run pytest -x

# Run tests with verbose output
uv run pytest -v --tb=short
```

## 🎯 Contribution Areas

Please check our [Roadmap](./ROADMAP.md) to find planned items we welcome contributions for.

Beyond the roadmap, contributions in these areas are most welcome:

### Ease-of-Use and Stability 
- **Built-in connector templates** for popular SaaS (Salesforce, Jira, etc.)
- **Enhanced error handling** and retry mechanisms
- **Configuration validation improvements**

### Documentation & Examples
- **Real-world configuration examples**
- **Integration guides** for specific platforms
- **Performance tuning guides**
- **Troubleshooting documentation**


## ❓ Getting Help

- **General questions**: Open a GitHub Discussion
- **Bug reports**: Open a GitHub Issue with full details
- **Feature requests**: Open a GitHub Issue with use case
- **Development help**: Reference existing tests and `IMPLEMENTATION_DIARY.md`

## 🔒 Security Considerations

- Never commit secrets, tokens, or credentials
- Use environment variables for sensitive configuration
- Follow secure coding practices for authentication handling
- Report security vulnerabilities privately via GitHub Security Advisories

---
