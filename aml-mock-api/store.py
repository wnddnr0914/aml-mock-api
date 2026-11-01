"""단일 프로세스 Mock용 SQLite 저장소."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from models import ErrorInfo, Results, RunStatus
from pipeline import utc_now


class Store:
    def __init__(self, data_dir: str):
        directory = Path(data_dir)
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "mock.db"
        with self.connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE,
                request_json TEXT NOT NULL, status_json TEXT NOT NULL, result_json TEXT
            )""")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                db.row_factory = sqlite3.Row
                yield db
        finally:
            db.close()

    def get(self, run_id):
        with self.connection() as db:
            row = db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return row

    def get_by_key(self, key):
        with self.connection() as db:
            return db.execute("SELECT * FROM runs WHERE idempotency_key = ?", (key,)).fetchone()

    def create(self, status: RunStatus, key, request_json):
        with self.connection() as db:
            db.execute("INSERT INTO runs(run_id,idempotency_key,request_json,status_json) VALUES(?,?,?,?)",
                       (status.run_id, key, request_json, status.model_dump_json()))

    def update(self, status: RunStatus):
        status.updated_at = utc_now()
        with self.connection() as db:
            db.execute("UPDATE runs SET status_json = ? WHERE run_id = ?", (status.model_dump_json(), status.run_id))

    def complete(self, status: RunStatus, result: Results):
        status.updated_at = utc_now()
        with self.connection() as db:
            db.execute("UPDATE runs SET status_json = ?, result_json = ? WHERE run_id = ?",
                       (status.model_dump_json(), result.model_dump_json(), status.run_id))

    def fail_interrupted(self):
        with self.connection() as db:
            rows = db.execute("SELECT status_json FROM runs").fetchall()
            for row in rows:
                status = RunStatus.model_validate_json(row["status_json"])
                if status.status in {"queued", "running"}:
                    status.status, status.stage = "failed", "failed"
                    status.finished_at = status.updated_at = utc_now()
                    status.error = ErrorInfo(code="SERVER_RESTARTED", message="서버가 중단되었습니다. 새 키로 다시 실행하세요.", retryable=True)
                    db.execute("UPDATE runs SET status_json = ? WHERE run_id = ?", (status.model_dump_json(), status.run_id))


def canonical_request(request):
    return json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
