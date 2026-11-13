# syntax=docker/dockerfile:1
# One Dockerfile for all three apps: build with --build-arg APP=web|seller|admin.
FROM node:20-alpine AS base
RUN corepack enable
WORKDIR /repo

FROM base AS build
ARG APP
COPY . .
RUN pnpm install --frozen-lockfile
RUN pnpm --filter "@sanad/${APP}" build

FROM node:20-alpine AS runtime
ARG APP
ENV NODE_ENV=production APP=${APP} HOSTNAME=0.0.0.0
WORKDIR /app
COPY --from=build --chown=node:node /repo/apps/${APP}/.next/standalone ./
COPY --from=build --chown=node:node /repo/apps/${APP}/.next/static ./apps/${APP}/.next/static
USER node
HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
  CMD wget -qO- "http://127.0.0.1:${PORT}${HEALTH_PATH:-/}" >/dev/null || exit 1
CMD ["sh", "-c", "node apps/${APP}/server.js"]
