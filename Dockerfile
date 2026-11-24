FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PRINTHUB_DATA_DIR=/app/data \
    HOME=/app/data/claude_home \
    CLAUDE_CONFIG_DIR=/app/data/claude_home/.claude \
    VECTORCRAFT_WEB_DIR=/app/data/vectorcraft_web \
    PATH="/app/data/tools/npm-global/bin:/app/data/tools/node/bin:/app/data/tools/bin:${PATH}"

# Lightweight OS packages only (~15s). Heavy AI tools (Node, Claude Code, VectorCraft CLI & Web)
# are persisted once in the /app/data volume so Docker builds always finish in <1 minute!
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-liberation \
    fonts-dejavu-core \
    curl \
    ca-certificates \
    unzip \
    xz-utils \
    git \
    ripgrep \
    libxkbcommon0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY engines/ ./engines/
COPY app/ ./app/
COPY bot/ ./bot/
COPY data/ ./data_seed/

# Entrypoint script seeds /app/data volume on first run without overwriting user changes
RUN printf '#!/bin/sh\nset -e\nmkdir -p /app/data/sela_templates /app/data/sela_set /app/data/fonts /app/data/jobs /app/data/tools/bin /app/data/vectorcraft_web /app/data/claude_home /app/data/claude_workspace/.claude/skills /app/data/claude_workspace/assets /app/data/claude_workspace/uploads /app/data/claude_workspace/outputs\nif [ ! -f /app/data/gears.json ] && [ -f /app/data_seed/gears.json ]; then cp /app/data_seed/gears.json /app/data/gears.json; fi\nif [ -z "$(ls -A /app/data/sela_set 2>/dev/null)" ] && [ -d /app/data_seed/sela_set ]; then cp -r /app/data_seed/sela_set/* /app/data/sela_set/ 2>/dev/null || true; fi\nif [ -z "$(ls -A /app/data/sela_templates 2>/dev/null)" ] && [ -d /app/data_seed/sela_templates ]; then cp -r /app/data_seed/sela_templates/* /app/data/sela_templates/ 2>/dev/null || true; fi\nif [ -f /app/data/sela_templates/template.pdf ] && [ -f /app/data_seed/sela_templates/template.pdf ] && [ "$(wc -c < /app/data/sela_templates/template.pdf)" -lt 5000 ]; then cp /app/data_seed/sela_templates/template.pdf /app/data/sela_templates/template.pdf; fi\nif [ -z "$(ls -A /app/data/fonts 2>/dev/null)" ] && [ -d /app/data_seed/fonts ]; then cp -r /app/data_seed/fonts/* /app/data/fonts/ 2>/dev/null || true; fi\nexec "$@"\n' > /entrypoint.sh \
    && chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
