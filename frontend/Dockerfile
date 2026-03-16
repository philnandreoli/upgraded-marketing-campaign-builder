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

EXPOSE 80

# envsubst replaces ${BACKEND_URL} and ${NGINX_PORT} at container start,
# while leaving nginx's own $host / $uri variables intact.
CMD ["sh", "-c", "envsubst '${BACKEND_URL} ${NGINX_PORT}' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]
