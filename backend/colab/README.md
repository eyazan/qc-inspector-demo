# Remote GPU services on Colab (free) — runs OUR service code

Architecture: only DocLayout runs locally. PaddleOCR-VL + LLM run on a remote GPU
as OpenAI-compatible endpoints; the backend reaches them by URL + bearer token
(config only). The OCR endpoint on Colab runs the **same packaged service** that
the company H200 will run — `services/paddleocr_vl_service` — which reuses the
single model loader `app/providers/ocr/paddleocr_vl_local_provider.py`. No
throwaway/duplicate code. Only `OCR_LOCAL_DEVICE` (cuda) + the public URL differ.

---

## A) Get our code onto Colab (pick one)

**Option 1 — upload a code-only zip (no GitHub needed).** On your Mac:
```bash
cd qc_inspector_demo
zip -r /tmp/qc_backend.zip backend \
  -x 'backend/.venv/*' 'backend/models/*' 'backend/data/*' '*/__pycache__/*'
```
Then in Colab, Cell A:
```python
from google.colab import files
up = files.upload()            # choose /tmp/qc_backend.zip
import zipfile
zipfile.ZipFile(next(iter(up))).extractall(".")
%cd backend
```

**Option 2 — git clone** (if you push the repo to GitHub):
```python
!git clone https://github.com/<you>/<repo>.git
%cd <repo>/backend
```

---

## B) OCR service (PaddleOCR-VL) — same packaged service as prod

```python
# Cell 1 — deps the OCR service needs (NO paddle here; paddle is only for the
# local DocLayout on your Mac).
!pip install -q "transformers==4.55.0" torch torchvision accelerate einops \
    sentencepiece pillow fastapi "uvicorn[standard]" pydantic pydantic-settings \
    pyyaml huggingface_hub requests

# Cell 2 — config via env (model auto-downloads from HF on first OCR call)
import os
os.environ["OCR_LOCAL_MODEL_DIR"]      = "PaddlePaddle/PaddleOCR-VL-1.6"
os.environ["OCR_LOCAL_DEVICE"]         = "cuda"
os.environ["OCR_LOCAL_DTYPE"]          = "bfloat16"
os.environ["OCR_SERVICE_BEARER_TOKEN"] = "pick-your-own-secret"

# Cell 3 — run OUR packaged service (identical to the H200 deployment)
import subprocess, time, requests
srv = subprocess.Popen(["uvicorn", "services.paddleocr_vl_service.app:app",
                        "--host", "0.0.0.0", "--port", "8102"])
time.sleep(10)
print(requests.get("http://localhost:8102/health").json())   # {'status':'ok',...}

# Cell 4 — public HTTPS via cloudflared (no account)
!wget -q -O cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
!chmod +x cloudflared
import subprocess, re
p = subprocess.Popen(["./cloudflared","tunnel","--url","http://localhost:8102","--no-autoupdate"],
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
for line in p.stdout:
    print(line, end="")
    m = re.search(r"https://[-\w.]+trycloudflare\.com", line)
    if m:
        print("\n\n>>> OCR_SERVICE_URL =", m.group(0)); break
```
Keep the Colab tab open. Give back `OCR_SERVICE_URL` + the token.

---

## C) LLM (Qwen) — easiest is OpenRouter (no Colab GPU)
- `https://openrouter.ai` → Keys → create key (`sk-or-...`).
- `LLM_SERVICE_URL=https://openrouter.ai/api/v1`, `LLM_MODEL_NAME=qwen/...:free`,
  `LLM_SERVICE_BEARER_TOKEN=sk-or-...`.
- Or run Qwen via vLLM in a second Colab and tunnel port 8000 (same as B Cell 4).

---

## D) Point the backend at them (config only)
In `backend/.env`:
```dotenv
ACTIVE_LAYOUT_PROVIDER=paddlex_doclayout      # local
ACTIVE_OCR_PROVIDER=paddleocr_vl              # remote
OCR_SERVICE_URL=https://<ocr-tunnel>.trycloudflare.com
OCR_RECOGNIZE_PATH=/v1/chat/completions
OCR_SERVICE_BEARER_TOKEN=pick-your-own-secret
ACTIVE_LLM_PROVIDER=openai_compatible
LLM_SERVICE_URL=https://openrouter.ai/api/v1
LLM_MODEL_NAME=qwen/...:free
LLM_SERVICE_BEARER_TOKEN=sk-or-...
```
Same service image deploys to the company H200 — only `OCR_SERVICE_URL` changes.
