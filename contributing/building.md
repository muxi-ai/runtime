# Building MUXI Runtime

Guide for building MUXI Runtime artifacts (Docker images, SIF containers, PyPI packages).

## Prerequisites

- Docker (for Docker and SIF builds)
- Python 3.10+ (for PyPI builds)
- Apptainer or Singularity (for SIF builds; optional — `sif.sh` falls back to a Docker-wrapped converter)

## Build Scripts

All build scripts are in `scripts/build/`:

| Script | Purpose |
|--------|---------|
| `runtime.sh` | Build versioned Docker images (all variants) |
| `sif.sh` | Convert Docker image to SIF (all variants) |
| `docker.sh` | Legacy helper for dev/production images |
| `package.sh` | Build PyPI package |
| `publish.sh` | Publish to PyPI |

## Docker Images

MUXI Runtime ships three image variants:

| Variant | Dockerfile | SIF size | Description | Status |
|---------|------------|----------|-------------|--------|
| `default` | `Dockerfile` | ~600 MB | Lean base runtime; covers the vast majority of use cases | Stable |
| `pytorch` | `Dockerfile.pytorch` | larger | Adds CPU-only PyTorch for local embedding models without ONNX exports | Stable |
| `cuda` | `Dockerfile.cuda` | largest | ONNX + PyTorch local models, FAISS-GPU for faster vector ops; NVIDIA-only, `linux/amd64` | **Experimental** |

### Build a Variant

```bash
# Default variant
./scripts/build/runtime.sh

# PyTorch variant (build default first)
./scripts/build/runtime.sh --variant pytorch

# CUDA variant — experimental, linux/amd64 + NVIDIA tooling required
./scripts/build/runtime.sh --variant cuda
```

### Cross-Platform Builds

```bash
./scripts/build/runtime.sh --platform linux/amd64
./scripts/build/runtime.sh --platform linux/arm64
./scripts/build/runtime.sh --platform linux/amd64 --variant pytorch
```

> **Note:** The `cuda` variant only builds on `linux/amd64`. It requires NVIDIA tooling
> and `nvidia-container-toolkit`. It is not tested in CI against live GPUs.

### Image Tags

Each build produces two tags:
- `muxi-runtime:{version}` — version-pinned (e.g. `muxi-runtime:0.20260422.0`)
- `muxi-runtime:latest` — floating alias

Variant builds append a suffix: `muxi-runtime:{version}-pytorch`, `muxi-runtime:{version}-cuda`.

## SIF Containers

SIF (Singularity Image Format) containers are used by MUXI Server for isolated formation execution.

### Convert Docker to SIF

```bash
# Build Docker image first, then convert
./scripts/build/runtime.sh
./scripts/build/sif.sh

# With a specific variant
./scripts/build/runtime.sh --variant pytorch
./scripts/build/sif.sh --variant pytorch

# Force target architecture
./scripts/build/sif.sh --arch amd64
./scripts/build/sif.sh --arch arm64 --variant pytorch
```

If `apptainer` or `singularity` is not installed locally, `sif.sh` automatically falls back
to the Docker-wrapped `ghcr.io/muxi-ai/runtime-runner` converter.

> **Platform guidance:** On macOS and Windows the correct SIF arch is always `linux-amd64`
> regardless of host CPU (Rosetta / Hyper-V handles the translation). `linux-arm64` SIFs
> only apply on native arm64 Linux hosts (e.g. AWS Graviton).

### Output

SIF files are created in `sif-builds/` with naming convention:

```
muxi-runtime-{version}-linux-{arch}.sif          # default
muxi-runtime-{version}-pytorch-linux-{arch}.sif  # pytorch
muxi-runtime-{version}-cuda-linux-{arch}.sif     # cuda (experimental)
```

Each build also writes a `latest` alias:

```
muxi-runtime-latest-linux-{arch}.sif
muxi-runtime-latest-pytorch-linux-{arch}.sif
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
