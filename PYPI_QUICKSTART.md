# PyPI Quick Reference

**One-page guide for publishing MUXI Runtime to PyPI**

---

## 📦 Quick Commands

```bash
# 1. Update version
echo "0.$(date +%Y%m%d).1" > src/muxi/.version

# 2. Build package
./scripts/build_package.sh

# 3. Test locally
pip install dist/muxi-*.whl

# 4. Test on TestPyPI (recommended)
./scripts/publish_package.sh --test

# 5. Publish to PyPI (production)
./scripts/publish_package.sh

# 6. Tag release
VERSION=$(cat src/muxi/.version)
git tag "v${VERSION}" && git push origin "v${VERSION}"
```

---

## ✅ Pre-Release Checklist

- [ ] Version updated in `src/muxi/.version`
- [ ] CHANGELOG.md updated
- [ ] All tests passing: `pytest tests/`
- [ ] Git clean: `git status`
- [ ] Dependencies verified in `pyproject.toml`

---

## 📊 File Structure

```
runtime/
├── src/muxi/              # Main package
│   └── .version          # Version file (REQUIRED)
├── schemas/              # Included in distribution
├── migrations/           # Included in distribution
├── pyproject.toml        # Package metadata
├── setup.py              # Build configuration
├── MANIFEST.in           # File inclusion rules
├── README.md             # PyPI description
├── LICENSE               # Elastic License 2.0
└── scripts/
    ├── build_package.sh   # Build wheel + sdist
    └── publish_package.sh # Upload to PyPI
```

---

## 🔐 PyPI Credentials Setup

Create `~/.pypirc`:

```ini
[testpypi]
username = __token__
password = pypi-AgEIcH...  # TestPyPI token

[pypi]
username = __token__
password = pypi-AgEIcH...  # Production PyPI token
```

Get tokens:
- TestPyPI: https://test.pypi.org/manage/account/token/
- PyPI: https://pypi.org/manage/account/token/

---

## 🚀 Publishing Workflow

### Step-by-Step

1. **Update Version**
   ```bash
   echo "0.20251029.1" > src/muxi/.version
   ```

2. **Update CHANGELOG.md**
   ```markdown
   ## [0.20251029.1] - 2025-10-29
   ### Added
   - New feature X
   ### Fixed
   - Bug Y
   ```

3. **Commit Changes**
   ```bash
   git add .
   git commit -m "chore: prepare release 0.20251029.1"
   git push
   ```

4. **Build Package**
   ```bash
   ./scripts/build_package.sh
   # Creates dist/muxi-0.20251029.1-py3-none-any.whl
   #         dist/muxi-0.20251029.1.tar.gz
   ```

5. **Test Build**
   ```bash
   python3 -m venv test_env
   source test_env/bin/activate
   pip install dist/muxi-*.whl
   python -c "from muxi import Formation; print('OK')"
   deactivate && rm -rf test_env
   ```

6. **Upload to TestPyPI**
   ```bash
   ./scripts/publish_package.sh --test
   # View at: https://test.pypi.org/project/muxi/
   ```

7. **Test from TestPyPI**
   ```bash
   pip install --index-url https://test.pypi.org/simple/ \
               --extra-index-url https://pypi.org/simple/ \
               muxi
   ```

8. **Publish to PyPI**
   ```bash
   ./scripts/publish_package.sh
   # ⚠️ PRODUCTION - Cannot be undone!
   ```

9. **Tag Release**
   ```bash
   git tag "v0.20251029.1"
   git push origin "v0.20251029.1"
   ```

10. **Create GitHub Release**
    - Go to: https://github.com/muxi-ai/runtime/releases/new
    - Tag: `v0.20251029.1`
    - Title: `MUXI Runtime v0.20251029.1`
    - Description: Copy from CHANGELOG.md

---

## 🐛 Common Issues

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError: tomli` | `pip install tomli` |
| `HTTPError: 403 Forbidden` | Check API token in `~/.pypirc` |
| `File already exists` | Cannot re-upload same version, increment in `.version` |
| Build fails | `pip install --upgrade build twine` |
| Dependencies fail | Verify all packages exist on PyPI |

---

## 📋 What Gets Included?

**Included:**
- `src/muxi/` - All Python code
- `src/muxi/.version` - Version file
- `schemas/` - YAML schemas
- `migrations/` - Database migrations
- `README.md`, `LICENSE`, `CHANGELOG.md`

**Excluded:**
- `tests/`, `e2e/` - Test files
- `docs/` - Documentation (on website)
- `examples/` - Examples (separate repo)
- `sif/`, `docker-compose.yaml` - Container files
- `scripts/`, `utils/` - Development tools

See `MANIFEST.in` for full rules.

---

## 🔢 Version Format (ScalVer)

```
0.YYYYMMDD.N
│ │        └─ Release # for that day (1, 2, 3...)
│ └──────── Date (YYYYMMDD)
└────────── Major version (0 before 1.0)
```

Examples:
- `0.20251029.1` - First release on Oct 29, 2025
- `0.20251029.2` - Second release same day
- `0.20251030.1` - First release Oct 30, 2025

---

## 🔗 Quick Links

- **PyPI**: https://pypi.org/project/muxi/
- **TestPyPI**: https://test.pypi.org/project/muxi/
- **GitHub**: https://github.com/muxi-ai/runtime
- **Docs**: https://muxi.org/docs

---

## 📖 Full Guide

For detailed documentation, see: **[PYPI_DISTRIBUTION.md](./PYPI_DISTRIBUTION.md)**
