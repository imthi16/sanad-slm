# sanad-web — build with pnpm, serve with nginx (CSP self-only baked in).
FROM node:22-slim AS build
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml* ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile
COPY . .
ARG SANAD_MODE=sovereign
ENV SANAD_MODE=$SANAD_MODE
RUN pnpm build
# sovereign gate at image build time (same script as `just verify-no-cdn`)
RUN node scripts/verify-no-cdn.mjs dist

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
RUN sed -i '/^http {/a \    server_tokens off;' /etc/nginx/nginx.conf || true
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s CMD wget -qO- http://127.0.0.1:8080/ >/dev/null || exit 1
