# Embeddings Setup

Embeddings power the respondent recommendation system, which uses pgvector cosine similarity to match questions with the best-suited respondents based on their past answers.

When enabled, embeddings are generated automatically whenever a question or answer is created or updated. When disabled (or `RECOMMENDATION_STRATEGY=llm`), recommendations use LLM-based scoring via the worker service instead. See `docs/architecture.md` for strategy comparison.

> [!NOTE]
> Embeddings are entirely optional. If you don't need embedding-based recommendations, set `RECOMMENDATION_STRATEGY=llm` and skip this guide entirely. LLM-based recommendation requires only an Anthropic API key — no local inference infrastructure.

> [!WARNING]
> **This guide's Docker Compose setup is for CPU-only servers.** The `embedding` service uses the `ghcr.io/ggml-org/llama.cpp:server` image which runs CPU inference only. This is well-suited for servers without a GPU (bge-m3 at Q8_0 runs comfortably on modern CPUs with 2GB+ free RAM), but is **not optimal if you have a GPU available**. See [GPU alternatives](#gpu-alternatives) below for CUDA and Metal setups.

## Quick Start (Docker Compose)

The embedding server runs as an optional Docker Compose service using [llama.cpp](https://github.com/ggerganov/llama.cpp).

### 1. Download the model

```bash
make embed-download
```

This downloads the [bge-m3](https://huggingface.co/BAAI/bge-m3) Q8_0 quantized GGUF (~605MB) into `./models/`. See [Why Q8_0?](#why-q8_0) for the rationale.

> [!TIP]
> To use a custom model directory, set `EMBEDDING_MODEL_DIR` in your `.env` or pass it to Make: `make embed-download EMBEDDING_MODEL_DIR=~/models`

### 2. Configure environment variables

Add to your `.env`:

```bash
EMBEDDING_MODEL=openai/bge-m3
EMBEDDING_API_BASE=http://embedding:8090/v1/
EMBEDDING_API_KEY=no-key
```

- `EMBEDDING_MODEL` uses the `openai/` prefix because litellm routes to the OpenAI-compatible `/v1/embeddings` endpoint that llama-server exposes
- `embedding` is the Docker Compose service name — containers reach it directly via the compose network
- `EMBEDDING_API_KEY` is required by litellm but llama-server ignores it — any non-empty value works

### 3. Start all services including embeddings

```bash
make up-embed
```

This starts the four core services plus the embedding server. The embedding service has a health check with a 30-second start period to allow model loading.

Verify it's working:

```bash
make embed-status
```

Or test directly:

```bash
curl -s http://localhost:8090/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"input": "test", "model": "bge-m3"}' | python3 -c "
import sys, json
emb = json.load(sys.stdin)['data'][0]['embedding']
print(f'{len(emb)} dimensions')  # Should print: 1024 dimensions
"
```

## GPU Alternatives

> [!IMPORTANT]
> The Docker Compose `embedding` service runs **CPU-only inference**. If your deployment environment has a GPU, you should use a GPU-accelerated setup instead for significantly better throughput. The options below replace the `embedding` compose service — configure `EMBEDDING_API_BASE` to point to whichever server you choose.

### macOS (Metal GPU)

Docker on macOS cannot access Metal GPU. Run llama-server natively on the host:

```bash
brew install llama.cpp
llama-server --model ./models/bge-m3-q8_0.gguf --embeddings --port 8090
```

Set `EMBEDDING_API_BASE=http://host.docker.internal:8090/v1/` in your `.env` so Docker containers reach the host. Do **not** enable the `embedding` compose profile — the host-side server replaces it.

### Linux (NVIDIA CUDA)

Use the CUDA-accelerated llama.cpp image:

```yaml
# docker-compose.override.yml
services:
  embedding:
    image: ghcr.io/ggml-org/llama.cpp:server-cuda
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

Or use [HuggingFace Text Embeddings Inference (TEI)](https://github.com/huggingface/text-embeddings-inference) which is purpose-built for GPU embedding workloads:

```bash
docker run -d --gpus all -p 8090:80 \
  ghcr.io/huggingface/text-embeddings-inference:latest \
  --model-id BAAI/bge-m3
```

TEI exposes the same OpenAI-compatible API, so the `.env` configuration is identical.

### Linux (AMD ROCm)

```yaml
# docker-compose.override.yml
services:
  embedding:
    image: ghcr.io/ggml-org/llama.cpp:server-rocm
    devices:
      - /dev/kfd
      - /dev/dri
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

### Cloud Provider Alternative

For production without local infrastructure, use a cloud embedding API:

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

## Troubleshooting

**"Connection refused" from Docker containers**
- If using the compose `embedding` service: check `make embed-status` and `docker compose --profile embedding logs embedding`
- If using host-side llama-server (macOS): verify `host.docker.internal` resolves: `docker compose exec api curl http://host.docker.internal:8090/health`

**Embeddings not being generated**
- Check `EMBEDDING_MODEL` is set and non-empty in the api container: `docker compose exec api env | grep EMBEDDING`
- The embedding service silently skips generation when the model is not configured (by design — it's optional infrastructure)

**Dimension mismatch errors**
- The pgvector columns expect 1024 dimensions (matching bge-m3)
- If using a different model, you'll need to alter the `Vector(1024)` column definitions and re-run migrations
