# MUXI SIF Quick Start

**Get up and running with MUXI Singularity containers in 5 minutes**

---

## Prerequisites

```bash
# Install Apptainer (macOS)
brew install apptainer

# Install Apptainer (Ubuntu/Debian)
sudo add-apt-repository -y ppa:apptainer/ppa
sudo apt update && sudo apt install -y apptainer

# Verify
apptainer --version
```

---

## Build Your First SIF

```bash
# Clone MUXI Runtime
git clone https://github.com/muxi-ai/runtime
cd runtime

# Build basic runtime (~2GB, 10-15 minutes)
./build-sif.sh basic

# Or build production runtime with services (~3GB, 15-20 minutes)
./build-sif.sh production
```

---

## Test the Image

```bash
# Quick test
apptainer exec muxi-runtime.sif python -c "import muxi; print('✅ Works!')"

# Interactive shell
apptainer shell muxi-runtime.sif

# Check installed packages
apptainer exec muxi-runtime.sif pip list | grep muxi
```

---

## Run a Formation

```bash
# Create test formation
cat > formation.yaml <<EOF
schema: "1.0.0"
id: "hello"
llm:
  models:
    - text: "openai/gpt-4o-mini"
  api_keys:
    openai: "\${{ secrets.OPENAI_API_KEY }}"
agents:
  - id: "bot"
    name: "Hello Bot"
    system_message: "You are a friendly assistant."
EOF

# Run it
apptainer run \
    --bind ./formation.yaml:/formation.yaml \
    --env OPENAI_API_KEY=sk-your-key-here \
    muxi-runtime.sif \
    --formation /formation.yaml --port 8000

# Test in another terminal
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!", "user_id": "test"}'
```

---

## Deploy to MUXI Server

```bash
# 1. Copy SIF to server
scp muxi-runtime.sif user@server:/opt/muxi/

# 2. Update server config
# Edit ~/.muxi-server/config.yaml:
formations:
  runtime_type: "singularity"
  singularity_image: "/opt/muxi/muxi-runtime.sif"

# 3. Restart server
systemctl restart muxi-server

# 4. Deploy formation
tar czf formation.tar.gz formation.yaml
curl -X POST http://server:7890/rpc/formations/deploy \
  --data-binary @formation.tar.gz
```

---

## Common Commands

```bash
# Build image
apptainer build image.sif definition.def

# Run container
apptainer run image.sif

# Execute command
apptainer exec image.sif python script.py

# Shell access
apptainer shell image.sif

# Inspect image
apptainer inspect image.sif

# Run tests
apptainer test image.sif

# Background instance
apptainer instance start image.sif myinstance
apptainer instance list
apptainer instance stop myinstance
```

---

## Bind Mounts

```bash
# Single directory
apptainer run --bind /host/path:/container/path image.sif

# Multiple directories
apptainer run \
    --bind /data:/data:ro \
    --bind /logs:/logs:rw \
    --bind /config:/config:ro \
    image.sif

# Current directory (automatic)
apptainer run image.sif  # $HOME bound by default
```

---

## Environment Variables

```bash
# Pass variables
apptainer run --env KEY=value image.sif

# From file
apptainer run --env-file .env image.sif

# Clean environment
apptainer run --cleanenv image.sif
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Permission denied | Use `sudo` on Linux for build |
| Module not found | Check `PYTHONPATH` in container |
| Can't access files | Verify bind mounts with `--bind` |
| Out of memory | Increase Docker memory (8GB+) |
| Image too large | Clean up: `pip cache purge`, remove build deps |

---

## Performance Tips

✅ **DO:**
- Pin all dependency versions
- Clean up after install (apt, pip cache)
- Use `--cleanenv` for consistent behavior
- Test with `%test` section in .def file
- Use read-only bind mounts (`:ro`)

❌ **DON'T:**
- Use `latest` tags (use exact versions)
- Install unnecessary packages
- Run as root (create user)
- Forget to test after build
- Skip documentation

---

## Next Steps

1. **Read the full guide:** [SIF-GUIDE.md](./SIF-GUIDE.md)
2. **Try examples:** [examples/README.md](./examples/README.md)
3. **Integrate with server:** See server docs
4. **Optimize:** Review best practices in guide
5. **Deploy:** Use in production with monitoring

---

## Resources

- **Apptainer Docs:** https://apptainer.org/docs/
- **MUXI Docs:** https://muxi.org/docs
- **MUXI Runtime:** https://github.com/muxi-ai/runtime
- **MUXI Server:** https://github.com/muxi-ai/server
- **Get Help:** https://github.com/muxi-ai/runtime/discussions

---

**Questions?** Check [SIF-GUIDE.md](./SIF-GUIDE.md) for detailed documentation.

**Ready to build?** Run `./build-sif.sh` to get started! 🚀
