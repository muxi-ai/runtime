# MUXI Runtime - Server Integration Guide

## Overview

This guide documents how MUXI Server should integrate with the versioned MUXI Runtime Docker/SIF images to execute formations.

## Architecture

```
MUXI Server
    ↓
Formation Registry (version pinning)
    ↓
Runtime Resolution (0.2025 → 0.2025.0)
    ↓
SIF Execution (Singularity)
    ↓
Formation API Server (localhost:PORT)
```

## Runtime Distribution

### File Naming Convention

Server expects versioned SIF files with platform suffixes:

```
muxi-runtime-{version}-linux-{arch}.sif          # default
muxi-runtime-{version}-pytorch-linux-{arch}.sif  # pytorch
muxi-runtime-{version}-cuda-linux-{arch}.sif     # cuda (experimental)

Examples:
  muxi-runtime-0.20260422.0-linux-amd64.sif
  muxi-runtime-0.20260422.0-linux-arm64.sif
  muxi-runtime-0.20260422.0-pytorch-linux-amd64.sif
```

### Storage Location

```
~/.muxi/server/runtimes/
├── muxi-runtime-0.2025.0-linux-amd64.sif
├── muxi-runtime-0.2024.12-linux-amd64.sif
└── muxi-runtime-0.2024.11-linux-amd64.sif
```

### Building SIF Files

```bash
# In runtime repository (works on Linux and macOS)
./scripts/build/runtime.sh            # Build Docker image (default variant)
./scripts/build/sif.sh                # Convert to SIF
# Creates: sif-builds/muxi-runtime-{version}-linux-amd64.sif
```

`sif.sh` detects `apptainer` or `singularity` automatically. If neither is installed locally
(typical on macOS), it falls back to the Docker-wrapped `ghcr.io/muxi-ai/runtime-runner`
converter — no manual `docker save` required.

**Variant-aware builds:**
```bash
./scripts/build/runtime.sh --variant pytorch && ./scripts/build/sif.sh --variant pytorch
./scripts/build/runtime.sh --variant cuda   && ./scripts/build/sif.sh --variant cuda    # experimental
```

**Force architecture:**
```bash
./scripts/build/runtime.sh --platform linux/amd64
./scripts/build/sif.sh --arch amd64
```

> On macOS and Windows the correct SIF arch is always `linux-amd64` regardless of host CPU.
> `linux-arm64` SIFs only apply on native arm64 Linux hosts (e.g. AWS Graviton).

## Formation Directory Structure

Server manages formations with version directories:

```
~/.muxi/server/formations/{formation-id}/
├── current/                          ← Active version
│   ├── formation.afs                ← Formation configuration
│   ├── .key                          ← Encryption key
│   ├── secrets.enc                   ← Encrypted secrets
│   ├── agents/                       ← Agent definitions
│   ├── mcp/                          ← MCP servers
│   ├── a2a/                          ← A2A services
│   └── knowledge/                    ← Knowledge files (confined)
├── previous/                         ← Backup for rollback
│   └── (same structure)
└── version.json                      ← Version metadata
```

**Key Points:**
- Everything is self-contained in the formation directory
- Knowledge files must be within formation directory (security)
- Single mount point for Singularity bind

## Server Execution Pattern

### Phase 2 Command (YAML-based formations)

```bash
apptainer exec --writable-tmpfs \
  --bind {formation-dir}/current:/formation \
  ~/.muxi/server/runtimes/muxi-runtime-{version}-linux-{arch}.sif \
  python -m muxi.runtime.utils.run_formation \
  /formation/formation.afs \
  --port {allocated-port} \
  --host 127.0.0.1
```

`--writable-tmpfs` is required because the SIF rootfs is read-only; without it the
runtime fails when trying to create `~/.muxi/default/memory`.

### Detailed Example

```bash
# Formation: my-chatbot (version: 0.20260422.0)
# Allocated port: 8001

apptainer exec --writable-tmpfs \
  --bind ~/.muxi/server/formations/my-chatbot/current:/formation \
  ~/.muxi/server/runtimes/muxi-runtime-0.20260422.0-linux-amd64.sif \
  python -m muxi.runtime.utils.run_formation \
  /formation/formation.afs \
  --port 8001 \
  --host 127.0.0.1
```

