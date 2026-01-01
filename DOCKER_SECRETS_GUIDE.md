# MUXI Secrets Management for Docker

**Complete guide to using MUXI's encrypted secrets system with Docker Compose**

---

## 🔐 How MUXI Handles Secrets

MUXI uses **encrypted secrets files**, NOT environment variables or `.env` files!

### Key Concepts

1. **Formation-Level Secrets**: Each formation has its own encrypted secrets
2. **Encrypted Storage**: Secrets stored in `secrets.enc` (encrypted)
3. **Decryption Key**: `.key` file decrypts the secrets
4. **Never in Environment**: API keys never go in environment variables

---

## 📁 File Structure

```
formations/
└── my-formation/
    ├── formation.afs      # Formation config
    ├── secrets.enc         # Encrypted secrets ✅ (safe to commit)
    ├── .key                # Decryption key ⚠️  (NEVER commit!)
    └── secrets             # Template (auto-generated)
```

**Security:**
- ✅ `secrets.enc` - Encrypted, safe to share
- ⚠️  `.key` - Must be kept secret (in .gitignore)
- ✅ `secrets` - Template only, no values

---

## 🚀 Quick Start

### Step 1: Create Formation

```bash
mkdir -p formations/my-agent
cd formations/my-agent

cat > formation.afs << 'EOF'
schema: "1.0.0"
id: my-agent

llm:
  api_keys:
    openai: "${{ secrets.OPENAI_API_KEY }}"
  models:
    - text: "openai/gpt-4o-mini"

agents:
  - id: assistant
    name: "My Assistant"
    system_message: "You are helpful."
EOF
```

### Step 2: Add Secrets

```bash
# From your formation directory
python ../../utils/add_secret.py

# Interactive prompts:
#   Formation directory: . (or leave empty for current)
#   Key name: OPENAI_API_KEY
#   Value: sk-your-actual-key-here
```

This creates `secrets.enc` and `.key` files.

### Step 3: Run with Docker

```bash
# Return to runtime directory
cd ../../

# Start MUXI - secrets are automatically loaded!
docker compose up muxi
```

Done! MUXI reads `secrets.enc` using `.key` at startup.

---

## 🔧 Managing Secrets

### Add a Secret

```bash
cd formations/my-formation
python ../../utils/add_secret.py

# Prompts:
#   Formation: . (current directory)
#   Key name: ANTHROPIC_API_KEY
#   Value: sk-ant-your-key
```

### List Secrets

```bash
cd formations/my-formation
python ../../e2e/assets/list_secrets.py
```

Output:
```
Secrets in formations/my-formation:
  - OPENAI_API_KEY: sk-***************************
  - ANTHROPIC_API_KEY: sk-ant-*********************
```

### Delete a Secret

```bash
cd formations/my-formation
python ../../utils/delete_secret.py

# Prompts:
#   Formation: . (current directory)
#   Key name: ANTHROPIC_API_KEY
```

### Update a Secret

Just add it again - overwrites the old value:

```bash
python ../../utils/add_secret.py
# Use same key name with new value
```

---

## 📝 Using Secrets in Formation YAML

Reference secrets using the template syntax:

```yaml
llm:
  api_keys:
    openai: "${{ secrets.OPENAI_API_KEY }}"
    anthropic: "${{ secrets.ANTHROPIC_API_KEY }}"
    google: "${{ secrets.GOOGLE_API_KEY }}"

mcp:
  servers:
    - name: "github"
      command: "mcp-github"
      env:
        GITHUB_TOKEN: "${{ secrets.GITHUB_TOKEN }}"
```

**Template Syntax**: `${{ secrets.KEY_NAME }}`

---

## 🐳 Docker Integration

### How It Works

1. Docker Compose mounts your `formations/` directory
2. Each formation directory includes `secrets.enc` and `.key`
3. MUXI runtime reads and decrypts secrets on startup
4. Secrets are used to populate the formation configuration

### What Gets Mounted

```yaml
# In docker-compose.yaml
volumes:
  - ${FORMATIONS_DIR:-./formations}:/formations:ro
```

This mounts:
- `formations/my-agent/formation.afs`
- `formations/my-agent/secrets.enc`
- `formations/my-agent/.key`

All automatically!

---

## 🔒 Security Best Practices

### DO ✅

