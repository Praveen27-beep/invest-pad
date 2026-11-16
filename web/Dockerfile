FROM node:22-slim
WORKDIR /srv
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# The backend address is fixed when the app is built (Next records rewrites at build time).
ARG API_URL=http://api:8000
ENV API_URL=$API_URL
RUN npm run build
CMD ["npm", "run", "start"]