**Result:**
- Formation API server binds to `127.0.0.1:8001`
- Server proxies requests: `http://server:7890/api/my-chatbot/*` → `http://127.0.0.1:8001/*`
- Knowledge files accessible at `/formation/knowledge/`

### Environment Variables (Optional)

While CLI args are preferred, environment variables are also supported:

```bash
singularity exec \
  --env PORT=8001 \
  --env HOST=127.0.0.1 \
  --bind ~/.muxi/server/formations/my-chatbot/current:/formation \
  ~/.muxi/server/runtimes/muxi-runtime-0.2025.0-linux-amd64.sif \
  python -m muxi.runtime.utils.run_formation /formation/formation.afs
```

**Recommendation:** Use CLI args for explicitness and debuggability.

## Version Resolution

### Formation Runtime Specification

Formations specify runtime version in `formation.afs`:

```yaml
schema: "1.0.0"
id: my-formation
runtime: "0.2025.0"    # Exact version
# OR
runtime: "0.2025"      # Latest 0.2025.x
# OR
runtime: "0"           # Latest 0.x.x
# OR
runtime: "latest"      # Absolute latest
```

### Server Resolution Logic

```go
// Example from server/src/pkg/runtime/resolver.go

// User specifies: "0.2025"
resolver := NewResolver([]string{
    "0.2025.0",
    "0.2025.1",
    "0.2024.12",
})

version := resolver.Resolve("0.2025")  // Returns: "0.2025.1" (latest 0.2025.x)

// Construct SIF path
sifPath := fmt.Sprintf(
    "~/.muxi/server/runtimes/muxi-runtime-%s-%s.sif",
    version,
    getPlatform(),
)
// Result: ~/.muxi/server/runtimes/muxi-runtime-0.2025.1-linux-amd64.sif
```

### Version Pinning on Deploy

When a formation is deployed:
1. Server resolves version constraint → exact version
2. Exact version stored in formation metadata
3. Formation always runs on this exact version until redeployed
4. Ensures stability even when new runtime versions are released

## CLI Arguments Reference

### Required Arguments

```bash
python -m muxi.runtime.utils.run_formation <formation-path>
```

- `formation-path`: Absolute path to formation.afs file

### Optional Arguments

```bash
--port PORT              # Port to bind server (overrides formation.afs)
--host HOST              # Host to bind server (overrides formation.afs, default: 127.0.0.1)
```

### Argument Precedence

1. CLI arguments (highest priority)
2. Environment variables
3. formation.afs configuration (lowest priority)

**Example:**
```yaml
# formation.afs specifies:
server:
  port: 3000
  host: 0.0.0.0

# Server overrides with CLI:
--port 8001 --host 127.0.0.1

# Result: Server binds to 127.0.0.1:8001
```

## Security Considerations

### 1. Formation Binding

Formations MUST bind to `127.0.0.1` (localhost):
- Server enforces this via `--host 127.0.0.1`
- Prevents direct external access to formations
- All requests go through server proxy

### 2. Knowledge Path Confinement

Knowledge files are restricted to formation directory:
- Absolute paths rejected (fail-fast)
- Parent directory traversal rejected (`..`)
- Ensures formations are self-contained
- Single mount point for security

### 3. Singularity Isolation

Use Singularity's isolation features:
```bash
singularity exec \
  --contain \                          # Container mode (isolated)
  --no-home \                          # Don't mount home directory
  --bind /tmp:/tmp \                   # Explicit temp binding
  --bind {formation-dir}:/formation \  # Only formation access
  {sif-path} \
  python -m muxi.runtime.utils.run_formation /formation/formation.afs
```

## Server Code Integration

### Formation Spawning (pkg/process/spawn.go)

