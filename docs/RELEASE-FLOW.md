# Release Flow: develop -> rc -> main

This document describes the Git branching and release strategy for MUXI repositories.

## Branch Structure

```
main     ─────●─────────●─────────●─────  (production releases)
              ↑         ↑         ↑
rc       ────●●────────●●────────●●────  (release candidates)
             ↑↑        ↑↑        ↑↑
develop  ●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●  (continuous development)
```

| Branch | Purpose | CI Workflow |
|--------|---------|-------------|
| `develop` | Active development, feature integration | `ci.yml` - runs tests |
| `rc` | Release candidates, final testing | `rc.yml` - builds & tests |
| `main` | Production releases | `release.yml` - creates GitHub release |

## Release Process

### 1. Development (develop branch)
```bash
# Work on features
git checkout develop
git pull origin develop

# Make changes, commit
git add .
git commit -m "feat: description"
git push origin develop
```

CI runs automatically on every push to `develop`.

### 2. Prepare Release Candidate (rc branch)
```bash
# Update version
echo "X.YYYYMMDD.N" > .version
git add .version
git commit -m "chore: bump version to X.YYYYMMDD.N"
git push origin develop

# Wait for CI to pass, then merge to rc
git checkout rc
git pull origin rc
git merge develop -m "Merge develop into rc for vX.YYYYMMDD.N"
git push origin rc
```

RC workflow runs - builds artifacts and runs full test suite.

### 3. Production Release (main branch)
```bash
# Wait for RC workflow to pass, then merge to main
git checkout main
git pull origin main
git merge rc -m "Release vX.YYYYMMDD.N"
git push origin main
```

Release workflow runs:
- Builds production artifacts
- Creates GitHub Release with version tag
- Uploads binaries/assets to release

### 4. Return to develop
```bash
git checkout develop
```

## Version Format

```
X.YYYYMMDD.N
```

- `X` - Major version (0 for pre-1.0)
- `YYYYMMDD` - Date of release
- `N` - Release number on that date (0, 1, 2...)

Examples:
- `0.20251204.0` - First release on Dec 4, 2025
- `0.20251204.1` - Second release on Dec 4, 2025
- `1.20260101.0` - First v1.x release on Jan 1, 2026

## CI/CD Workflows

### ci.yml (develop)
```yaml
on:
  push:
    branches: [develop]
  pull_request:
    branches: [develop]

jobs:
  test:
    - Run linters (fmt, vet)
    - Run tests with coverage
    - Check coverage threshold
```

### rc.yml (rc)
```yaml
on:
  push:
    branches: [rc]

jobs:
  build-and-test:
    - Run full test suite
    - Build artifacts for all platforms
    - Upload artifacts (optional)
```

### release.yml (main)
```yaml
on:
  push:
    branches: [main]

jobs:
  release:
    - Run tests
    - Build artifacts for all platforms
    - Create GitHub Release
    - Upload artifacts to release
```

## Handling Merge Conflicts

### .version conflict
Common when merging rc -> main:
```bash
# Resolve by keeping the new version
echo "X.YYYYMMDD.N" > .version
git add .version
git commit -m "Release vX.YYYYMMDD.N"
git push origin main
```

## Hotfix Process

For urgent fixes to production:
```bash
# Create hotfix from main
git checkout main
git pull origin main
git checkout -b hotfix/description

# Make fix, commit
git add .
git commit -m "fix: description"

# Merge to main
git checkout main
git merge hotfix/description
git push origin main

# Backport to develop
git checkout develop
git merge hotfix/description
git push origin develop

# Clean up
git branch -d hotfix/description
```

## Checklist

### Before RC merge:
- [ ] All CI tests pass on develop
- [ ] Version bumped in `.version`
- [ ] CHANGELOG.md updated (if applicable)

### Before main merge:
- [ ] RC workflow passed
- [ ] Manual testing complete (if needed)

### After release:
- [ ] Verify GitHub Release created
- [ ] Verify assets uploaded
- [ ] Return to develop branch
