FROM node:22-alpine AS build
WORKDIR /app
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web ./
RUN npm run build
FROM caddy:2.9-alpine
COPY --from=build /app/dist /srv
COPY deployments/Caddyfile /etc/caddy/Caddyfile
