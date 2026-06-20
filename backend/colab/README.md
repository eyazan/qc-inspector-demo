# Remote GPU services on Google Colab (free) — OCR + LLM

Architecture: **only DocLayout runs locally.** PaddleOCR-VL and the Qwen LLM run
on a free Colab GPU, exposed as OpenAI-compatible HTTPS endpoints via a
cloudflared tunnel. The backend reaches them by URL + bearer token — config only.

> Colab free tier gives a T4 (15 GB). PaddleOCR-VL-1.6 (0.9B) is tiny; a Qwen
> 3B/7B-AWQ fits too. Use **two Colab notebooks** (one per service) or two
> accounts, since a session has one GPU.

---

## 1) PaddleOCR-VL service (OCR)

New Colab notebook → Runtime → Change runtime type → **GPU (T4)**. Cells:

```python
# Cell 1 — deps
!pip install -q "transformers==4.55.0" torch torchvision accelerate einops \
    sentencepiece pillow fastapi "uvicorn[standard]" huggingface_hub

# Cell 2 — get the server file (paste it, or upload colab/paddleocr_vl_server.py)
# Easiest: upload this repo's backend/colab/paddleocr_vl_server.py to the session.

# Cell 3 — config + warm the model (downloads ~1.9 GB from HF)
import os
os.environ["OCR_LOCAL_MODEL_DIR"]      = "PaddlePaddle/PaddleOCR-VL-1.6"
os.environ["OCR_LOCAL_DEVICE"]         = "cuda"
os.environ["OCR_LOCAL_DTYPE"]          = "bfloat16"
os.environ["OCR_SERVICE_BEARER_TOKEN"] = "dev-ocr-token-change-me"
os.environ["PORT"]                     = "8102"

# Cell 4 — run server in background
import subprocess, time
proc = subprocess.Popen(["python", "paddleocr_vl_server.py"])
time.sleep(60)  # first run loads weights

# Cell 5 — public HTTPS via cloudflared quick tunnel (no account needed)
!wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O cloudflared
!chmod +x cloudflared
import subprocess
tunnel = subprocess.Popen(["./cloudflared","tunnel","--url","http://localhost:8102","--no-autoupdate"],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
# Watch output for: https://<random>.trycloudflare.com  -> that is OCR_SERVICE_URL
for line in tunnel.stdout:
    line=line.decode(); print(line, end="")
    if "trycloudflare.com" in line: break
```

The printed `https://<random>.trycloudflare.com` is your **OCR_SERVICE_URL**.

---

## 2) Qwen LLM service (reasoning / comparison)

New Colab notebook (GPU). vLLM gives an OpenAI-compatible server:

```python
# Cell 1
!pip install -q vllm
# Cell 2 — serve a T4-friendly Qwen (AWQ fits 15 GB). For more VRAM use 7B/14B.
import os, subprocess, time
os.environ["VLLM_API_KEY"] = "dev-llm-token-change-me"
srv = subprocess.Popen([
    "python","-m","vllm.entrypoints.openai.api_server",
    "--model","Qwen/Qwen2.5-3B-Instruct",
    "--port","8000","--api-key","dev-llm-token-change-me",
    "--max-model-len","8192","--gpu-memory-utilization","0.9",
])
time.sleep(120)
# Cell 3 — cloudflared tunnel for port 8000 (same as OCR cell 5, change port)
```

The printed URL + `/v1` is your **LLM_SERVICE_URL** (e.g.
`https://<random>.trycloudflare.com/v1`), model `Qwen/Qwen2.5-3B-Instruct`.

### Free LLM alternatives (no Colab GPU needed)
- **OpenRouter** free Qwen models — set `LLM_SERVICE_URL=https://openrouter.ai/api/v1`,
  `LLM_MODEL_NAME=qwen/qwen-2.5-7b-instruct:free`, `LLM_SERVICE_BEARER_TOKEN=<key>`.
- **Together AI / Fireworks** — free credits, OpenAI-compatible, same three vars.

---

## 3) Point the backend at the remote services (config only)

In `backend/.env`:

```dotenv
# Local: ONLY DocLayout
ACTIVE_LAYOUT_PROVIDER=paddlex_doclayout
LAYOUT_DEVICE=cpu

# Remote OCR (Colab)
ACTIVE_OCR_PROVIDER=paddleocr_vl
OCR_SERVICE_URL=https://<ocr-tunnel>.trycloudflare.com
OCR_RECOGNIZE_PATH=/v1/chat/completions
OCR_SERVICE_BEARER_TOKEN=dev-ocr-token-change-me
OCR_MODEL_NAME=paddleocr-vl-16
OCR_BATCH_SIZE=4

# Remote LLM (Colab vLLM or OpenRouter/Together/Fireworks)
ACTIVE_LLM_PROVIDER=openai_compatible
LLM_SERVICE_URL=https://<llm-tunnel>.trycloudflare.com/v1
LLM_MODEL_NAME=Qwen/Qwen2.5-3B-Instruct
LLM_SERVICE_BEARER_TOKEN=dev-llm-token-change-me
```

Then `python scripts/test_full_pipeline.py` (or the normal upload flow) runs
DocLayout locally and OCR/LLM on the Colab GPUs. Nothing heavy runs locally.

> cloudflared quick-tunnel URLs change each run; update `.env` (or set them in
> `config.yaml`) when you restart the Colab session.
