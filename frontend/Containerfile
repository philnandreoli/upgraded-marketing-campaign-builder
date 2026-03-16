# ---------- Stage 1: Build ----------
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Vite embeds VITE_* variables at build time via import.meta.env.
# Pass them as build args so the bundled JS contains the correct values.
ARG VITE_AZURE_CLIENT_ID
ARG VITE_AZURE_TENANT_ID
ARG VITE_REDIRECT_URI
ARG VITE_API_SCOPE

RUN npm run build

# ---------- Stage 2: Serve ----------
FROM nginx:stable-alpine

# Copy built assets
COPY --from=build /app/dist /usr/share/nginx/html

# Copy nginx config as a template (uses $BACKEND_URL, $NGINX_PORT)
COPY nginx.conf /etc/nginx/templates/default.conf.template

# Defaults — override at runtime via environment variables
ENV BACKEND_URL=http://backend:8000
ENV NGINX_PORT=80

# Only substitute BACKEND_URL and NGINX_PORT — leave nginx's own
# $host, $uri, $remote_addr, $http_upgrade etc. intact.
ENV NGINX_ENVSUBST_FILTER=^(BACKEND_URL|NGINX_PORT)$

EXPOSE 80

# The nginx:stable-alpine entrypoint automatically runs envsubst on
# templates in /etc/nginx/templates/, substituting only defined env vars
# (BACKEND_URL, NGINX_PORT) while leaving nginx's own $host/$uri intact.
