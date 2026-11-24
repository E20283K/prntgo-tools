# Stage 1: Build React + shadcn/ui frontend
FROM node:22-alpine AS frontend-builder
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: FastAPI + PrintHub + Claude Code CLI + VectorCraft (CLI MCP & Web WASM)
FROM python:3.12-slim

ARG VECTORCRAFT_VERSION=0.24.1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PRINTHUB_DATA_DIR=/app/data \
    HOME=/app/data/claude_home \
    CLAUDE_CONFIG_DIR=/app/data/claude_home/.claude \
    VECTORCRAFT_WEB_DIR=/app/vectorcraft_web

# Linux fonts, curl, unzip, git, ripgrep, Node.js 22 LTS, and Claude Code CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-liberation \
    fonts-dejavu-core \
    curl \
    ca-certificates \
    gnupg \
    unzip \
    git \
    ripgrep \
    libxkbcommon0 \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && npm cache clean --force \
    && rm -rf /var/lib/apt/lists/*

# Install VectorCraft CLI (headless MCP server & converter) for Linux x86_64 / aarch64
RUN set -eux; \
    ARCH="$(uname -m)"; \
    case "$ARCH" in \
        x86_64|amd64) VC_ARCH="x86_64" ;; \
        aarch64|arm64) VC_ARCH="aarch64" ;; \
        *) echo "Unsupported architecture: $ARCH" >&2; exit 1 ;; \
    esac; \
    TARBALL="vectorcraft-${VECTORCRAFT_VERSION}-linux-${VC_ARCH}.tar.gz"; \
    curl -fsSL -o "/tmp/${TARBALL}" \
        "https://github.com/storytold/vectorcraft/releases/download/v${VECTORCRAFT_VERSION}/${TARBALL}"; \
    tar -xzf "/tmp/${TARBALL}" -C /tmp; \
    install -Dm755 "/tmp/vectorcraft-${VECTORCRAFT_VERSION}-linux-${VC_ARCH}/bin/vectorcraft-cli" /usr/local/bin/vectorcraft-cli; \
    rm -rf "/tmp/${TARBALL}" "/tmp/vectorcraft-${VECTORCRAFT_VERSION}-linux-${VC_ARCH}"; \
    /usr/local/bin/vectorcraft-cli --version

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY engines/ ./engines/
COPY app/ ./app/
COPY bot/ ./bot/
COPY data/ ./data_seed/
COPY --from=frontend-builder /app/static ./app/static

# Install VectorCraft Web (WebAssembly browser studio) under /app/vectorcraft_web
RUN set -eux; \
    mkdir -p /app/vectorcraft_web; \
    curl -fsSL -o /tmp/vectorcraft-web.zip \
        "https://github.com/storytold/vectorcraft/releases/download/v${VECTORCRAFT_VERSION}/vectorcraft-web-${VECTORCRAFT_VERSION}.zip"; \
    unzip -q /tmp/vectorcraft-web.zip -d /tmp/vc_web; \
    cp -r /tmp/vc_web/vectorcraft-web-${VECTORCRAFT_VERSION}/* /app/vectorcraft_web/; \
    rm -rf /tmp/vectorcraft-web.zip /tmp/vc_web

# Entrypoint script seeds /app/data volume on first run without overwriting user changes
RUN printf '#!/bin/sh\nset -e\nmkdir -p /app/data/sela_templates /app/data/sela_set /app/data/fonts /app/data/jobs /app/data/claude_home /app/data/claude_workspace/.claude/skills /app/data/claude_workspace/assets\nif [ ! -f /app/data/gears.json ] && [ -f /app/data_seed/gears.json ]; then cp /app/data_seed/gears.json /app/data/gears.json; fi\nif [ -z "$(ls -A /app/data/sela_set 2>/dev/null)" ] && [ -d /app/data_seed/sela_set ]; then cp -r /app/data_seed/sela_set/* /app/data/sela_set/ 2>/dev/null || true; fi\nif [ -z "$(ls -A /app/data/sela_templates 2>/dev/null)" ] && [ -d /app/data_seed/sela_templates ]; then cp -r /app/data_seed/sela_templates/* /app/data/sela_templates/ 2>/dev/null || true; fi\nif [ -f /app/data/sela_templates/template.pdf ] && [ -f /app/data_seed/sela_templates/template.pdf ] && [ "$(wc -c < /app/data/sela_templates/template.pdf)" -lt 5000 ]; then cp /app/data_seed/sela_templates/template.pdf /app/data/sela_templates/template.pdf; fi\nif [ -z "$(ls -A /app/data/fonts 2>/dev/null)" ] && [ -d /app/data_seed/fonts ]; then cp -r /app/data_seed/fonts/* /app/data/fonts/ 2>/dev/null || true; fi\nexec "$@"\n' > /entrypoint.sh \
    && chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
