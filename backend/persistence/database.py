import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self, presets: dict[str, dict[str, Any]], music_presets: dict[str, list[tuple[str, str, str, str]]] | None = None) -> None:
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL,
                request_json TEXT NOT NULL, artifact_name TEXT, artifact_url TEXT,
                error TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL,
                completed_at REAL, elapsed_seconds REAL, width INTEGER,
                height INTEGER, duration_seconds REAL, artifact_media_type TEXT,
                artifact_size INTEGER, artifacts_json TEXT,
                task_dir TEXT, manifest_path TEXT, parent_job_id TEXT,
                revision INTEGER DEFAULT 1, comfy_prompt_id TEXT,
                project_id TEXT
            );
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY, name TEXT NOT NULL,
                output_subdir TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                content_summary TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                created_at REAL NOT NULL, updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS workspace_projects (
                workspace_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            );
            CREATE TABLE IF NOT EXISTS artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                filename TEXT NOT NULL, path TEXT NOT NULL, media_type TEXT,
                size INTEGER DEFAULT 0, created_at REAL NOT NULL,
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            );
            CREATE TABLE IF NOT EXISTS voice_presets (
                id INTEGER PRIMARY KEY AUTOINCREMENT, preset_key TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL, speaker TEXT DEFAULT '', language TEXT DEFAULT 'Chinese',
                model TEXT DEFAULT '', instruction TEXT NOT NULL, enabled INTEGER DEFAULT 1,
                sort_order INTEGER DEFAULT 0, created_at REAL NOT NULL, updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS creative_presets (
                id TEXT NOT NULL, domain TEXT NOT NULL, category TEXT NOT NULL,
                name TEXT NOT NULL, description TEXT DEFAULT '', instruction TEXT NOT NULL,
                config_json TEXT DEFAULT '{}', source TEXT DEFAULT 'user', enabled INTEGER DEFAULT 1,
                sort_order INTEGER DEFAULT 0, created_at REAL NOT NULL, updated_at REAL NOT NULL,
                PRIMARY KEY(domain, category, id),
                UNIQUE(domain, category, name)
            );
            CREATE TABLE IF NOT EXISTS api_idempotency (
                key TEXT PRIMARY KEY, job_id TEXT NOT NULL, created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS collaborations (
                id TEXT PRIMARY KEY, capability_id TEXT NOT NULL,
                model_id TEXT NOT NULL, mode_id TEXT NOT NULL,
                status TEXT NOT NULL, request_json TEXT NOT NULL,
                result_json TEXT DEFAULT '{}', revision INTEGER DEFAULT 0,
                job_id TEXT, progress_json TEXT DEFAULT '{}', state_json TEXT DEFAULT '{}',
                client_request_id TEXT, error TEXT, started_at REAL, completed_at REAL,
                project_id TEXT,
                created_at REAL NOT NULL, updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS api_collaboration_idempotency (
                key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
                collaboration_id TEXT NOT NULL,
                FOREIGN KEY(collaboration_id) REFERENCES collaborations(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS collaboration_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collaboration_id TEXT NOT NULL, role TEXT NOT NULL,
                content TEXT NOT NULL, created_at REAL NOT NULL,
                FOREIGN KEY(collaboration_id) REFERENCES collaborations(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_collaboration_messages
                ON collaboration_messages(collaboration_id, id);
            CREATE TABLE IF NOT EXISTS collaboration_requests (
                request_id TEXT PRIMARY KEY, collaboration_id TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY(collaboration_id) REFERENCES collaborations(id) ON DELETE CASCADE
            );
            """)
            preset_schema = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='creative_presets'").fetchone()["sql"]
            if "id TEXT PRIMARY KEY" in preset_schema:
                db.executescript("""
                ALTER TABLE creative_presets RENAME TO creative_presets_legacy;
                CREATE TABLE creative_presets (
                    id TEXT NOT NULL, domain TEXT NOT NULL, category TEXT NOT NULL,
                    name TEXT NOT NULL, description TEXT DEFAULT '', instruction TEXT NOT NULL,
                    config_json TEXT DEFAULT '{}', source TEXT DEFAULT 'user', enabled INTEGER DEFAULT 1,
                    sort_order INTEGER DEFAULT 0, created_at REAL NOT NULL, updated_at REAL NOT NULL,
                    PRIMARY KEY(domain, category, id), UNIQUE(domain, category, name)
                );
                INSERT INTO creative_presets SELECT * FROM creative_presets_legacy;
                DROP TABLE creative_presets_legacy;
                """)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(voice_presets)").fetchall()}
            if "sample_audio_name" not in columns:
                db.execute("ALTER TABLE voice_presets ADD COLUMN sample_audio_name TEXT")
            if "sample_audio_url" not in columns:
                db.execute("ALTER TABLE voice_presets ADD COLUMN sample_audio_url TEXT")
            if "profile_version" not in columns:
                db.execute("ALTER TABLE voice_presets ADD COLUMN profile_version INTEGER DEFAULT 1")
            job_columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)").fetchall()}
            for name, definition in {
                "elapsed_seconds": "REAL",
                "width": "INTEGER",
                "height": "INTEGER",
                "duration_seconds": "REAL",
                "artifact_media_type": "TEXT",
                "artifact_size": "INTEGER",
                "artifacts_json": "TEXT",
                "task_dir": "TEXT",
                "manifest_path": "TEXT",
                "parent_job_id": "TEXT",
                "revision": "INTEGER DEFAULT 1",
                "comfy_prompt_id": "TEXT",
                "project_id": "TEXT",
            }.items():
                if name not in job_columns:
                    db.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
            unassigned_id = "project-unassigned"
            now = time.time()
            db.execute(
                "INSERT OR IGNORE INTO projects (id, name, output_subdir, status, created_at, updated_at) VALUES (?, ?, ?, 'active', ?, ?)",
                (unassigned_id, "未归档项目", "_unassigned", now, now),
            )
            collaboration_columns = {row["name"] for row in db.execute("PRAGMA table_info(collaborations)").fetchall()}
            for name, definition in {
                "progress_json": "TEXT DEFAULT '{}'",
                "state_json": "TEXT DEFAULT '{}'",
                "client_request_id": "TEXT",
                "error": "TEXT",
                "started_at": "REAL",
                "completed_at": "REAL",
                "project_id": "TEXT",
            }.items():
                if name not in collaboration_columns:
                    db.execute(f"ALTER TABLE collaborations ADD COLUMN {name} {definition}")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_collaboration_request_id ON collaborations(client_request_id) WHERE client_request_id IS NOT NULL")
            # Older collaborations stored the project only inside the request
            # payload. Normalize that legacy ownership once so all consumers
            # use the same top-level field.
            legacy_rows = db.execute(
                "SELECT id, project_id, request_json FROM collaborations "
                "WHERE project_id IS NULL OR project_id=''"
            ).fetchall()
            for row in legacy_rows:
                project_id = self._project_id_from_request_json(row["request_json"])
                if project_id:
                    db.execute("UPDATE collaborations SET project_id=? WHERE id=?", (project_id, row["id"]))
            now = time.time()
            for index, (key, value) in enumerate(presets.items()):
                db.execute("""INSERT OR IGNORE INTO voice_presets
                    (preset_key, display_name, speaker, language, model, instruction, sort_order, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
                        key, value.get("display_name", key), value.get("speaker", ""),
                        value.get("language", "Chinese"), value.get("model", ""),
                        value.get("instruction", ""), index, now, now))
                if value.get("sample_audio_name"):
                    db.execute("""UPDATE voice_presets
                        SET display_name=?, model=?, instruction=?, sample_audio_name=?, sample_audio_url=?, updated_at=?
                        WHERE preset_key=?""", (
                            value.get("display_name", key), value.get("model", ""),
                            value.get("instruction", ""), value["sample_audio_name"],
                            f"/v1/voices/{key}/sample", now, key,
                        ))
                # Upgrade bundled profiles once; future user edits are kept.
                db.execute("""UPDATE voice_presets SET display_name=?, instruction=?, profile_version=2, updated_at=?
                    WHERE preset_key=? AND COALESCE(profile_version, 1) < 2""", (
                        value.get("display_name", key), value.get("instruction", ""), now, key))
            for category, items in (music_presets or {}).items():
                for index, (key, name, description, instruction) in enumerate(items):
                    db.execute("""INSERT OR IGNORE INTO creative_presets
                        (id, domain, category, name, description, instruction, source, sort_order, created_at, updated_at)
                        VALUES (?, 'music', ?, ?, ?, ?, 'builtin', ?, ?, ?)""",
                        (key, category, name, description, instruction, index, now, now))
            self.compact_job_requests(db)

    @staticmethod
    def compact_job_requests(db: sqlite3.Connection) -> None:
        """Remove media payloads already persisted in each task package."""
        rows = db.execute("SELECT id, request_json FROM jobs").fetchall()
        for row in rows:
            try:
                request = json.loads(row["request_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            compact = dict(request)
            compact.pop("references", None)
            compact.pop("reference_audio", None)
            if isinstance(compact.get("params"), dict):
                compact["params"] = dict(compact["params"])
                compact["params"].pop("videos", None)
                compact["params"].pop("audios", None)
            encoded = json.dumps(compact, ensure_ascii=False)
            if encoded != row["request_json"]:
                db.execute("UPDATE jobs SET request_json=? WHERE id=?", (encoded, row["id"]))

    def jobs(self, limit: int | None = 500, project_id: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as db:
            query = "SELECT * FROM jobs"
            values: list[Any] = []
            if project_id:
                query += " WHERE project_id=?"
                values.append(project_id)
            query += " ORDER BY created_at DESC"
            if limit is not None:
                query += " LIMIT ?"
                values.append(limit)
            rows = db.execute(query, values).fetchall()
        return [self._job(row) for row in rows]

    def pending_jobs(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM jobs WHERE status IN ('queued','running') ORDER BY created_at"
            ).fetchall()
        return [self._job(row) for row in rows]

    def job(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return self._job(row) if row else None

    def insert_job(self, job: dict[str, Any]) -> None:
        with self.connect() as db:
            db.execute("""INSERT INTO jobs (id, kind, status, request_json, created_at, updated_at, width, height, duration_seconds, task_dir, manifest_path, parent_job_id, revision, project_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
                job["id"], job["kind"], job["status"], json.dumps(job["request"], ensure_ascii=False),
                job["created_at"], job["created_at"], job.get("width"), job.get("height"), job.get("duration_seconds"),
                job.get("task_dir"), job.get("manifest_path"), job.get("parent_job_id"), job.get("revision", 1), job.get("project_id", "project-unassigned"),
            ))

    def update_job(self, job_id: str, values: dict[str, Any]) -> None:
        allowed = {key: value for key, value in values.items() if key in {"status", "artifact_name", "artifact_url", "error", "completed_at", "updated_at", "elapsed_seconds", "width", "height", "duration_seconds", "artifact_media_type", "artifact_size", "artifacts_json", "task_dir", "manifest_path", "parent_job_id", "revision", "comfy_prompt_id", "project_id"}}
        if not allowed:
            return
        allowed["updated_at"] = time.time()
        fields = ", ".join(f"{key}=?" for key in allowed)
        with self.connect() as db:
            db.execute(f"UPDATE jobs SET {fields} WHERE id=?", (*allowed.values(), job_id))

    def update_job_request(self, job_id: str, request: dict[str, Any]) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE jobs SET request_json=?, updated_at=? WHERE id=?",
                (json.dumps(request, ensure_ascii=False), time.time(), job_id),
            )

    def add_artifact(self, job_id: str, path: Path, media_type: str) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO artifacts (job_id, filename, path, media_type, size, created_at) VALUES (?, ?, ?, ?, ?, ?)", (job_id, path.name, str(path), media_type, path.stat().st_size if path.exists() else 0, time.time()))

    def artifact_names(self, job_id: str) -> list[str]:
        with self.connect() as db:
            rows = db.execute("SELECT filename FROM artifacts WHERE job_id=?", (job_id,)).fetchall()
        return [row["filename"] for row in rows if row["filename"]]

    def delete_job(self, job_id: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM api_idempotency WHERE job_id=?", (job_id,))
            db.execute("DELETE FROM artifacts WHERE job_id=?", (job_id,))
            db.execute("DELETE FROM jobs WHERE id=?", (job_id,))

    def projects(self, include_archived: bool = False) -> list[dict[str, Any]]:
        query = "SELECT p.*, COUNT(DISTINCT j.id) AS job_count, COUNT(DISTINCT a.id) AS artifact_count " \
                "FROM projects p LEFT JOIN jobs j ON j.project_id=p.id LEFT JOIN artifacts a ON a.job_id=j.id"
        if not include_archived:
            query += " WHERE p.status='active'"
        query += " GROUP BY p.id ORDER BY CASE WHEN p.id='project-unassigned' THEN 1 ELSE 0 END, p.updated_at DESC"
        with self.connect() as db:
            return [dict(row) for row in db.execute(query).fetchall()]

    def project(self, project_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        return dict(row) if row else None

    def create_project(self, value: dict[str, Any]) -> dict[str, Any]:
        now = time.time()
        with self.connect() as db:
            db.execute(
                "INSERT INTO projects (id, name, output_subdir, description, content_summary, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'active', ?, ?)",
                (value["id"], value["name"], value["output_subdir"], value.get("description", ""), value.get("content_summary", ""), now, now),
            )
        return self.project(value["id"]) or value

    def archive_project(self, project_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            db.execute("UPDATE projects SET status='archived', updated_at=? WHERE id=?", (time.time(), project_id))
        return self.project(project_id)

    def update_project(self, project_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {key: values[key] for key in ("name", "description", "content_summary") if key in values}
        if not allowed:
            return self.project(project_id)
        allowed["updated_at"] = time.time()
        fields = ", ".join(f"{key}=?" for key in allowed)
        with self.connect() as db:
            db.execute(f"UPDATE projects SET {fields} WHERE id=?", (*allowed.values(), project_id))
        return self.project(project_id)

    def delete_project(self, project_id: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM workspace_projects WHERE project_id=?", (project_id,))
            db.execute("DELETE FROM api_idempotency WHERE job_id IN (SELECT id FROM jobs WHERE project_id=?)", (project_id,))
            db.execute("DELETE FROM artifacts WHERE job_id IN (SELECT id FROM jobs WHERE project_id=?)", (project_id,))
            db.execute("DELETE FROM jobs WHERE project_id=?", (project_id,))
            db.execute("DELETE FROM projects WHERE id=?", (project_id,))

    def current_project(self, workspace_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT p.* FROM workspace_projects w JOIN projects p ON p.id=w.project_id WHERE w.workspace_id=?",
                (workspace_id,),
            ).fetchone()
        return dict(row) if row else None

    def set_current_project(self, workspace_id: str, project_id: str) -> dict[str, Any] | None:
        now = time.time()
        with self.connect() as db:
            db.execute(
                "INSERT INTO workspace_projects (workspace_id, project_id, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(workspace_id) DO UPDATE SET project_id=excluded.project_id, updated_at=excluded.updated_at",
                (workspace_id, project_id, now),
            )
        return self.current_project(workspace_id)

    def presets(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM voice_presets WHERE enabled=1 ORDER BY sort_order, id").fetchall()
        return [dict(row) for row in rows]

    def preset(self, preset_key: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM voice_presets WHERE preset_key=? AND enabled=1", (preset_key,)).fetchone()
        return dict(row) if row else None

    def create_preset(self, values: dict[str, Any]) -> dict[str, Any]:
        now = time.time()
        key = values["preset_key"]
        with self.connect() as db:
            cursor = db.execute("""INSERT INTO voice_presets
                (preset_key, display_name, speaker, language, model, instruction, sort_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", (key, values["display_name"], values.get("speaker", ""), values.get("language", "Chinese"), values.get("model", ""), values["instruction"], values.get("sort_order", 99), now, now))
            row = db.execute("SELECT * FROM voice_presets WHERE id=?", (cursor.lastrowid,)).fetchone()
        return dict(row)

    def update_preset(self, preset_key: str, values: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {key: values[key] for key in ("display_name", "instruction", "speaker", "language", "model") if key in values}
        if not allowed:
            return self.preset(preset_key)
        # Metadata changes invalidate the generated reference sample. The
        # workbench must explicitly regenerate it so the sample cannot drift
        # away from the edited preset definition.
        allowed["sample_audio_name"] = None
        allowed["sample_audio_url"] = None
        allowed["updated_at"] = time.time()
        fields = ", ".join(f"{key}=?" for key in allowed)
        with self.connect() as db:
            db.execute(f"UPDATE voice_presets SET {fields} WHERE preset_key=? AND enabled=1", (*allowed.values(), preset_key))
            row = db.execute("SELECT * FROM voice_presets WHERE preset_key=? AND enabled=1", (preset_key,)).fetchone()
        return dict(row) if row else None

    def update_sample(self, preset_key: str, filename: str) -> dict[str, Any] | None:
        with self.connect() as db:
            db.execute("UPDATE voice_presets SET sample_audio_name=?, sample_audio_url=?, updated_at=? WHERE preset_key=? AND enabled=1", (filename, f"/v1/voices/{preset_key}/sample", time.time(), preset_key))
            row = db.execute("SELECT * FROM voice_presets WHERE preset_key=? AND enabled=1", (preset_key,)).fetchone()
        return dict(row) if row else None

    def disable_preset(self, preset_key: str) -> bool:
        with self.connect() as db:
            cursor = db.execute("UPDATE voice_presets SET enabled=0, updated_at=? WHERE preset_key=? AND enabled=1", (time.time(), preset_key))
        return cursor.rowcount > 0

    def creative_presets(self, domain: str, category: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM creative_presets WHERE domain=? AND enabled=1"
        values: list[Any] = [domain]
        if category:
            query += " AND category=?"
            values.append(category)
        query += " ORDER BY category, sort_order, name"
        with self.connect() as db:
            rows = db.execute(query, values).fetchall()
        return [self._creative_preset(row) for row in rows]

    def creative_preset(self, domain: str, category: str, preset_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM creative_presets WHERE domain=? AND category=? AND id=? AND enabled=1", (domain, category, preset_id)).fetchone()
        return self._creative_preset(row) if row else None

    def save_creative_preset(self, values: dict[str, Any], update: bool = False) -> dict[str, Any]:
        now = time.time()
        preset_id = values["id"]
        with self.connect() as db:
            identity = (values["domain"], values["category"], preset_id)
            existing = db.execute("SELECT source FROM creative_presets WHERE domain=? AND category=? AND id=?", identity).fetchone()
            if existing and not update:
                raise ValueError("preset already exists")
            if existing:
                db.execute("""UPDATE creative_presets SET name=?, description=?, instruction=?, config_json=?, enabled=1, updated_at=? WHERE domain=? AND category=? AND id=?""", (
                    values["name"], values.get("description", ""), values["instruction"],
                    json.dumps(values.get("config", {}), ensure_ascii=False), now, *identity))
            else:
                db.execute("""INSERT INTO creative_presets
                    (id, domain, category, name, description, instruction, config_json, source, sort_order, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
                    preset_id, values["domain"], values["category"], values["name"], values.get("description", ""),
                    values["instruction"], json.dumps(values.get("config", {}), ensure_ascii=False),
                    values.get("source", "ai"), values.get("sort_order", 99), now, now))
            row = db.execute("SELECT * FROM creative_presets WHERE domain=? AND category=? AND id=?", identity).fetchone()
        return self._creative_preset(row)

    def disable_creative_preset(self, domain: str, category: str, preset_id: str) -> bool:
        with self.connect() as db:
            cursor = db.execute("UPDATE creative_presets SET enabled=0, updated_at=? WHERE domain=? AND category=? AND id=? AND enabled=1", (time.time(), domain, category, preset_id))
        return cursor.rowcount > 0

    def idempotent_job(self, key: str) -> str | None:
        with self.connect() as db:
            row = db.execute("SELECT job_id FROM api_idempotency WHERE key=?", (key,)).fetchone()
        return row["job_id"] if row else None

    def save_idempotent_job(self, key: str, job_id: str) -> None:
        with self.connect() as db:
            db.execute("""INSERT INTO api_idempotency (key, job_id, created_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET job_id=excluded.job_id, created_at=excluded.created_at""",
                (key, job_id, time.time()))

    def create_collaboration(self, value: dict[str, Any], *, idempotency_key: str | None = None,
                             fingerprint: str = "") -> dict[str, Any]:
        now = time.time()
        with self.connect() as db:
            if idempotency_key:
                # Claim and create in one transaction, including concurrent retries.
                db.execute("BEGIN IMMEDIATE")
                existing = db.execute("SELECT fingerprint, collaboration_id FROM api_collaboration_idempotency WHERE key=?", (idempotency_key,)).fetchone()
                if existing:
                    if existing["fingerprint"] != fingerprint:
                        raise ValueError("幂等键已用于不同的生成请求，请为新请求使用新键")
                    row = db.execute("SELECT * FROM collaborations WHERE id=?", (existing["collaboration_id"],)).fetchone()
                    return self._collaboration(row)
            db.execute("""INSERT INTO collaborations
                (id, capability_id, model_id, mode_id, status, request_json,
                 result_json, revision, job_id, progress_json, state_json,
                 client_request_id, error, started_at, completed_at, project_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
                value["id"], value["capability_id"], value["model_id"], value["mode_id"],
                value.get("status", "processing"), json.dumps(value["request"], ensure_ascii=False),
                json.dumps(value.get("result", {}), ensure_ascii=False), value.get("revision", 0),
                value.get("job_id"), json.dumps(value.get("progress", {}), ensure_ascii=False),
                json.dumps(value.get("state", {}), ensure_ascii=False), value.get("client_request_id"),
                value.get("error"), value.get("started_at"), value.get("completed_at"),
                value.get("project_id") or self._project_id_from_value(value.get("request", {})), now, now,
            ))
            if idempotency_key:
                db.execute("INSERT INTO api_collaboration_idempotency VALUES (?, ?, ?)",
                           (idempotency_key, fingerprint, value["id"]))
        return self.collaboration(value["id"])

    def collaboration(self, collaboration_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM collaborations WHERE id=?", (collaboration_id,)).fetchone()
        return self._collaboration(row) if row else None

    def collaboration_by_request_id(self, request_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM collaborations WHERE client_request_id=?", (request_id,)).fetchone()
        return self._collaboration(row) if row else None

    def collaboration_for_turn(self, request_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("""SELECT c.* FROM collaborations c
                JOIN collaboration_requests r ON r.collaboration_id=c.id
                WHERE r.request_id=?""", (request_id,)).fetchone()
        return self._collaboration(row) if row else None

    def save_collaboration_turn(self, request_id: str, collaboration_id: str) -> None:
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO collaboration_requests (request_id, collaboration_id, created_at) VALUES (?, ?, ?)",
                       (request_id, collaboration_id, time.time()))

    def collaborations(self, statuses: tuple[str, ...] | None = None, limit: int = 50) -> list[dict[str, Any]]:
        query = "SELECT * FROM collaborations"
        values: list[Any] = []
        if statuses:
            query += f" WHERE status IN ({','.join('?' for _ in statuses)})"
            values.extend(statuses)
        query += " ORDER BY updated_at DESC LIMIT ?"
        values.append(limit)
        with self.connect() as db:
            rows = db.execute(query, values).fetchall()
        return [self._collaboration(row) for row in rows]

    def update_collaboration(self, collaboration_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {
            key: values[key] for key in (
                "status", "result", "revision", "job_id", "progress", "state",
                "error", "started_at", "completed_at", "request", "project_id",
            )
            if key in values
        }
        if not allowed:
            return self.collaboration(collaboration_id)
        if "result" in allowed:
            allowed["result_json"] = json.dumps(allowed.pop("result"), ensure_ascii=False)
        if "progress" in allowed:
            allowed["progress_json"] = json.dumps(allowed.pop("progress"), ensure_ascii=False)
        if "state" in allowed:
            allowed["state_json"] = json.dumps(allowed.pop("state"), ensure_ascii=False)
        if "request" in allowed:
            allowed["request_json"] = json.dumps(allowed.pop("request"), ensure_ascii=False)
        if "project_id" in allowed and not allowed["project_id"]:
            allowed["project_id"] = None
        allowed["updated_at"] = time.time()
        fields = ", ".join(f"{key}=?" for key in allowed)
        with self.connect() as db:
            db.execute(f"UPDATE collaborations SET {fields} WHERE id=?", (*allowed.values(), collaboration_id))
        return self.collaboration(collaboration_id)

    def claim_collaboration(self, collaboration_id: str) -> bool:
        """Atomically claim a queued collaboration for the worker."""
        now = time.time()
        with self.connect() as db:
            cursor = db.execute(
                "UPDATE collaborations SET status='running', started_at=?, error=NULL, updated_at=? "
                "WHERE id=? AND status='queued'",
                (now, now, collaboration_id),
            )
        return cursor.rowcount == 1

    def add_collaboration_message(self, collaboration_id: str, role: str, content: str) -> None:
        with self.connect() as db:
            db.execute("""INSERT INTO collaboration_messages
                (collaboration_id, role, content, created_at) VALUES (?, ?, ?, ?)""",
                (collaboration_id, role, content, time.time()))

    def collaboration_messages(self, collaboration_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("""SELECT role, content, created_at FROM collaboration_messages
                WHERE collaboration_id=? ORDER BY id""", (collaboration_id,)).fetchall()
        return [dict(row) for row in rows]

    def delete_collaboration(self, collaboration_id: str) -> bool:
        with self.connect() as db:
            cursor = db.execute("DELETE FROM collaborations WHERE id=?", (collaboration_id,))
        return cursor.rowcount > 0

    def prune_collaborations(self, cutoff: float) -> list[str]:
        terminal = ("submitted", "cancelled", "abandoned", "failed", "interrupted")
        with self.connect() as db:
            rows = db.execute(
                f"SELECT id FROM collaborations WHERE status IN ({','.join('?' for _ in terminal)}) AND updated_at < ?",
                (*terminal, cutoff),
            ).fetchall()
            ids = [row["id"] for row in rows]
            if ids:
                db.executemany("DELETE FROM collaborations WHERE id=?", ((item,) for item in ids))
        return ids

    def settings(self) -> dict[str, str]:
        with self.connect() as db:
            return {row["key"]: row["value"] for row in db.execute("SELECT key, value FROM settings")}

    def save_settings(self, values: dict[str, Any]) -> None:
        now = time.time()
        with self.connect() as db:
            for key, value in values.items():
                db.execute("INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at", (key, str(value), now))

    @staticmethod
    def _job(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["request"] = json.loads(item.pop("request_json"))
        raw_artifacts = item.pop("artifacts_json", None)
        if raw_artifacts:
            try:
                item["artifacts"] = json.loads(raw_artifacts)
            except json.JSONDecodeError:
                item["artifacts"] = []
        return {key: value for key, value in item.items() if value is not None}

    @staticmethod
    def _creative_preset(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        try:
            item["config"] = json.loads(item.pop("config_json", "{}"))
        except json.JSONDecodeError:
            item["config"] = {}
        item["enabled"] = bool(item.get("enabled"))
        return item

    @staticmethod
    def _collaboration(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        for source, target in (
            ("request_json", "request"), ("result_json", "result"),
            ("progress_json", "progress"), ("state_json", "state"),
        ):
            try:
                item[target] = json.loads(item.pop(source) or "{}")
            except json.JSONDecodeError:
                item[target] = {}
        if not item.get("project_id"):
            item["project_id"] = Database._project_id_from_value(item.get("request", {}))
        return {key: value for key, value in item.items() if value is not None}

    @staticmethod
    def _project_id_from_request_json(raw: str | None) -> str | None:
        try:
            value = json.loads(raw or "{}")
        except (TypeError, json.JSONDecodeError):
            return None
        return Database._project_id_from_value(value)

    @staticmethod
    def _project_id_from_value(value: Any) -> str | None:
        if isinstance(value, dict):
            for key in ("project_id", "_project_id"):
                candidate = value.get(key)
                if candidate:
                    return str(candidate)
            for child in value.values():
                found = Database._project_id_from_value(child)
                if found:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = Database._project_id_from_value(child)
                if found:
                    return found
        return None
