FROM node:20-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends     chromium ffmpeg fonts-dejavu-core ca-certificates  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .

ENV NODE_ENV=production
EXPOSE 3001
CMD ["npm", "run", "server"]

