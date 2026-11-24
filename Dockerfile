# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PRINTHUB_DATA_DIR=/app/data \
    HOME=/app/data/claude_home \
    CLAUDE_CONFIG_DIR=/app/data/claude_home/.claude \
    VECTORCRAFT_WEB_DIR=/app/vectorcraft_web \
    VECTORCRAFT_VERSION=0.24.1

# 1. System packages, Node.js 22 LTS, and Claude Code CLI (NO ARG above this -> 100% Docker layer cached!)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    --mount=type=cache,target=/root/.npm \
    set -eux; \
    apt-get update && apt-get install -y --no-install-recommends \
        fonts-liberation \
        fonts-dejavu-core \
        curl \
        ca-certificates \
        gnupg \
        unzip \
        git \
        ripgrep \
        libxkbcommon0; \
    if ! command -v node >/dev/null 2>&1; then \
        curl -fsSL https://deb.nodesource.com/setup_22.x | bash -; \
        apt-get install -y --no-install-recommends nodejs; \
    fi; \
    npm install -g @anthropic-ai/claude-code --prefer-offline --no-audit --no-fund

# 2. VectorCraft CLI + VectorCraft Web (NO ARG above this -> 100% Docker layer cached!)
RUN --mount=type=cache,target=/var/cache/printhub \
    set -eux; \
    ARCH="$(uname -m)"; \
    case "$ARCH" in \
        x86_64|amd64) VC_ARCH="x86_64" ;; \
        aarch64|arm64) VC_ARCH="aarch64" ;; \
        *) echo "Unsupported architecture: $ARCH" >&2; exit 1 ;; \
    esac; \
    CACHE_DIR="/var/cache/printhub/vc-${VECTORCRAFT_VERSION}-${VC_ARCH}"; \
    mkdir -p "$CACHE_DIR"; \
    if [ ! -x "$CACHE_DIR/vectorcraft-cli" ]; then \
        TARBALL="vectorcraft-${VECTORCRAFT_VERSION}-linux-${VC_ARCH}.tar.gz"; \
        curl -fsSL -o "$CACHE_DIR/${TARBALL}" \
            "https://github.com/storytold/vectorcraft/releases/download/v${VECTORCRAFT_VERSION}/${TARBALL}"; \
        tar -xzf "$CACHE_DIR/${TARBALL}" -C "$CACHE_DIR" \
            "vectorcraft-${VECTORCRAFT_VERSION}-linux-${VC_ARCH}/bin/vectorcraft-cli"; \
        mv "$CACHE_DIR/vectorcraft-${VECTORCRAFT_VERSION}-linux-${VC_ARCH}/bin/vectorcraft-cli" "$CACHE_DIR/vectorcraft-cli"; \
        chmod 755 "$CACHE_DIR/vectorcraft-cli"; \
        rm -rf "$CACHE_DIR/${TARBALL}" "$CACHE_DIR/vectorcraft-${VECTORCRAFT_VERSION}-linux-${VC_ARCH}"; \
    fi; \
    install -Dm755 "$CACHE_DIR/vectorcraft-cli" /usr/local/bin/vectorcraft-cli; \
    /usr/local/bin/vectorcraft-cli --version; \
    if [ ! -f "$CACHE_DIR/web/index.html" ]; then \
        mkdir -p "$CACHE_DIR/web_tmp" "$CACHE_DIR/web"; \
        curl -fsSL -o "$CACHE_DIR/vectorcraft-web.zip" \
            "https://github.com/storytold/vectorcraft/releases/download/v${VECTORCRAFT_VERSION}/vectorcraft-web-${VECTORCRAFT_VERSION}.zip"; \
        unzip -q "$CACHE_DIR/vectorcraft-web.zip" -d "$CACHE_DIR/web_tmp"; \
        cp -r "$CACHE_DIR/web_tmp/vectorcraft-web-${VECTORCRAFT_VERSION}/"* "$CACHE_DIR/web/"; \
        rm -rf "$CACHE_DIR/vectorcraft-web.zip" "$CACHE_DIR/web_tmp"; \
    fi; \
    mkdir -p /app/vectorcraft_web; \
    cp -r "$CACHE_DIR/web/"* /app/vectorcraft_web/

WORKDIR /app

# 3. Python dependencies (NO ARG above this -> 100% Docker layer cached!)
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# 4. Pre-declare all service & Coolify ARGs HERE (below heavy RUN layers) so Coolify
# sees "All required ARG declarations already exist" and NEVER injects ARGs after FROM!
ARG WEB_PASSWORD
ARG SECRET_KEY
ARG PUBLIC_URL
ARG JOB_TTL_HOURS
ARG CLAUDE_CODE_OAUTH_TOKEN
ARG ANTHROPIC_API_KEY
ARG TELEGRAM_BOT_TOKEN
ARG ALLOWED_TELEGRAM_IDS
ARG SOURCE_COMMIT
ARG COOLIFY_URL
ARG COOLIFY_FQDN
ARG COOLIFY_BRANCH
ARG COOLIFY_RESOURCE_UUID
ARG COOLIFY_CONTAINER_NAME

# 5. Application code & pre-built frontend static assets
COPY engines/ ./engines/
COPY app/ ./app/
COPY bot/ ./bot/
COPY data/ ./data_seed/

# Entrypoint script seeds /app/data volume on first run without overwriting user changes
RUN printf '#!/bin/sh\nset -e\nmkdir -p /app/data/sela_templates /app/data/sela_set /app/data/fonts /app/data/jobs /app/data/claude_home /app/data/claude_workspace/.claude/skills /app/data/claude_workspace/assets /app/data/claude_workspace/uploads /app/data/claude_workspace/outputs\nif [ ! -f /app/data/gears.json ] && [ -f /app/data_seed/gears.json ]; then cp /app/data_seed/gears.json /app/data/gears.json; fi\nif [ -z "$(ls -A /app/data/sela_set 2>/dev/null)" ] && [ -d /app/data_seed/sela_set ]; then cp -r /app/data_seed/sela_set/* /app/data/sela_set/ 2>/dev/null || true; fi\nif [ -z "$(ls -A /app/data/sela_templates 2>/dev/null)" ] && [ -d /app/data_seed/sela_templates ]; then cp -r /app/data_seed/sela_templates/* /app/data/sela_templates/ 2>/dev/null || true; fi\nif [ -f /app/data/sela_templates/template.pdf ] && [ -f /app/data_seed/sela_templates/template.pdf ] && [ "$(wc -c < /app/data/sela_templates/template.pdf)" -lt 5000 ]; then cp /app/data_seed/sela_templates/template.pdf /app/data/sela_templates/template.pdf; fi\nif [ -z "$(ls -A /app/data/fonts 2>/dev/null)" ] && [ -d /app/data_seed/fonts ]; then cp -r /app/data_seed/fonts/* /app/data/fonts/ 2>/dev/null || true; fi\nexec "$@"\n' > /entrypoint.sh \
    && chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
