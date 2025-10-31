import asyncio
from typing import Optional

from src.celery_app import celery_app
from src.chemistry import substructure_search
from src.db import db_session_scope
from src.utils import _get_smiles_list


@celery_app.task(name="tasks.substructure_search_db")
def substructure_search_db(substructure: str, limit: Optional[int] = None):
    async def _run():
        async with db_session_scope() as db:
            smiles_list = await _get_smiles_list(db)
        hits = substructure_search(smiles_list, substructure, limit)
        if limit is not None:
            hits = hits[:limit]
        return hits

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_run())
    finally:
        loop.close()
