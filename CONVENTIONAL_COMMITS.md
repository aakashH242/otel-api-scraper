# Pre-commit Hooks and Conventional Commits

This project uses pre-commit hooks to ensure code quality and commit message consistency.

## Setup

The pre-commit hooks are automatically installed when you run:

```bash
uv sync --dev
uv run pre-commit install
uv run pre-commit install --hook-type commit-msg
```

## Hooks Configuration

The pre-commit pipeline runs in this order:

### 1. Conventional Commit Check (commit-msg stage)
**When it runs:** Before the commit message is accepted  
**What it does:** Validates that commit messages follow the [Conventional Commits](https://www.conventionalcommits.org/) standard

**Valid commit types:**
- `feat`: A new feature
- `fix`: A bug fix  
- `docs`: Documentation only changes
- `style`: Changes that do not affect the meaning of the code
- `refactor`: A code change that neither fixes a bug nor adds a feature
- `perf`: A code change that improves performance
- `test`: Adding missing tests or correcting existing tests
- `chore`: Changes to the build process or auxiliary tools
- `ci`: Changes to CI configuration files and scripts
- `build`: Changes that affect the build system or external dependencies
- `revert`: Reverts a previous commit

**Examples of valid commit messages:**
```
feat(auth): add OAuth token validation
fix(scraper): handle connection timeouts properly
docs(readme): update installation instructions  
test(runner): increase coverage to 95%
chore(deps): update dependencies
ci(pre-commit): add conventional commit checking
refactor(config): simplify authentication logic
perf(fingerprints): optimize database queries
```

**Examples of invalid commit messages:**
```
updated readme
fixing bug
Add new feature
WIP: work in progress
```

### 2. Code Linting (pre-commit stage)
**When it runs:** Before files are committed  
**What it does:** 
- `ruff`: Lints Python code and automatically fixes issues
- `ruff-format`: Formats Python code consistently

### 3. Test Coverage (pre-commit stage)
**When it runs:** Before files are committed  
**What it does:** Runs pytest with coverage and fails if coverage falls below 90%

## Workflow

### Normal Commit Flow
```bash
# Stage your changes
git add .

# Commit with conventional message
git commit -m "feat(runner): increase test coverage to over 95%"
```

The hooks will run automatically:
1. ✅ Conventional commit message check passes
2. ✅ Ruff linting and formatting passes  
3. ✅ Test coverage passes (≥90%)
4. ✅ Commit is accepted

### If Hooks Fail

#### Conventional Commit Message Failure
```bash
$ git commit -m "updated some stuff"

Conventional Commit......................................................Failed
- hook id: conventional-pre-commit
- exit code: 1

[Bad Commit message] >> updated some stuff

Your commit message does not follow Conventional Commits formatting
```

**Fix:** Use a proper conventional commit message:
```bash
git commit -m "chore: update dependencies and configuration"
```

#### Code Linting Failure
```bash
ruff.................................................(no files to check)Skipped
ruff-format..........................................(no files to check)Skipped  
pytest with coverage (fail <90%).....................(no files to check)Skipped
```

**Fix:** The hooks will often auto-fix issues. If not, fix manually and commit again.

#### Test Coverage Failure
```bash
pytest with coverage (fail <90%).......................Failed
```

**Fix:** Add tests to increase coverage above 90% threshold.

## Manual Hook Execution

You can run hooks manually:

```bash
# Run all pre-commit hooks
uv run pre-commit run --all-files

# Run specific hook
uv run pre-commit run ruff --all-files
uv run pre-commit run pytest-cov --all-files

# Test commit message manually
echo "feat: add new feature" > temp_msg.txt
uv run pre-commit run conventional-pre-commit --hook-stage commit-msg --commit-msg-filename temp_msg.txt
```

## Bypassing Hooks (Emergency Only)

If you need to bypass hooks temporarily (NOT recommended):

```bash
# Skip all hooks
git commit -m "emergency fix" --no-verify

# Skip only commit-msg hooks
git commit -m "emergency fix" --no-verify
```

## Configuration Files

- **`.pre-commit-config.yaml`**: Defines which hooks to run
- **`pyproject.toml`**: Contains tool configurations (ruff, pytest, commitizen)
- **`.conventional-commit-types.md`**: Documents allowed commit types

## Benefits

1. **Consistent Code Style**: Ruff ensures consistent formatting
2. **Quality Assurance**: Tests must pass and maintain coverage
3. **Clear History**: Conventional commits make changelogs and history readable
4. **Automated Releases**: Conventional commits enable automated versioning
5. **Team Collaboration**: Everyone follows the same standards

## Common Conventional Commit Examples for This Project

```bash
# New features
git commit -m "feat(auth): add Azure AD authentication support"
git commit -m "feat(scraper): implement parallel window processing"
git commit -m "feat(metrics): add histogram support with custom buckets"

# Bug fixes  
git commit -m "fix(http-client): handle connection timeouts properly"
git commit -m "fix(pipeline): resolve fingerprint collision issue"
git commit -m "fix(config): validate required fields at startup"

# Documentation
git commit -m "docs(readme): update Docker Compose instructions"
git commit -m "docs(auth): add OAuth configuration examples"
git commit -m "docs(api): document admin endpoint authentication"

# Tests
git commit -m "test(runner): increase coverage to 95%"
git commit -m "test(config): add validation error test cases"
git commit -m "test(integration): add end-to-end scraping tests"

# Refactoring
git commit -m "refactor(telemetry): simplify metric emission logic"
git commit -m "refactor(config): extract auth validation to separate function"

# Performance improvements
git commit -m "perf(fingerprints): optimize database query with indexes"
git commit -m "perf(http): implement connection pooling"

# Dependencies and tooling
git commit -m "chore(deps): update OpenTelemetry to v1.38.0"
git commit -m "chore(dev): add pre-commit hooks for code quality"
git commit -m "ci(github): add automated testing workflow"
git commit -m "build(docker): optimize container image size"
```
