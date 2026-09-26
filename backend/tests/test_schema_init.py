"""init_db() may run in several processes at once against one database.

Production runs two gunicorn workers, and each creates the schema as it starts.
They used to race: on a fresh database both found a table missing, both issued
CREATE TABLE, and the loser failed with "table users already exists" --
which gunicorn answers by stopping the whole server. Four processes released
at the same instant reproduced that failure in three of them, every time.
"""

import multiprocessing as mp
import queue
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, inspect  # noqa: E402

N_PROCESSES = 4


def _init_db(path: str, barrier, errors) -> None:
    from app.database import init_db

    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    barrier.wait()
    try:
        init_db(engine)
    except Exception as exc:  # reported to the parent, which fails the test
        errors.put(f"{type(exc).__name__}: {exc}")
        raise
    finally:
        engine.dispose()


def test_workers_booting_together_create_the_schema_once(tmp_path):
    # spawn, not fork: each process imports the app on its own, as a gunicorn
    # worker without --preload does.
    ctx = mp.get_context("spawn")
    path = tmp_path / "fresh.db"
    barrier = ctx.Barrier(N_PROCESSES)
    errors = ctx.Queue()
    procs = [
        ctx.Process(target=_init_db, args=(str(path), barrier, errors))
        for _ in range(N_PROCESSES)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=120)

    found = []
    while True:
        try:
            found.append(errors.get(timeout=1))
        except queue.Empty:
            break
    assert not found, found
    assert [p.exitcode for p in procs] == [0] * N_PROCESSES

    engine = create_engine(f"sqlite:///{path}")
    try:
        tables = set(inspect(engine).get_table_names())
        columns = {c["name"] for c in inspect(engine).get_columns("users")}
    finally:
        engine.dispose()
    assert {"users", "morning_checkins", "evening_checkins"} <= tables
    assert "timezone" in columns, "the column migrations ran as well"
