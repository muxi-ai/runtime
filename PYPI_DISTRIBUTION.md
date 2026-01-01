# PyPI Distribution Guide

Complete guide for building and publishing MUXI Runtime to PyPI.

## 📦 Overview

MUXI Runtime is distributed on PyPI under the package name `muxi`. Users can install it with:

```bash
pip install muxi
```

## 🏗️ Package Structure

The distribution includes:

- **Core Python package** (`src/muxi/`) - All runtime code
- **Version file** (`src/muxi/.version`) - Version tracking for runtime
- **Schema files** (`schemas/`) - Formation YAML validation schemas
- **Prompt templates** (`src/muxi/formation/prompts/`) - LLM prompt templates
- **Built-in MCP servers** (`src/muxi/services/mcp/built_in/`) - File generation and other built-ins
- **SQLite extensions** (`src/muxi/extensions/loadable/`) - Native extensions (if present)
- **Migration scripts** (`migrations/`) - Database schema migrations
- **Documentation** - README, LICENSE, CHANGELOG, etc.

Files controlled by `MANIFEST.in` - see that file for inclusion/exclusion rules.

---

## 🔧 Prerequisites

### 1. Python Environment

```bash
# Ensure you have Python 3.10+
python3 --version

# Install build tools (if not already installed)
pip install build twine
```

### 2. PyPI Account & Credentials

