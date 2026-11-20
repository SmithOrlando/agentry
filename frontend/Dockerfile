# Stage 1: build the Vue app.
# Debian-based (not Alpine): Rollup's native parser needs more stack than Alpine's musl gives threads,
# and fails there with "Code is nested too deeply" on Vue's runtime files.
FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY . .
RUN npm run build

# Stage 2: serve it with nginx (which also proxies /api and /webhooks to Flask)
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
