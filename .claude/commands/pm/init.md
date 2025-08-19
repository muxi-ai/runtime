---
allowed-tools: Bash
---

# PM Init

Initialize the PM system with required dependencies and GitHub authentication.

## Usage
```
/pm:init
```

## Instructions

### 1. Check GitHub CLI

```bash
echo "🔍 Checking GitHub CLI installation..."

if command -v gh &> /dev/null; then
  echo "✅ GitHub CLI found: $(gh --version | head -1)"
else
  echo "❌ GitHub CLI not found"
  echo ""
  echo "Please install GitHub CLI:"
  echo "  macOS:  brew install gh"
  echo "  Linux:  See https://github.com/cli/cli#installation"
  echo "  Windows: winget install GitHub.cli"
  echo ""
  exit 1
fi
```

### 2. Check GitHub Authentication

```bash
echo ""
echo "🔍 Checking GitHub authentication..."

if gh auth status &> /dev/null; then
  echo "✅ GitHub authenticated"
  gh auth status
else
  echo "⚠️  GitHub CLI not authenticated"
  echo ""
  echo "Starting authentication flow..."
  gh auth login
  
  # Verify authentication succeeded
  if gh auth status &> /dev/null; then
    echo "✅ Authentication successful"
  else
    echo "❌ Authentication failed. Please run: gh auth login"
    exit 1
  fi
fi
```

### 3. Install gh-sub-issue Extension

```bash
echo ""
echo "🔍 Checking gh-sub-issue extension..."

if gh extension list | grep -q "yahsan2/gh-sub-issue"; then
  echo "✅ gh-sub-issue already installed"
else
  echo "📦 Installing gh-sub-issue extension..."
  gh extension install yahsan2/gh-sub-issue
  
  if [ $? -eq 0 ]; then
    echo "✅ gh-sub-issue installed successfully"
  else
    echo "⚠️  Failed to install gh-sub-issue"
    echo "The PM system will work but without proper sub-issue support"
    echo "To install manually: gh extension install yahsan2/gh-sub-issue"
  fi
fi
```

### 4. Verify Repository

```bash
echo ""
echo "🔍 Checking current repository..."

if git rev-parse --git-dir > /dev/null 2>&1; then
  # Get repository info
  if git remote -v | grep -q github.com; then
    repo_url=$(git remote get-url origin)
    repo_name=$(echo $repo_url | sed -E 's/.*github.com[:/]([^/]+\/[^.]+).*/\1/')
    echo "✅ GitHub repository: $repo_name"
    
    # Test GitHub access to this repo
    if gh repo view $repo_name --json name > /dev/null 2>&1; then
      echo "✅ GitHub access confirmed"
    else
      echo "⚠️  Cannot access repository via GitHub CLI"
      echo "Make sure you have appropriate permissions"
    fi
  else
    echo "⚠️  Not a GitHub repository"
    echo "The PM system works best with GitHub repositories"
  fi
else
  echo "⚠️  Not in a git repository"
  echo "Initialize with: git init"
fi
```

### 5. Create PM Directories

```bash
echo ""
echo "📁 Setting up PM directories..."

# Create required directories
mkdir -p .claude/prds
mkdir -p .claude/epics 

echo "✅ Directory structure created"

# Add to .gitignore if needed
if [ -f .gitignore ]; then
  if ! grep -q "^.claude/epics/$" .gitignore; then
    echo "" >> .gitignore
    echo "# PM system local workspace" >> .gitignore
    echo ".claude/epics/" >> .gitignore
    echo "✅ Updated .gitignore"
  fi
else
  echo "# PM system local workspace" > .gitignore
  echo ".claude/epics/" >> .gitignore
  echo "✅ Created .gitignore"
fi
```

### 6. Summary

```bash
echo ""
echo "════════════════════════════════════════"
echo "   PM System Initialization Complete"
echo "════════════════════════════════════════"
echo ""
echo "✅ GitHub CLI installed and authenticated"
echo "✅ gh-sub-issue extension installed"
echo "✅ Directory structure created"
echo "✅ Repository configured"
echo ""
echo "Quick Start:"
echo "  1. Create a PRD:     /pm:prd-new feature-name"
echo "  2. Create an epic:   /pm:prd-parse feature-name"
echo "  3. Break into tasks: /pm:epic-decompose feature-name"
echo "  4. Sync to GitHub:   /pm:epic-sync feature-name"
echo "  5. Start work:       /pm:epic-start feature-name"
echo ""
echo "For help: /pm:help"
```

## Error Handling

If any critical component fails:
- GitHub CLI not installed → Exit with installation instructions
- Authentication fails → Exit with manual auth command
- gh-sub-issue fails → Continue with warning (fallback mode available)

## Important Notes

- This command is idempotent - safe to run multiple times
- Checks existing setup before making changes
- Non-destructive - won't overwrite existing configuration
- Works on macOS, Linux, and Windows (with appropriate package managers)
