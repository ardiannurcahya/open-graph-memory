FROM node:22-alpine AS build
WORKDIR /app
ARG NPM_VERSION=11.6.2
RUN npm install --global "npm@${NPM_VERSION}" \
    && npm --version
COPY apps/web/package*.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund
COPY apps/web ./
RUN npm run build
FROM caddy:2.9-alpine
COPY --from=build /app/dist /srv
COPY deployments/Caddyfile /etc/caddy/Caddyfile
