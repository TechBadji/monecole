FROM node:22-slim AS build
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci || npm install

COPY . .

# L'API est servie sous le même domaine, derrière le frontal : une base
# relative évite d'avoir à reconstruire l'image pour changer de domaine.
ENV VITE_API_URL=/api
RUN npm run build

FROM node:22-slim
WORKDIR /app
RUN npm install -g serve
COPY --from=build /app/dist ./dist
EXPOSE 3000
CMD ["serve", "-s", "dist", "-l", "3000"]
