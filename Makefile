.PHONY: install test run up down logs


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
	PYTHONPATH=. DATABASE_URL=sqlite:///file::memory:?cache=shared CELERY_TASK_ALWAYS_EAGER=1 pytest -q