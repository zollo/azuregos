# ── Dev target (Vite dev server, source bind-mounted) ────────────────────
FROM node:20-alpine AS dev
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# ── Build target ─────────────────────────────────────────────────────────
FROM node:20-alpine AS build
WORKDIR /app
# Empty by default => the SPA uses same-origin relative /api (nginx proxies it).
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

# ── Prod target (static files via nginx) ─────────────────────────────────
FROM nginx:1.27-alpine AS prod
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
# Use 127.0.0.1 (not localhost): busybox wget may try ::1 first, but nginx
# listens on IPv4 only, which would make the check fail spuriously.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:80/ || exit 1
