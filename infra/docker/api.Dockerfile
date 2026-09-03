# Stage 1: Build React Frontends
FROM node:22-slim AS frontend-builder
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable

WORKDIR /app
COPY . .
RUN pnpm install
RUN pnpm --filter "@restaurantos/pos-web" build
RUN pnpm --filter "@restaurantos/admin-web" build
RUN pnpm --filter "@restaurantos/kds-web" build
RUN pnpm --filter "@restaurantos/mobile-web" build
RUN pnpm --filter "@restaurantos/landing-web" build

# Stage 2: Build Python Backend
FROM python:3.12-slim

WORKDIR /app

# Copy built frontends to static directory
COPY --from=frontend-builder /app/apps/pos-web/dist /app/static/pos-web
COPY --from=frontend-builder /app/apps/admin-web/dist /app/static/admin-web
COPY --from=frontend-builder /app/apps/kds-web/dist /app/static/kds-web
COPY --from=frontend-builder /app/apps/mobile-web/dist /app/static/mobile-web
COPY --from=frontend-builder /app/apps/landing-web/dist /app/static/landing-web

COPY *.XLS /app/
COPY *.XLS /app/apps/api/
COPY *.xlsx /app/
COPY *.xlsx /app/apps/api/

COPY apps/api /app/apps/api
WORKDIR /app/apps/api
RUN pip install --no-cache-dir -e .

ENV RESTAURANTOS_PUBLIC_ORDER_INTENTS_ENABLED="true"

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn restaurant_os.main:app --host 0.0.0.0 --port 8000"]

