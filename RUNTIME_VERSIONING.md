# MUXI Runtime Versioning for Server Integration

## Overview

MUXI Server manages multiple runtime versions to allow formations to pin to specific runtime versions and enable safe upgrades.

## Version Format

- **Current Version:** `0.2025.0` (from `src/muxi/.version`)
- **Format:** Semantic versioning (major.minor.patch)
- **Docker Tags:**
  - `muxi-runtime:0.2025.0` (specific version)
  - `muxi-runtime:latest` (convenience tag)

## SIF Naming Convention

MUXI Server expects SIF files to follow this naming pattern:

```
muxi-runtime-{version}-{platform}.sif
```

### Examples:
- `muxi-runtime-0.2025.0-linux-amd64.sif`
- `muxi-runtime-0.2025.0-linux-arm64.sif`
- `muxi-runtime-0.2025.0-darwin-arm64.sif`
- `muxi-runtime-0.2025.0-darwin-amd64.sif`

### Platform Format:
- **OS:** `linux`, `darwin` (macOS), `windows`
- **Architecture:** `amd64` (x86_64), `arm64` (aarch64)

## Build Process

### 1. Build Versioned Docker Image

```bash
# Automated build with version tags
./build-runtime.sh

# Manual build
VERSION=$(cat src/muxi/.version)
docker build -t muxi-runtime:$VERSION -t muxi-runtime:latest .
```

**Output:**
- `muxi-runtime:0.2025.0` (versioned)
- `muxi-runtime:latest` (convenience)

### 2. Convert to SIF

```bash
# Automated conversion with proper naming
./build-sif.sh

# Manual conversion
VERSION=$(cat src/muxi/.version)
PLATFORM="$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)"
docker save muxi-runtime:$VERSION -o muxi-runtime-$VERSION.tar
singularity build muxi-runtime-$VERSION-$PLATFORM.sif \
  docker-archive://muxi-runtime-$VERSION.tar
```

**Output:**
- `muxi-runtime-0.2025.0-linux-amd64.sif` (example)

### 3. Install for MUXI Server

```bash
# Copy to server's runtime directory
cp muxi-runtime-*.sif ~/.muxi/server/runtimes/

# Server will auto-register on next start
```

## Server Integration

### Formation Configuration

Formations specify which runtime version they need in `formation.yaml`:

```yaml
id: my-formation
name: My Formation
runtime: "0.2025.0"  # Exact version
# runtime: "0.2025"    # Latest 0.2025.x
# runtime: "0"         # Latest 0.x.x
# runtime: "latest"    # Absolute latest
```

### Server Behavior

1. **Formation Deploy:** Server reads `runtime` field from formation.yaml
2. **Version Resolution:** Resolves constraint to exact version (e.g., "0.2025" → "0.2025.0")
3. **SIF Lookup:** Finds `muxi-runtime-0.2025.0-{platform}.sif`
4. **Process Spawn:**
   ```bash
   singularity exec muxi-runtime-0.2025.0-linux-amd64.sif \
     python -m muxi.utils.run_formation /path/to/formation.yaml \
     --port 8001 --host 127.0.0.1
   ```

### Multi-Version Support

Server can run formations on different runtime versions simultaneously:

```
~/.muxi/server/runtimes/
├── muxi-runtime-0.2025.0-linux-amd64.sif
├── muxi-runtime-0.2024.12-linux-amd64.sif
└── muxi-runtime-0.2024.11-linux-amd64.sif

Active formations:
- formation-a (runtime: 0.2025.0)  ← Latest
- formation-b (runtime: 0.2024.12) ← Pinned for stability
- formation-c (runtime: latest)    ← Auto-upgrades
```

## CLI Arguments (Phase 2 Ready)

The runtime now accepts explicit CLI arguments for server integration:

```bash
python -m muxi.utils.run_formation formation.yaml \
  --port 8000 \
  --host 127.0.0.1
```

### Why CLI Args?
- **Explicit:** Everything visible in process list
- **Consistent:** Server controls all parameters
- **Override:** CLI args take precedence over formation.yaml
- **Debuggable:** Easy to see what's running

### Environment Variables (Still Supported)

```bash
# Both work - CLI args take precedence
PORT=8000 HOST=127.0.0.1 python -m muxi.utils.run_formation formation.yaml
python -m muxi.utils.run_formation formation.yaml --port 8000 --host 127.0.0.1
```

Server prefers CLI args for explicit control, but supports env vars for compatibility.

## Docker Entrypoint Integration

The `docker-entrypoint.sh` now uses CLI flags:

```bash
# Reads from PORT/HOST or FORMATION_PORT/FORMATION_HOST env vars
# Passes explicitly via CLI
exec python -m muxi.utils.run_formation "$FORMATION_PATH" \
  --port "$PORT" \
  --host "$HOST"
```

## Testing

### Test Docker Image

```bash
docker run -it --rm \
  -v $(pwd)/e2e/tests/1_foundation/formations/formation-base:/formation \
  -e PORT=8000 -e HOST=0.0.0.0 \
  -p 8000:8000 \
  muxi-runtime:0.2025.0 \
  /formation/formation.yaml
```

### Test SIF File

```bash
singularity exec muxi-runtime-0.2025.0-linux-amd64.sif \
  python -m muxi.utils.run_formation \
  /path/to/formation.yaml \
  --port 8000 --host 127.0.0.1
```

## Upgrade Path

1. **Build new version:** Update `src/muxi/.version` → `./build-runtime.sh` → `./build-sif.sh`
2. **Install on server:** Copy new SIF to `~/.muxi/server/runtimes/`
3. **Test with formation:** Update formation to `runtime: "0.2025.1"` → deploy
4. **Gradual rollout:** Upgrade formations one by one
5. **Rollback if needed:** Update formation to `runtime: "0.2025.0"` → restart

## Version History

- **0.2025.0** - Initial version with server integration (current)
- Future versions will be documented here

## References

- **Server Runtime Manager:** `/Users/ran/Projects/muxi/code/server/src/pkg/runtime/`
- **Version Resolver:** `server/src/pkg/runtime/resolver.go`
- **SIF Downloader:** `server/src/pkg/runtime/download.go`
- **Runtime Registry:** `server/src/pkg/runtime/registry.go`
