# Build frontend once on builder's native architecture. Static output is architecture-independent,
# so npm never runs through QEMU during multi-platform image builds.
FROM --platform=$BUILDPLATFORM node:24-bookworm-slim AS build
WORKDIR /app
ARG NPM_VERSION=12.0.1
RUN npm install --global "npm@${NPM_VERSION}" \
    && node --version \
    && npm --version
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci \
    --no-audit \
    --no-fund \
    --fetch-retries=5 \
    --fetch-retry-mintimeout=20000 \
    --fetch-retry-maxtimeout=120000 \
    --fetch-timeout=600000 \
    --maxsockets=5 \
    || { status=$?; find /root/.npm/_logs -maxdepth 1 -type f -print -exec cat {} \; 2>/dev/null; exit "$status"; }
COPY apps/web ./
RUN npm run build

FROM caddy:2.9-alpine
COPY --from=build /app/dist /srv
COPY deployments/Caddyfile /etc/caddy/Caddyfile
