# Build Scripts

Scripts for building MUXI Runtime artifacts.

## Scripts

| Script | Description |
|--------|-------------|
| `docker.sh` | Build Docker images (dev/production) |
| `sif.sh` | Convert Docker image to Singularity SIF |
| `runtime.sh` | Build runtime wheel |
| `package.sh` | Build PyPI package |
| `publish.sh` | Publish to PyPI |

## Quick Reference

```bash
# Build Docker image
./scripts/build/docker.sh

# Build production Docker image
./scripts/build/docker.sh --production

# Convert to SIF (after Docker build)
./scripts/build/sif.sh

# Build PyPI package
./scripts/build/package.sh
```

## Documentation

See [contributing/building.md](../../contributing/building.md) for full documentation.
