# Environment

Environment variables, external dependencies, and setup notes for this mission.

**What belongs here:** env vars, external accounts, dependency quirks, platform-specific notes.
**What does NOT belong here:** service ports / commands (use `.factory/services.yaml`).

---

## Required environment variables

| Var | Required for | Source | Notes |
|---|---|---|---|
| `OPENAI_API_KEY` | VAL-INTEG-003 (OpenAI regression test) + any e2e test using OpenAI | user's shell env + `e2e/tests/*/secrets.enc` | Never commit or log |
| `HF_HOME` | optional | not set by default | OneLLM LocalProvider respects this; defaults to `~/.cache/huggingface/hub/` |
| `ONELLM_ALLOW_TRUST_REMOTE_CODE` | optional kill switch | not set by default | Nomic models require `trust_remote_code=True`; setting this to `false` blocks loading |
| `ONELLM_LOCAL_CACHE_SIZE` | optional | not set by default | LRU cache size for loaded local models; default 2 |

## External accounts

- **HuggingFace** — public access, no token required for `nomic-ai/nomic-embed-text-v1.5` or `nomic-ai/nomic-embed-text-v2-moe`. Both are gated-free Apache-2.0 Nomic repos.
- **OpenAI** — needed only for the cloud regression test. Key pre-configured.

## Dependency quirks

- **`onellm[cache]==0.20260421.0` is a HARD BREAK** from earlier versions: the `[cache]` extra no longer pulls `sentence-transformers` / `torch`. Runtime must drop its direct `sentence-transformers>=2.2.0` dep or imports will break.
- **`sentence-transformers` fallback path**: if a user pins a PyTorch-only HF repo (not Nomic v1.5 / v2 MoE), they need `pip install 'onellm[local-pytorch]'` to opt-in. MUXI does not carry this transitively.
- **ONNX Runtime on Apple Silicon**: uses CoreML execution provider automatically. No additional setup needed.
- **ONNX Runtime on Linux ARM64**: CPU provider works out of the box as of `onnxruntime>=1.17`.
- **PyTorch-only repos**: if a worker encounters a HF repo without `onnx/model.onnx`, OneLLM's LocalProvider raises `InvalidConfigurationError` pointing at the `local-pytorch` extra. This is expected behavior; do not silently fall back.

## Disk / network footprint

- First integration-test run downloads Nomic v1.5 (~275 MB) + Nomic v2 MoE (~1.9 GB) to HF cache. Total: ~2.2 GB.
- Subsequent runs reuse the cache (warm: ~0 MB network, ~3.5s ONNX session load per fresh pytest process).
- No outbound network required for unit tests.

## Platform notes

- macOS darwin 24.6.0 (user's host) — Apple Silicon, ONNX via CoreML
- MUXI runtime targets Python 3.10+ per `pyproject.toml`
- Editable install: `/Users/ran/Projects/muxi/code/runtime/` and `/Users/ran/Projects/muxi/code/onellm/` both `pip install -e .`
