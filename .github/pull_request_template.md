## Description

<!-- Please include a summary of the changes and why this PR is needed. -->

Fixes # (issue)

### Type of Change

<!-- Mark the relevant option with an "x" -->

- [ ] 🐛 **Bug fix** (non-breaking change which fixes an issue)
- [ ] ✨ **New feature** (non-breaking change which adds functionality)
- [ ] 📚 **Documentation** (changes to documentation or examples)
- [ ] 🎨 **Style** (formatting, imports, minor refactoring)
- [ ] ♻️ **Refactoring** (code change that doesn't fix bugs or add features)
- [ ] ⚡ **Performance** (improves performance)
- [ ] 🧪 **Test** (adding or modifying tests)
- [ ] 🔨 **Build/CI** (changes to build system or CI configuration)
- [ ] 🔐 **Security** (security improvements or fixes)
- [ ] ⚠️ **Breaking change** (change that breaks existing functionality)

## Changes Made

<!-- Describe the specific changes made in this PR -->

- 
- 
- 

## Related Configuration Changes

<!-- If this PR modifies configuration, list the changes -->

- [ ] Updated `config.yaml.template`
- [ ] Updated `CONFIGURATION/README.md` or related docs
- [ ] Updated global settings documentation
- [ ] Added new auth strategy / scrape type / measurement type

**Configuration details:**
<!-- Describe any config changes here -->

## Testing

### Testing Checklist

- [ ] Unit tests added/updated
- [ ] All tests pass: `uv run pytest --cov=src --cov-report=term-missing`
- [ ] Test coverage maintained ≥90%
- [ ] Local stack testing completed (if affecting core scraper/telemetry/auth/config)

### Test Coverage

<!-- Provide coverage metrics if applicable -->

```
Before: XX%
After:  XX%
```

### Local Stack Testing

<!-- If this affects core functionality, confirm local stack testing -->

- [ ] Started local stack: `cd "LOCAL TESTING" && docker-compose up -d`
- [ ] Tested with updated configuration
- [ ] Verified in Grafana, Prometheus, and Loki dashboards
- [ ] Checked scraper logs for errors: `docker-compose logs -f scraper`

## Documentation

### Documentation Checklist

- [ ] Docstrings added/updated for all new functions and classes (100% coverage)
- [ ] README.md updated (if user-facing change)
- [ ] config.yaml.template updated (if configuration changed)
- [ ] Example configurations updated (if needed)
- [ ] TELEMETRY.md updated (if self-telemetry metrics changed)

**Documentation updated in:**
<!-- List files modified for documentation -->

## Code Quality

### Code Quality Checklist

- [ ] Code follows project style (verified by `uv run ruff check .`)
- [ ] Code is formatted correctly (`uv run ruff format .`)
- [ ] Pre-commit hooks pass: `uv run pre-commit run --all-files`
- [ ] Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/)

### Conventional Commits

Commit messages in this PR follow the format: `<type>(<scope>): <description>`

**Example commits:**
```
feat(auth): add SAML authentication support
fix(scraper): handle connection timeout errors
test(runner): increase coverage to 95%
docs(config): add OAuth configuration examples
```

## Breaking Changes

<!-- If this is a breaking change, please describe the migration path for users -->

- [ ] This PR introduces breaking changes

**Migration guide for users:**
<!-- Describe how users should update their configurations/code -->

## Performance Impact

<!-- Describe any performance implications -->

- [ ] No performance impact
- [ ] Improves performance (describe improvements)
- [ ] May impact performance (describe potential issues)

**Performance details:**
<!-- Provide benchmarks or analysis if applicable -->

## Security Considerations

<!-- Note any security implications -->

- [ ] No security concerns
- [ ] Security improvement (describe improvements)
- [ ] Security review recommended (describe concerns)

**Security details:**
<!-- Describe any security considerations -->

## Screenshots / Logs (if applicable)

<!-- Add screenshots, logs, or other evidence of testing -->

## Additional Context

<!-- Add any other context about the PR here -->

---

## Pre-Submission Checklist

Before submitting this PR, please ensure:

- [ ] **Conventional commits**: All commit messages follow the standard format
- [ ] **Commits squashed**: Related commits have been squashed into logical units
- [ ] **Tests passing**: `uv run pytest --cov=src --cov-fail-under=90`
- [ ] **Linting passing**: `uv run ruff check . --fix && uv run ruff format .`
- [ ] **Pre-commit passing**: `uv run pre-commit run --all-files`
- [ ] **Docstrings complete**: All functions/classes have docstrings (100% coverage)
- [ ] **Config files updated**: config.yaml.template and docs updated if needed
- [ ] **Local stack tested**: Core changes tested with local stack if applicable
- [ ] **Documentation updated**: README and relevant docs reflect changes
- [ ] **No merge conflicts**: Branch is up to date with main

---

**Reviewer notes:**
<!-- Add any notes for reviewers -->

**Related issues/discussions:**
<!-- Link to related GitHub issues or discussions -->

Closes # (if applicable)

Related to # (if applicable)