```go
func (pm *ProcessManager) SpawnFormation(formation *Formation) error {
    // 1. Resolve runtime version
    version, err := pm.runtimeResolver.Resolve(formation.RuntimeVersion)
    if err != nil {
        return fmt.Errorf("failed to resolve runtime: %w", err)
    }

    // 2. Construct SIF path
    sifPath := pm.runtimeDownloader.GetSIFPath(version)
    if !fileExists(sifPath) {
        return fmt.Errorf("runtime not found: %s", sifPath)
    }

    // 3. Construct formation path
    formationPath := filepath.Join(
        pm.formationsDir,
        formation.ID,
        "current",
        "formation.afs",
    )

    // 4. Build Apptainer command (--writable-tmpfs required: SIF rootfs is read-only)
    cmd := exec.Command("apptainer", "exec", "--writable-tmpfs",
        "--bind", fmt.Sprintf("%s:/formation", filepath.Dir(formationPath)),
        sifPath,
        "python", "-m", "muxi.runtime.utils.run_formation",
        "/formation/formation.afs",
        "--port", fmt.Sprintf("%d", formation.Port),
        "--host", "127.0.0.1",
    )

    // 5. Set up logging
    cmd.Stdout = formation.LogFile
    cmd.Stderr = formation.LogFile

    // 6. Start process
    if err := cmd.Start(); err != nil {
        return fmt.Errorf("failed to start formation: %w", err)
    }

    formation.PID = cmd.Process.Pid
    return nil
}
```

### Health Check

After spawning, server should wait for formation to be ready. The health endpoint is
mounted under the `/v1` prefix:

```go
func (pm *ProcessManager) WaitForFormationReady(formation *Formation) error {
    url := fmt.Sprintf("http://127.0.0.1:%d/v1/health", formation.Port)

    for i := 0; i < 30; i++ {  // 30 second timeout
        resp, err := http.Get(url)
        if err == nil && resp.StatusCode == 200 {
            resp.Body.Close()
            return nil  // Formation ready!
        }
        time.Sleep(1 * time.Second)
    }

    return fmt.Errorf("formation failed to become ready within timeout")
}
```

## Testing

### Local Testing (without server)

```bash
# Build Docker image
cd /path/to/runtime
./scripts/build/runtime.sh

# Test directly
docker run --rm \
  -v /path/to/formation:/formation:ro \
  -e PORT=8000 -e HOST=0.0.0.0 \
  -p 8000:8000 \
  muxi-runtime:latest \
  /formation/formation.afs

# Access endpoints
curl http://localhost:8000/v1/health       # Health check
curl http://localhost:8000/docs            # Swagger UI
```

### SIF Testing (on Linux)

```bash
# Convert to SIF
./scripts/build/sif.sh

# Test SIF directly (--writable-tmpfs required: SIF rootfs is read-only)
apptainer exec --writable-tmpfs \
  --bind /path/to/formation:/formation \
  sif-builds/muxi-runtime-latest-linux-amd64.sif \
  python -m muxi.runtime.utils.run_formation \
  /formation/formation.afs \
  --port 8000 --host 127.0.0.1 &

# Wait for startup (~60s on first boot)
sleep 60

# Test endpoints
curl http://127.0.0.1:8000/v1/health      # Health check
curl http://127.0.0.1:8000/docs           # Swagger UI
```

## Deployment Workflow

### 1. Formation Deployment

```bash
# User deploys formation
muxi formation deploy my-chatbot.tar.gz

# Server extracts to:
~/.muxi/server/formations/my-chatbot/current/
├── formation.afs      # Specifies runtime: "0.2025"
├── .key
├── secrets.enc
├── agents/
├── knowledge/
└── ...
```

### 2. Runtime Resolution

```go
// Server reads formation.afs
runtime := "0.2025"  // From formation.afs

// Resolves to exact version
version := resolver.Resolve(runtime)  // "0.2025.0"

// Checks if SIF exists
sifPath := "~/.muxi/server/runtimes/muxi-runtime-0.2025.0-linux-amd64.sif"
if !exists(sifPath) {
    // Download from registry (future enhancement)
    // For now: fail with clear error message
    return fmt.Errorf("runtime %s not found", version)
}
```

### 3. Formation Spawning

```bash
# Server spawns formation (--writable-tmpfs required: SIF rootfs is read-only)
apptainer exec --writable-tmpfs \
  --bind ~/.muxi/server/formations/my-chatbot/current:/formation \
  ~/.muxi/server/runtimes/muxi-runtime-0.2025.0-linux-amd64.sif \
  python -m muxi.runtime.utils.run_formation \
  /formation/formation.afs \
  --port 8001 \
  --host 127.0.0.1
```

