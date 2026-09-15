FROM node:20.18.3-alpine AS build
RUN npm install --global pnpm@9.15.5
WORKDIR /workspace
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml tsconfig.base.json ./
COPY apps/web/package.json apps/web/package.json
RUN pnpm install --frozen-lockfile --filter @jobos/web...
COPY apps/web apps/web
RUN pnpm --filter @jobos/web build

FROM node:20.18.3-alpine
WORKDIR /site
COPY --from=build /workspace/apps/web/dist ./
COPY apps/web/server.mjs /server.mjs
USER 10001
CMD ["node", "/server.mjs"]
