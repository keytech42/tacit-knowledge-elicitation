# Embeddings Setup

Embeddings power the respondent recommendation system, which uses pgvector cosine similarity to match questions with the best-suited respondents based on their past answers.

When enabled, embeddings are generated automatically whenever a question or answer is created or updated. When disabled (or `RECOMMENDATION_STRATEGY=llm`), recommendations use LLM-based scoring via the worker service instead. See `docs/architecture.md` for strategy comparison.

## Quick Start (Local Development)

### 1. Install llama.cpp

```bash
# macOS (Homebrew)
brew install llama.cpp
```

Verify it's installed:

```bash
llama-server --version
```

### 2. Download the model

We use [bge-m3](https://huggingface.co/BAAI/bge-m3) — a multilingual embedding model (1024 dimensions, 8K token context, strong English + Korean support).

Download the Q8_0 quantized GGUF from the official [ggml-org conversion](https://huggingface.co/ggml-org/bge-m3-Q8_0-GGUF):

```bash
mkdir -p ~/models
python3 -c "
from huggingface_hub import hf_hub_download
hf_hub_download(
    repo_id='ggml-org/bge-m3-Q8_0-GGUF',
    filename='bge-m3-q8_0.gguf',
    local_dir='$HOME/models',
)
print('Done')
"
```

If `huggingface_hub` isn't installed: `pip install huggingface_hub`.

### 3. Start the embedding server

```bash
llama-server --model ~/models/bge-m3-q8_0.gguf --embeddings --port 8090
```

That's it. The server auto-detects GPU layers (Metal on macOS, CUDA on Linux) and loads the model's context size from metadata.

Verify it's working:

```bash
curl -s http://127.0.0.1:8090/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"input": "test", "model": "bge-m3"}' | python3 -c "
import sys, json
emb = json.load(sys.stdin)['data'][0]['embedding']
print(f'{len(emb)} dimensions')  # Should print: 1024 dimensions
"
```

### 4. Configure environment variables

Add to your `.env`:

```bash
EMBEDDING_MODEL=openai/bge-m3
EMBEDDING_API_BASE=http://host.docker.internal:8090/v1/
EMBEDDING_API_KEY=no-key
```

- `EMBEDDING_MODEL` uses the `openai/` prefix because litellm routes to the OpenAI-compatible `/v1/embeddings` endpoint that llama-server exposes
- `host.docker.internal` lets Docker containers reach the host machine where llama-server runs
- `EMBEDDING_API_KEY` is required by litellm but llama-server ignores it — any non-empty value works

Restart the api service to pick up the changes:

```bash
docker compose restart api
```

## Why Q8_0?

Embedding models are more sensitive to quantization than generative models — small vector distortions compound in cosine similarity calculations. Q8_0 strikes the right balance:

| Quantization | Size   | Quality vs F16 | Notes |
|-------------|--------|-----------------|-------|
| F16         | ~1.1GB | Baseline        | No quality loss, but unnecessary for this model size |
| **Q8_0**    | **605MB** | **~99%**     | **Recommended — negligible quality loss** |
| Q5_K_M      | ~400MB | ~96%            | Measurable retrieval accuracy loss |
| Q4_K_M      | ~330MB | ~93%            | Noticeable degradation in similarity rankings |

For a 567M parameter model, 605MB is small enough that further compression isn't worth the quality tradeoff.

## llama-server Options

The minimal command (`llama-server --model <path> --embeddings --port 8090`) is sufficient for most setups. Here's what the relevant flags do if you need to tune:

| Flag | Default | Purpose |
|------|---------|---------|
| `--embeddings` | off | **Required.** Enables the `/v1/embeddings` endpoint |
| `--port` | 8080 | Port to listen on |
| `--ctx-size` | from model | Max input token length. bge-m3 declares 8192 in its metadata, so this is auto-set. Only useful if you want to *reduce* it to save memory |
| `-ngl`, `--n-gpu-layers` | auto | Layers offloaded to GPU. Modern llama.cpp auto-detects and offloads all layers. Only needed on older versions or to force CPU-only (`-ngl 0`) |
| `--n-parallel` | auto | Concurrent request slots. Defaults to 4. Increase if you're bulk-generating embeddings |
| `--host` | 127.0.0.1 | Bind address. Use `0.0.0.0` to expose on the network |

## Cloud Provider Alternative

For production without local GPU, use a cloud embedding API:

```bash
# OpenAI
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_API_KEY=sk-...

# Azure OpenAI
EMBEDDING_MODEL=azure/my-embedding-deployment
EMBEDDING_API_BASE=https://my-resource.openai.azure.com/
EMBEDDING_API_KEY=...
```

Note: If switching models, the embedding dimensions must match the pgvector column (1024). OpenAI's `text-embedding-3-small` outputs 1536 by default but supports a `dimensions` parameter — configure litellm accordingly, or migrate the column.

## Production (Linux with CUDA)

For GPU-accelerated production servers, use HuggingFace Text Embeddings Inference (TEI) instead of llama.cpp:

```bash
docker run -d --gpus all -p 8090:80 \
  ghcr.io/huggingface/text-embeddings-inference:latest \
  --model-id BAAI/bge-m3
```

The `.env` configuration is the same — TEI exposes an OpenAI-compatible API.

## Troubleshooting

**"Connection refused" from Docker containers**
- Ensure llama-server is running on the host (not inside Docker)
- Verify `host.docker.internal` resolves: `docker compose exec api curl http://host.docker.internal:8090/health`

**Embeddings not being generated**
- Check `EMBEDDING_MODEL` is set and non-empty in the api container: `docker compose exec api env | grep EMBEDDING`
- The embedding service silently skips generation when the model is not configured (by design — it's optional infrastructure)

**Dimension mismatch errors**
- The pgvector columns expect 1024 dimensions (matching bge-m3)
- If using a different model, you'll need to alter the `Vector(1024)` column definitions and re-run migrations
