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

# ── Install requirements ─────────────────────────────────────────────────────
COPY web/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --timeout 600 -r requirements.txt

# ── Copy web application source ──────────────────────────────────────────────
COPY web/app/ ./app/

RUN mkdir -p /app/data/projects

EXPOSE 8080

CMD ["python", "-m", "app.main"]