**For Testing (Optional but Recommended):**
1. Create account at [test.pypi.org](https://test.pypi.org/account/register/)
2. Create API token at [test.pypi.org/manage/account/token/](https://test.pypi.org/manage/account/token/)
3. Save credentials in `~/.pypirc`:

```ini
[testpypi]
username = __token__
password = pypi-AgEIcHlwaS5vcmc...  # Your TestPyPI token
```

**For Production:**
1. Create account at [pypi.org](https://pypi.org/account/register/)
2. Create API token at [pypi.org/manage/account/token/](https://pypi.org/manage/account/token/)
3. Save credentials in `~/.pypirc`:

```ini
[pypi]
username = __token__
password = pypi-AgEIcHlwaS5vcmc...  # Your PyPI token
```

---

## 📋 Pre-Release Checklist

Before building and publishing, ensure:

- [ ] **Version updated** - Update `src/muxi/.version` with new version (ScalVer: `0.YYYYMMDD.N`)
- [ ] **CHANGELOG updated** - Document all changes in `CHANGELOG.md`
- [ ] **Tests passing** - Run full test suite: `pytest tests/`
- [ ] **Dependencies current** - Verify `pyproject.toml` dependencies are up to date
- [ ] **README current** - Update README.md with any new features
- [ ] **Documentation complete** - Ensure all docs reflect the new version
- [ ] **Git clean** - Commit all changes: `git status` should be clean
- [ ] **Git tagged** - Ready to tag release after successful publish

---

## 🚀 Build Process

### Step 1: Build Distribution Packages

The build script creates both wheel (`.whl`) and source distribution (`.tar.gz`):

```bash
./scripts/build_package.sh
```

This will:
1. Clean previous builds (`dist/`, `build/`, `*.egg-info`)
2. Verify build dependencies (install if missing)
3. Build packages using `python -m build`
4. Verify package integrity with `twine check`
5. Display generated files in `dist/`

**Expected output:**

```
Generated packages:
-rw-r--r-- 1 user staff  245K Jan 29 10:00 muxi-0.20251029.1-py3-none-any.whl
-rw-r--r-- 1 user staff  198K Jan 29 10:00 muxi-0.20251029.1.tar.gz
```

### Step 2: Test Locally (Recommended)

Before publishing, test the wheel locally:

```bash
# Create a fresh virtual environment
python3 -m venv test_env
source test_env/bin/activate

# Install the wheel
pip install dist/muxi-0.YYYYMMDD.N-py3-none-any.whl

# Verify installation
python3 -c "from muxi.runtime import Formation; print('✓ Import successful')"

# Test version
python3 -c "from muxi.runtime.utils.version import get_version; print(f'Version: {get_version()}')"

# Deactivate and clean up
deactivate
rm -rf test_env
```

---

## 🧪 Publishing to TestPyPI (Recommended First)

Always test on TestPyPI before publishing to production PyPI:

```bash
./scripts/publish_package.sh --test
```

This uploads to [test.pypi.org](https://test.pypi.org) where you can verify the package without affecting production.

**Test installation from TestPyPI:**

```bash
# Install from TestPyPI
pip install --index-url https://test.pypi.org/simple/ \
            --extra-index-url https://pypi.org/simple/ \
            muxi

# Note: --extra-index-url allows installing dependencies from main PyPI
```

**Verify on TestPyPI:**
- Visit: https://test.pypi.org/project/muxi/
- Check metadata, description, links
- Verify version number
- Test README rendering

---

## 🚀 Publishing to PyPI (Production)

Once verified on TestPyPI, publish to production PyPI:

```bash
./scripts/publish_package.sh
```

⚠️ **WARNING**: This publishes to production PyPI and **CANNOT be undone**!

The script will:
1. Show what will be uploaded
2. Ask for confirmation (you must type "yes")
3. Upload to PyPI
4. Display success message with links

**Post-Publish Steps:**

```bash
# 1. Tag the release in Git
VERSION=$(cat src/muxi/.version)
git tag "v${VERSION}"
git push origin "v${VERSION}"

# 2. Create GitHub release
# Go to: https://github.com/muxi-ai/runtime/releases/new
# Use tag: v0.YYYYMMDD.N
# Copy CHANGELOG section as release notes

# 3. Verify on PyPI
# Visit: https://pypi.org/project/muxi/
```

---

## 📊 Verification Checklist

After publishing, verify:

- [ ] **PyPI page loads** - https://pypi.org/project/muxi/
- [ ] **Version correct** - Matches `src/muxi/.version`
- [ ] **README renders** - Markdown displays correctly
- [ ] **Links work** - All project URLs functional
- [ ] **Installation works** - `pip install muxi` succeeds
- [ ] **Import works** - `from muxi.runtime import Formation` succeeds
- [ ] **Dependencies install** - All required packages install correctly
- [ ] **GitHub tagged** - Git tag exists: `git tag -l`
- [ ] **GitHub release created** - Release notes published

---

## 🔄 Version Numbering (ScalVer)

MUXI uses **ScalVer** (Semantic Calendar Versioning):

```
0.YYYYMMDD.N
│ │        └─── Release number for that day (starts at 1)
│ └──────────── Date: YYYY = year, MM = month, DD = day
└────────────── Major version (0 = pre-1.0)
```

**Examples:**
- `0.20251029.1` - First release on October 29, 2025
- `0.20251029.2` - Second release on October 29, 2025
- `0.20251030.1` - First release on October 30, 2025

**To update version:**

```bash
# Edit the version file
echo "0.$(date +%Y%m%d).1" > src/muxi/.version

# Or manually
echo "0.20251029.1" > src/muxi/.version
```

---

## 🛠️ Troubleshooting

### Build Fails

**Problem:** `ModuleNotFoundError: No module named 'tomli'`

**Solution:**
```bash
pip install tomli  # For Python 3.10
# Python 3.11+ has tomllib built-in
```

---

**Problem:** `error: invalid command 'bdist_wheel'`

**Solution:**
```bash
pip install wheel
```

---

### Upload Fails

**Problem:** `HTTPError: 403 Forbidden`

**Solution:** Check your API token in `~/.pypirc`. Ensure you're using a token, not a password.

---

**Problem:** `File already exists`

**Solution:** You cannot re-upload the same version. Increment the version number in `src/muxi/.version`.

---

**Problem:** `The user 'xxx' isn't allowed to upload to project 'muxi'`

**Solution:** Ensure you're using the correct PyPI account that has permissions for the `muxi` package.

---

### Installation Fails

**Problem:** `Could not find a version that satisfies the requirement muxi`

**Solution:**
- Ensure package published successfully
- Try `pip install --upgrade pip`
- Check PyPI status: https://status.python.org/

---

**Problem:** Dependencies fail to install

**Solution:**
- Check `pyproject.toml` dependencies are valid
- Ensure all packages exist on PyPI
- Verify version constraints are not too strict

---

## 📝 Additional Notes

### File Inclusion

Files are included/excluded based on:
1. `MANIFEST.in` - Explicit include/exclude rules
2. `pyproject.toml` - Package data patterns
3. Default behaviors - Python files, README, LICENSE auto-included

### Package Size

Keep package size reasonable:
- Current size: ~250 KB wheel, ~200 KB source
- Exclude test files, docs, examples (users get from GitHub)
- Include only essential runtime files

### Licensing

MUXI Runtime uses **Elastic License 2.0**:
- ✅ Free to use, modify, distribute
- ✅ Commercial use allowed
- ❌ Cannot offer as a hosted/managed SaaS service
- ❌ Cannot circumvent license key functionality

See `LICENSE` for full terms.

---

## 🔗 Useful Links

- **PyPI Project Page**: https://pypi.org/project/muxi/
- **PyPI Packaging Guide**: https://packaging.python.org/
- **Twine Documentation**: https://twine.readthedocs.io/
- **PEP 621** (pyproject.toml): https://peps.python.org/pep-0621/
- **PEP 517** (build backend): https://peps.python.org/pep-0517/

---

## 📧 Support

Questions about PyPI distribution?
- **GitHub Issues**: https://github.com/muxi-ai/runtime/issues
- **GitHub Discussions**: https://github.com/muxi-ai/runtime/discussions
- **Email**: ran@aroussi.com
