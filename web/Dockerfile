FROM python:3.11-slim

WORKDIR /app

# ── System dependencies ──────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# ── Copy parent project source (agents, tools, templates, schemas) ───────────
COPY agents/    ./agents/
COPY tools/     ./tools/
COPY templates/ ./templates/
COPY schemas/   ./schemas/
COPY .env.default ./.env.default
COPY main.py ./main.py

# ── Step 1 : Pin torch BEFORE docling resolves it ───────────────────────────
# torch >= 2.10 started shipping aarch64 CUDA wheels
# (nvidia_cudnn_cu13 444 MB + nvidia_cusparselt_cu13 221 MB) that are
# useless inside Docker on Mac.  Pin to the last CPU-only aarch64 version.
RUN pip install --no-cache-dir --timeout 1800 \
    "torch>=2.2.2,<2.10.0" \
    "torchvision>=0.17.0,<0.25.0"

# ── Step 2 : Install the rest of the requirements ────────────────────────────
# pip will see torch is already satisfied and skip the heavy CUDA re-download.
COPY web/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --timeout 600 -r requirements.txt

# ── Copy web application source ──────────────────────────────────────────────
COPY web/app/ ./app/

RUN mkdir -p /app/data/projects

EXPOSE 8080

CMD ["python", "-m", "app.main"]
