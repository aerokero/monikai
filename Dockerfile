FROM node:22-bookworm-slim AS node-runtime

FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ffmpeg \
        libasound2-dev \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY backend/integrations/games/minecraft-bot/package*.json \
    /app/backend/integrations/games/minecraft-bot/
RUN npm ci --omit=dev \
    --prefix /app/backend/integrations/games/minecraft-bot \
    && npm cache clean --force

COPY . .

EXPOSE 8000

CMD ["python", "-m", "backend.core.server"]
