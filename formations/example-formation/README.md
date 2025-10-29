# Example Formation

This is an example formation showing how to use MUXI's encrypted secrets system.

## Setup Secrets

MUXI uses encrypted secrets stored in `secrets.enc` and `.key` files.

### Add Your API Key

```bash
# From the formation directory
cd formations/example-formation

# Run the add_secret utility
python ../../utils/add_secret.py

# When prompted:
#   Formation: . (current directory)
#   Key name: OPENAI_API_KEY
#   Value: sk-your-actual-key-here
```

This creates:
- `secrets.enc` - Encrypted secrets file
- `.key` - Encryption key (keep this secure!)
- `secrets.example` - Template showing what secrets are needed (auto-generated)

### In Your Formation YAML

Reference secrets using the template syntax:

```yaml
llm:
  api_keys:
    openai: "${{ secrets.OPENAI_API_KEY }}"
```

## Running with Docker

Once secrets are configured:

```bash
# From repository root
cd ../../

# Run with docker-compose
docker compose up muxi

# The formation directory (including secrets) is automatically mounted
```

## Security Notes

- ✅ `secrets.enc` - Safe to commit (encrypted)
- ⚠️  `.key` - **NEVER commit this!** (in .gitignore)
- ✅ `secrets.example` - Safe to commit (no values)

The `.key` file must be kept secure and separate from version control.

## More Info

See:
- `utils/add_secret.py` - Add/update secrets
- `utils/delete_secret.py` - Remove secrets  
- `e2e/assets/list_secrets.py` - List all secrets
- `docs/secrets-management.md` - Complete documentation
