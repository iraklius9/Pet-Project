#!/bin/sh
set -e

python - <<'PY'
import asyncio
from src.db import init_db
asyncio.run(init_db())
PY

if [ "${SERVER_ID:-SERVER-1}" = "SERVER-1" ]; then
  echo "Running Alembic migrations on initializer instance (${SERVER_ID})"
  alembic upgrade head
else
  echo "Waiting for DB tables to be ready (instance ${SERVER_ID})"
  python - <<'PY'
import asyncio
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine
from src.db import DATABASE_URL

async def wait():
    engine = create_async_engine(DATABASE_URL)
    for _ in range(120):
        try:
            async with engine.connect() as conn:
                names = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
                if 'molecules' in names:
                    return
        except Exception:
            pass
        await asyncio.sleep(1)
    raise SystemExit('Timed out waiting for DB tables to exist')

asyncio.run(wait())
PY
fi

exec "$@"
