# Cheminformatics API

FastAPI-based web service for storing molecules (SMILES), substructure search (RDKit), Redis caching, and Celery async
tasks. Includes Dockerized stack with PostgreSQL, Redis, RabbitMQ, and Nginx load balancer.

## Features

- CRUD for molecules (PostgreSQL via SQLAlchemy)
- RDKit substructure search
- Redis caching
- Celery tasks (RabbitMQ broker, Redis backend)
- Nginx load balancing across two app replicas
- Pytest test suite and GitHub Actions CI

## Async runtime

This application runs fully async end-to-end:

- SQLAlchemy AsyncEngine/AsyncSession for database access
- Redis asyncio client for caching
- FastAPI routes and startup lifespan are async
- Celery tasks wrap async DB operations safely

**Driver requirements:**

- **PostgreSQL**: `asyncpg` - Use `postgresql+asyncpg://` in DATABASE_URL
- **SQLite**: `aiosqlite` - Use `sqlite+aiosqlite://` in DATABASE_URL

**Important:** The application uses async drivers (`asyncpg`, `aiosqlite`). Make sure your `DATABASE_URL` specifies the async driver explicitly (e.g., `postgresql+asyncpg://...`). Using sync drivers like `psycopg2` or `pysqlite` will cause errors.

**Environment compatibility:**

- If you provide a synchronous `DATABASE_URL` (e.g., `sqlite:///…` or `postgresql:///…` without a driver), the app auto-normalizes it to async drivers at runtime
- Alembic migrations use synchronous engines (async URLs are automatically mapped to sync equivalents: `psycopg2` for PostgreSQL, `pysqlite` for SQLite)

Local testing:

- The test suite uses `sqlite+aiosqlite` and an in-memory async fake cache.
- Run tests:

```bash
make test
```

Local run:

## Quick start (Docker)

```bash
docker compose up --build or use Makefile: make up
```

Then open http://localhost (via Nginx).

## Configuration via .env

- Copy `.env.example` to `.env` and adjust values.
- The app loads `.env` automatically; docker-compose also uses it for services.

Common variables:

- DATABASE_URL
- REDIS_URL
- RABBITMQ_URL
- CACHE_TTL (default 360)
- UVICORN_PORT

## Local dev

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn src.main:app --reload
```

## API

- POST /molecules/
- GET /molecules/{id}
- PUT /molecules/{id}
- DELETE /molecules/{id}
- GET /molecules/?limit=100&stream=false
- GET /substructure-search/?substructure=SMARTS[&limit=N]
- POST /tasks/substructure
- GET /tasks/{task_id}
- POST /upload/

