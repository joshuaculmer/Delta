FROM python:3.12-slim-bookworm

COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules

RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && apt-get update \
    && apt-get install -y --no-install-recommends git curl procps ca-certificates ripgrep \
    && rm -rf /var/lib/apt/lists/*

# Packages available to agents. The image has no package-index access at run time.

RUN pip install --no-cache-dir \
    "fastapi==0.115.*" "uvicorn==0.34.*" "flask==3.1.*" "sqlalchemy==2.0.*" \
    "pydantic==2.11.*" "pytest==8.4.*" "httpx==0.28.*" "requests==2.32.*"

ARG CODEX_VERSION=0.166.0
RUN npm install -g @openai/codex@${CODEX_VERSION}

COPY delta-validate /usr/local/bin/delta-validate
RUN chmod 755 /usr/local/bin/delta-validate \
    && useradd -m -u 1000 agent \
    && mkdir -p /workspace && chown agent:agent /workspace

USER agent
WORKDIR /workspace
