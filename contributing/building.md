# Building MUXI Runtime

Guide for building MUXI Runtime artifacts (Docker images, SIF containers, PyPI packages).

## Prerequisites

- Docker (for Docker and SIF builds)
- Python 3.10+ (for PyPI builds)
- Singularity/Apptainer (for SIF builds, Linux only)

## Build Scripts

All build scripts are in `scripts/build/`:

| Script | Purpose |
|--------|---------|
| `docker.sh` | Build Docker images |
| `sif.sh` | Convert Docker image to SIF |
| `runtime.sh` | Build runtime wheel |
| `package.sh` | Build PyPI package |
| `publish.sh` | Publish to PyPI |

## Docker Images

### Build Development Image

```bash
./scripts/build/docker.sh
```

### Build Production Image

```bash
./scripts/build/docker.sh --production
```

### Build for Specific Architecture

```bash
./scripts/build/docker.sh --arch linux/arm64
./scripts/build/docker.sh --arch linux/amd64
```

### Image Tags

- `muxi-runtime:latest` - Development image
- `muxi-runtime:production` - Production image with optimizations
- `muxi-runtime:{version}` - Version-tagged images

## SIF Containers

SIF (Singularity Image Format) containers are used by MUXI Server for isolated formation execution.

### Convert Docker to SIF

```bash
# Build Docker image first
./scripts/build/docker.sh

# Convert to SIF
./scripts/build/sif.sh
```

### Build for Specific Architecture

```bash
./scripts/build/sif.sh --arch arm64
./scripts/build/sif.sh --arch amd64
```

### Output

SIF files are created in `sif-builds/` with naming convention:
```
muxi-runtime-{version}-linux-{arch}.sif
```

### Alternative: Build from Definition Files

The `sif/` directory contains Singularity definition files for direct builds (requires Linux with Singularity installed):

```bash
cd sif
sudo singularity build muxi-runtime.sif muxi-runtime.def
```

## PyPI Package

### Build Package

```bash
./scripts/build/package.sh
```

Output is created in `dist/`.

### Publish to PyPI

```bash
./scripts/build/publish.sh
```

Requires PyPI credentials configured.

## Testing Builds

Test scripts are in `scripts/test/`:

```bash
# Test Docker image
./scripts/test/docker.sh

# Test local server
./scripts/test/local-server.sh
```

## Related Documentation

- [docker-compose-guide.md](docker-compose-guide.md) - Running with Docker Compose
- [docker-secrets-guide.md](docker-secrets-guide.md) - Secrets management
- [docker-testing.md](docker-testing.md) - Docker testing details
- [pypi-distribution.md](pypi-distribution.md) - PyPI distribution details
- [server-integration.md](server-integration.md) - How Server uses Runtime