- Keep `.key` files secure and backed up separately
- Add `.key` to `.gitignore` (already done)
- Commit `secrets.enc` (it's encrypted)
- Commit `secrets` (template only)
- Use different `.key` files per environment
- Share `secrets.enc` with team (key separately)

### DON'T ❌

- Never commit `.key` files
- Never put API keys in environment variables
- Never share `.key` via insecure channels
- Never hard-code secrets in YAML
- Never use same `.key` across environments

---

## 🌍 Multi-Environment Setup

### Development
```
formations/my-agent-dev/
├── formation.afs
├── secrets.enc       # Dev API keys
└── .key              # Dev key
```

### Production
```
formations/my-agent-prod/
├── formation.afs
├── secrets.enc       # Prod API keys (different!)
└── .key              # Prod key (different!)
```

Different `.key` means different encryption, even if you commit both `secrets.enc` files.

---

## 🔄 Team Workflow

### Sharing Formation with Team

**Step 1: Developer creates formation**
```bash
# Create formation and add secrets locally
cd formations/new-feature
python ../../utils/add_secret.py
# Add OPENAI_API_KEY

# Commit encrypted secrets (NOT .key!)
git add formation.afs secrets.enc secrets
git commit -m "Add new feature formation"
git push
```

**Step 2: Teammate pulls formation**
```bash
# Pull the changes
git pull

# They need the .key file (shared securely, NOT via git)
# Get .key via: 1Password, AWS Secrets Manager, secure chat, etc.
# Put it in: formations/new-feature/.key

# Now they can run it
docker compose up muxi
```

**Secure Key Sharing Methods:**
- 1Password shared vaults
- AWS Secrets Manager
- HashiCorp Vault
- Encrypted email
- Secure messaging (Signal, etc.)
- Physical transfer (USB, etc.)

---

## 🛠️ Troubleshooting

### Error: "Missing .key file"

```
Error: Could not find .key file in formations/my-agent/
```

**Fix:** Create the `.key` file:
```bash
cd formations/my-agent
python ../../utils/add_secret.py
# This will create .key if it doesn't exist
```

### Error: "Invalid key or corrupted secrets.enc"

```
Error: Failed to decrypt secrets.enc
```

**Fix:** Wrong `.key` file or corrupted `secrets.enc`:
```bash
# Regenerate from scratch
rm secrets.enc .key
python ../../utils/add_secret.py
# Re-add all secrets
```

### Error: "Secret not found: OPENAI_API_KEY"

```
Error: Secret OPENAI_API_KEY not found in secrets.enc
```

**Fix:** Add the secret:
```bash
cd formations/my-agent
python ../../utils/add_secret.py
# Add OPENAI_API_KEY
```

### Verify Secrets are Loaded

```bash
# List secrets (shows masked values)
cd formations/my-agent
python ../../e2e/assets/list_secrets.py
```

---

## 💡 Advanced Usage

### Multiple API Keys

```yaml
llm:
  api_keys:
    openai: "${{ secrets.OPENAI_API_KEY }}"
    anthropic: "${{ secrets.ANTHROPIC_API_KEY }}"
    openai_backup: "${{ secrets.OPENAI_API_KEY_2 }}"
```

Add each secret:
```bash
python utils/add_secret.py  # OPENAI_API_KEY
python utils/add_secret.py  # ANTHROPIC_API_KEY
python utils/add_secret.py  # OPENAI_API_KEY_2
```

### Custom Secret Names

You can use any name:
```bash
# Add custom secrets
python utils/add_secret.py
# Key: MY_CUSTOM_DATABASE_URL
# Value: postgresql://...

# Use in formation:
database:
  url: "${{ secrets.MY_CUSTOM_DATABASE_URL }}"
```

### Conditional Secrets

Some secrets may be optional:
```yaml
llm:
  api_keys:
    # Required
    openai: "${{ secrets.OPENAI_API_KEY }}"

    # Optional - only needed for certain features
    anthropic: "${{ secrets.ANTHROPIC_API_KEY || '' }}"
```

---

## 📚 Related Documentation

- `utils/add_secret.py` - Add/update secrets utility
- `utils/delete_secret.py` - Delete secrets utility
- `e2e/assets/list_secrets.py` - List secrets utility
- `docs/secrets-management.md` - Detailed MUXI secrets documentation
- `DOCKER_COMPOSE_GUIDE.md` - Docker Compose usage
- `formations/example-formation/README.md` - Example setup

---

## 🎯 Summary

**Remember:**
1. ✅ Secrets go in `secrets.enc` (encrypted, per-formation)
2. ⚠️  `.key` is required to decrypt (keep it secure!)
3. ❌ Never use environment variables for API keys
4. ✅ Use `python utils/add_secret.py` to manage secrets
5. ✅ Reference with `${{ secrets.KEY_NAME }}` in YAML
6. ✅ Docker automatically mounts formation directories

**That's it!** MUXI's secrets system keeps your API keys secure and encrypted. 🔐

---

**Need help?** Check `DOCKER_COMPOSE_GUIDE.md` for full Docker documentation.
