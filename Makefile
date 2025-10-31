.PHONY: install test run up down logs up-detached lint migrate revision


# for local development
install:
	python -m pip install --upgrade pip
	pip install -r requirements.txt

run:
	uvicorn src.main:app --reload

# for docker
up:
	docker compose up --build

down:
	docker compose down -v

up-detached:
	docker compose up -d --build

logs:
	docker compose logs -f

# tests
test:
	PYTHONPATH=. DATABASE_URL=sqlite+aiosqlite:///file::memory:?cache=shared CELERY_TASK_ALWAYS_EAGER=1 pytest -q -rA


lint:
	flake8 src tests

# migrations
migrate:
	alembic upgrade head

revision:
	alembic revision --autogenerate -m "update"
