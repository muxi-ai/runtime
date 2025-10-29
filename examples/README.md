# MUXI Runtime Examples

This directory contains example formations and configurations for testing MUXI Runtime.

## Test Formation

**File:** `test-formation.yaml`

A simple formation for validating SIF builds and testing basic functionality.

### Usage

#### 1. Test with SIF Image Locally

```bash
# Build SIF image first (from runtime root)
cd ..
./build-sif.sh basic

# Test the formation
apptainer exec \
    --bind ./examples/test-formation.yaml:/formation.yaml \
    --bind $(pwd)/data:/data \
    --env OPENAI_API_KEY=sk-your-key-here \
    muxi-runtime.sif \
    python -m muxi.server run --formation /formation.yaml
```

#### 2. Test with MUXI Server

```bash
# Create formation bundle
tar czf test-formation.tar.gz test-formation.yaml

# Deploy to server
curl -X POST http://localhost:7890/rpc/formations/deploy \
  -H "Content-Type: application/gzip" \
  --data-binary @test-formation.tar.gz

# Test the formation
curl -X POST http://localhost:7890/api/test-assistant/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello! Please confirm you are running in a SIF container.",
    "user_id": "test-user"
  }'
```

#### 3. Interactive Testing

```bash
# Start formation server
apptainer run \
    --bind ./examples:/formations \
    --bind $(pwd)/data:/data \
    --env OPENAI_API_KEY=sk-your-key-here \
    muxi-runtime.sif \
    --formation /formations/test-formation.yaml \
    --port 8000

# In another terminal, test the endpoint
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is 2+2?",
    "user_id": "test-user"
  }'
```

## Expected Results

When working correctly, you should see:

1. **Formation loads successfully**
   ```
   ✅ Formation loaded: test-assistant
   ✅ Agent initialized: assistant
   ✅ Server started on port 8000
   ```

2. **Chat endpoint responds**
   ```json
   {
     "response": "I'm an AI assistant running in a Singularity container...",
     "agent_id": "assistant",
     "formation_id": "test-assistant"
   }
   ```

3. **Health check passes**
   ```bash
   curl http://localhost:8000/health
   # {"status": "healthy"}
   ```

## Troubleshooting

### Issue: "Module not found" errors

**Solution:**
```bash
# Verify MUXI is installed in the SIF
apptainer exec muxi-runtime.sif python -c "import muxi; print(muxi.__version__)"
```

### Issue: "Permission denied" accessing files

**Solution:**
```bash
# Check file permissions
ls -la examples/test-formation.yaml

# Make sure bind mounts are correct
apptainer run --bind ./examples:/formations:ro muxi-runtime.sif
#                                             ^^ read-only
```

### Issue: "API key not found"

**Solution:**
```bash
# Pass environment variables
apptainer run \
    --env OPENAI_API_KEY=sk-your-key \
    --env ANTHROPIC_API_KEY=sk-ant-your-key \
    muxi-runtime.sif

# Or use env file
apptainer run --env-file .env muxi-runtime.sif
```

## More Examples

For more complex examples, see:
- [MUXI Formations Gallery](https://muxi.org/formations)
- [MUXI Documentation](https://muxi.org/docs)
- [MUXI GitHub](https://github.com/muxi-ai/runtime/tree/main/examples)

## Need Help?

- 📖 Read the [SIF-GUIDE.md](../SIF-GUIDE.md)
- 💬 Ask questions in [GitHub Discussions](https://github.com/muxi-ai/runtime/discussions)
- 🐛 Report issues at [GitHub Issues](https://github.com/muxi-ai/runtime/issues)
