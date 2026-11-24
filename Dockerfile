FROM node:22-trixie-slim

WORKDIR /app
ENV NODE_ENV=production

RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 python3-venv \
  && rm -rf /var/lib/apt/lists/*
COPY python/requirements.txt ./python/requirements.txt
RUN python3 -m venv /opt/venv \
  && /opt/venv/bin/pip install --no-cache-dir -r python/requirements.txt
ENV PYTHON_BIN=/opt/venv/bin/python \
    PYTHONDONTWRITEBYTECODE=1 \
    NUMBA_CACHE_DIR=/tmp/numba

COPY package*.json ./
RUN if [ -f package-lock.json ]; then npm ci --omit=dev; else npm install --omit=dev; fi

COPY index.js ./
COPY src ./src
COPY python ./python

RUN chmod -R a+rX python

USER node
EXPOSE 3000
CMD ["node", "index.js"]
