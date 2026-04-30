# Dockerfile for frontend-react (Vite + React)

FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Set DOCKER=1 to use base: '/' in Vite config
ENV DOCKER=1
RUN npm run build

FROM nginx:alpine
WORKDIR /usr/share/nginx/html
# Copy Vite build output (../docs) from build stage
COPY --from=build /app/../docs .
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
