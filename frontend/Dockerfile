# syntax=docker/dockerfile:1

# Stage 1: Build frontend
FROM node:22-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

ARG VITE_USE_API=true
ARG API_TARGET=http://localhost:8000
ARG API_APP_KEY=zapominalka-secret-key
ARG API_DEV_USER_ID=12345678

ENV VITE_USE_API=${VITE_USE_API} \
    API_TARGET=${API_TARGET} \
    API_APP_KEY=${API_APP_KEY} \
    API_DEV_USER_ID=${API_DEV_USER_ID}

RUN npm run build

# Stage 2: Serve with Nginx
FROM nginx:alpine AS production

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
