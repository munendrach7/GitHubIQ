# Build stage
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

# Serve stage
FROM nginx:1.27-alpine
# Only substitute BACKEND_URL, leaving nginx's own $uri/$host vars intact.
ENV BACKEND_URL=http://backend:8000
ENV NGINX_ENVSUBST_FILTER=BACKEND_URL
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
