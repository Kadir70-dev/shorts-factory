FROM node:20-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends     chromium ffmpeg fonts-dejavu-core ca-certificates  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY package.json package-lock.json ./
ENV PUPPETEER_SKIP_DOWNLOAD=true
RUN npm ci
COPY . .
RUN npm run threejs:build

ENV NODE_ENV=production
ENV THREEJS_BROWSER_EXECUTABLE=/usr/bin/chromium
EXPOSE 3001
CMD ["npm", "run", "server"]