### 4. Health Check & Registration

```go
// Wait for formation to be ready
if err := pm.WaitForFormationReady(formation); err != nil {
    return err
}

// Register in proxy
proxy.AddFormation(formation.ID, formation.Port)
// Routes: http://server:7890/api/my-chatbot/* → http://127.0.0.1:8001/*
```

## Troubleshooting

### SIF Not Found

**Error:**
```
runtime 0.2025.0 not found at ~/.muxi/server/runtimes/muxi-runtime-0.2025.0-linux-amd64.sif
```

**Solution:**
```bash
# Build the runtime for the required version
cd /path/to/runtime
git checkout v0.2025.0
./scripts/build/runtime.sh
./scripts/build/sif.sh

# Copy to server
cp sif-builds/muxi-runtime-0.2025.0-linux-amd64.sif ~/.muxi/server/runtimes/
```

### Formation Fails to Start

**Check logs:**
```bash
# Server logs
tail -f ~/.muxi/server/logs/formation-my-chatbot.log

# Look for:
# - Dependency errors (should be rare now)
# - Knowledge path errors (absolute paths, ..)
# - Secret loading errors (.key missing)
# - Port binding errors (already in use)
```

### Knowledge Path Errors

**Error:**
```
[ FAIL ] Invalid knowledge path
         Absolute paths not allowed for knowledge sources: /data/docs
```

**Solution:**
Update formation.afs:
```yaml
# Wrong:
knowledge:
  sources:
    - path: "/data/docs"           # ❌ Absolute path
    - path: "../shared/docs"       # ❌ Parent traversal

# Correct:
knowledge:
  sources:
    - path: "knowledge/docs"       # ✅ Within formation
    - path: "docs/manuals"         # ✅ Anywhere in formation
```

## Migration from Phase 1

### Phase 1 (app.py-based)

```go
// OLD CODE
cmd := exec.Command("python", "app.py")
```

Formations shipped with `app.py` containing FastAPI server code.

### Phase 2 (YAML-based)

```go
// NEW CODE
cmd := exec.Command("apptainer", "exec", "--writable-tmpfs",
    "--bind", formationDir + ":/formation",
    sifPath,
    "python", "-m", "muxi.runtime.utils.run_formation",
    "/formation/formation.afs",
    "--port", port,
    "--host", "127.0.0.1",
)
```

Formations are pure configuration (YAML), runtime provides server.

### Backward Compatibility

If supporting both:
```go
// Check formation type
if hasAppPy(formationDir) {
    // Phase 1: python app.py
    cmd = buildPhase1Command(formationDir, port)
} else {
    // Phase 2: run_formation
    cmd = buildPhase2Command(formationDir, port, sifPath)
}
```

## Summary

**Server Requirements:**
1. Singularity/Apptainer installed
2. Runtime SIF files in `~/.muxi/server/runtimes/`
3. Formation directories in `~/.muxi/server/formations/{id}/current/`
4. Version resolution logic
5. Process spawning with Singularity exec
6. Health check after spawn
7. HTTP proxy to localhost ports

**Runtime Guarantees:**
1. Self-contained (2.42GB SIF file)
2. All dependencies included (OneLLM, providers, etc.)
3. Version is explicit (0.2025.0, not "latest")
4. CLI arguments for port/host control
5. Knowledge path security enforcement
6. Formation isolation (single mount point)

**Commands Server Uses:**
```bash
# List available runtimes
ls ~/.muxi/server/runtimes/muxi-runtime-*

# Spawn formation (--writable-tmpfs required: SIF rootfs is read-only)
apptainer exec --writable-tmpfs \
  --bind {formation-dir}:/formation {sif-path} \
  python -m muxi.runtime.utils.run_formation /formation/formation.afs \
  --port {port} --host 127.0.0.1

# Health check
curl http://127.0.0.1:{port}/v1/health

# View formation logs
tail -f ~/.muxi/server/logs/formation-{id}.log
```
