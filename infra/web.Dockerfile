FROM node:20.18-alpine AS base

WORKDIR /app

FROM base AS deps

COPY web/package.json web/package-lock.json ./web/
COPY packages ./packages

WORKDIR /app/web
RUN npm ci

FROM deps AS build

COPY web/tsconfig.json web/next.config.ts web/next-env.d.ts ./
COPY web/src ./src
COPY web/public ./public

RUN npm run build

FROM base AS runner

ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000

WORKDIR /app/web

COPY web/package.json web/package-lock.json ./
COPY packages ./packages
RUN npm ci --omit=dev

COPY --from=build /app/web/.next ./.next
COPY --from=build /app/web/public ./public

RUN addgroup -S appgroup \
    && adduser -S appuser -G appgroup \
    && chown -R appuser:appgroup /app/web

USER appuser

EXPOSE 3000

CMD ["npm", "run", "start"]
