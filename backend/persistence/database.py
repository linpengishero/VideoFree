# Copyright (c) 2026 VideoFree Studio individual project author and contributors.
# Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

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
                ai_created INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL, updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS project_categories (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL, name TEXT NOT NULL,
                UNIQUE(project_id, name),
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS project_assets (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                name TEXT NOT NULL, kind TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
                media_json TEXT NOT NULL DEFAULT '[]',
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS project_asset_types (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL, updated_at REAL NOT NULL,
                UNIQUE(project_id, name),
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS plugin_documents (
                plugin_id TEXT NOT NULL, id TEXT NOT NULL, project_id TEXT NOT NULL,
                category_id TEXT NOT NULL DEFAULT '',
                document_json TEXT NOT NULL, references_json TEXT NOT NULL DEFAULT '[]',
                active INTEGER NOT NULL DEFAULT 0, updated_at REAL NOT NULL,
                PRIMARY KEY(plugin_id, project_id, category_id, id),
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS plugin_job_marks (
                plugin_id TEXT NOT NULL, job_id TEXT NOT NULL,
                PRIMARY KEY(plugin_id, job_id),
                FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS plugin_job_files (
                plugin_id TEXT NOT NULL, job_id TEXT NOT NULL, name TEXT NOT NULL,
                project_id TEXT NOT NULL, object_key TEXT NOT NULL,
                sha256 TEXT NOT NULL, size INTEGER NOT NULL, metadata_json TEXT NOT NULL,
                PRIMARY KEY(plugin_id, job_id, name),
                FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_plugin_job_files_object ON plugin_job_files(object_key);
            CREATE TABLE IF NOT EXISTS upload_metadata (
                id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL DEFAULT 'local',
                created_by TEXT NOT NULL DEFAULT 'local', created_at REAL NOT NULL
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
                key TEXT PRIMARY KEY, job_id TEXT NOT NULL, created_at REAL NOT NULL,
                fingerprint TEXT NOT NULL DEFAULT ''
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
            plugin_document_columns = {row['name'] for row in db.execute('PRAGMA table_info(plugin_documents)').fetchall()}
            if 'category_id' not in plugin_document_columns:
                db.executescript("""
                ALTER TABLE plugin_documents RENAME TO plugin_documents_legacy;
                CREATE TABLE plugin_documents (
                    plugin_id TEXT NOT NULL, id TEXT NOT NULL, project_id TEXT NOT NULL,
                    category_id TEXT NOT NULL DEFAULT '', document_json TEXT NOT NULL,
                    references_json TEXT NOT NULL DEFAULT '[]', active INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY(plugin_id, project_id, category_id, id),
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                );
                INSERT INTO plugin_documents
                    (plugin_id, id, project_id, category_id, document_json, references_json, active, updated_at)
                    SELECT plugin_id, id, project_id, '', document_json, references_json, active, updated_at
                    FROM plugin_documents_legacy;
                DROP TABLE plugin_documents_legacy;
                """)
            # One-way migration of the former built-in film store; no duplicate writer.
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='films'").fetchone():
                for row in db.execute('SELECT * FROM films').fetchall():
                    film = json.loads(row['document_json'])
                    references = [c['job_id'] for c in film.get('clips', [])]
                    if film.get('bgm_job_id'):
                        references.append(film['bgm_job_id'])
                    db.execute('INSERT OR IGNORE INTO plugin_documents (plugin_id, id, project_id, category_id, document_json, references_json, active, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                        ('film-studio', row['id'], row['project_id'], '', row['document_json'],
                         json.dumps(references), int(film.get('render', {}).get('status') in {'queued', 'running'}), row['updated_at']))
                db.execute('DROP TABLE films')
            if 'film_selected' in {row['name'] for row in db.execute('PRAGMA table_info(jobs)')}:
                db.execute("INSERT OR IGNORE INTO plugin_job_marks SELECT 'film-studio', id FROM jobs WHERE film_selected=1")
                db.execute('UPDATE jobs SET film_selected=0 WHERE film_selected=1')
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
            if 'fingerprint' not in {row['name'] for row in db.execute('PRAGMA table_info(api_idempotency)')}:
                db.execute("ALTER TABLE api_idempotency ADD COLUMN fingerprint TEXT NOT NULL DEFAULT ''")
            columns = {row["name"] for row in db.execute("PRAGMA table_info(voice_presets)").fetchall()}
            if "sample_audio_name" not in columns:
                db.execute("ALTER TABLE voice_presets ADD COLUMN sample_audio_name TEXT")
            if "sample_audio_url" not in columns:
                db.execute("ALTER TABLE voice_presets ADD COLUMN sample_audio_url TEXT")
            if "profile_version" not in columns:
                db.execute("ALTER TABLE voice_presets ADD COLUMN profile_version INTEGER DEFAULT 1")
            job_columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)").fetchall()}
            project_columns = {row["name"] for row in db.execute("PRAGMA table_info(projects)").fetchall()}
            for name in ("tenant_id", "created_by"):
                if name not in project_columns:
                    db.execute(f"ALTER TABLE projects ADD COLUMN {name} TEXT NOT NULL DEFAULT 'local'")
            if "ai_created" not in project_columns:
                db.execute("ALTER TABLE projects ADD COLUMN ai_created INTEGER NOT NULL DEFAULT 0")
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
                "category_id": "TEXT NOT NULL DEFAULT ''",
                "created_by": "TEXT NOT NULL DEFAULT 'local'",
                "execution_node_id": "TEXT NOT NULL DEFAULT ''",
            }.items():
                if name not in job_columns:
                    db.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
            # The implicit unassigned project was removed from the product.
            # Purge remnants during startup so it cannot reappear after upgrade.
            legacy_jobs = [row["id"] for row in db.execute(
                "SELECT id FROM jobs WHERE project_id='project-unassigned'"
            ).fetchall()]
            if legacy_jobs:
                placeholders = ",".join("?" for _ in legacy_jobs)
                db.execute(f"DELETE FROM artifacts WHERE job_id IN ({placeholders})", legacy_jobs)
                db.execute(f"DELETE FROM api_idempotency WHERE job_id IN ({placeholders})", legacy_jobs)
                db.execute(f"DELETE FROM plugin_job_marks WHERE job_id IN ({placeholders})", legacy_jobs)
                db.execute(f"DELETE FROM jobs WHERE id IN ({placeholders})", legacy_jobs)
            db.execute("DELETE FROM project_assets WHERE project_id='project-unassigned'")
            db.execute("DELETE FROM project_asset_types WHERE project_id='project-unassigned'")
            db.execute("DELETE FROM project_categories WHERE project_id='project-unassigned'")
            db.execute("DELETE FROM plugin_documents WHERE project_id='project-unassigned'")
            db.execute("DELETE FROM collaborations WHERE project_id='project-unassigned'")
            db.execute("DELETE FROM projects WHERE id='project-unassigned'")
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
            query = "SELECT jobs.*, (SELECT json_group_array(plugin_id) FROM plugin_job_marks WHERE job_id=jobs.id) AS application_marks_json FROM jobs"
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
            row = db.execute("SELECT jobs.*, (SELECT json_group_array(plugin_id) FROM plugin_job_marks WHERE job_id=jobs.id) AS application_marks_json FROM jobs WHERE id=?", (job_id,)).fetchone()
        return self._job(row) if row else None

    def insert_job(self, job: dict[str, Any]) -> None:
        with self.connect() as db:
            db.execute("""INSERT INTO jobs (id, kind, status, request_json, created_at, updated_at, width, height, duration_seconds, task_dir, manifest_path, parent_job_id, revision, project_id, category_id, created_by, execution_node_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
                job["id"], job["kind"], job["status"], json.dumps(job["request"], ensure_ascii=False),
                job["created_at"], job["created_at"], job.get("width"), job.get("height"), job.get("duration_seconds"),
                job.get("task_dir"), job.get("manifest_path"), job.get("parent_job_id"), job.get("revision", 1), job.get("project_id"),
                job.get("category_id", ""),
                job.get("created_by", "local"), job.get("execution_node_id", ""),
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

    def job_file(self, plugin_id: str, job_id: str, name: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM plugin_job_files WHERE plugin_id=? AND job_id=? AND name=?",
                             (plugin_id, job_id, name)).fetchone()
        if not row:
            return None
        value = dict(row)
        value["metadata"] = json.loads(value.pop("metadata_json"))
        return value

    def save_job_file(self, value: dict) -> None:
        with self.connect() as db:
            db.execute("""INSERT INTO plugin_job_files
                (plugin_id,job_id,name,project_id,object_key,sha256,size,metadata_json)
                VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(plugin_id,job_id,name) DO UPDATE SET
                object_key=excluded.object_key,sha256=excluded.sha256,size=excluded.size,
                metadata_json=excluded.metadata_json""", (
                value["plugin_id"], value["job_id"], value["name"], value["project_id"], value["object_key"],
                value["sha256"], value["size"], json.dumps(value.get("metadata", {}), ensure_ascii=False)))

    def job_files(self, job_id: str) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM plugin_job_files WHERE job_id=?", (job_id,))]

    def delete_job_files(self, job_id: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM plugin_job_files WHERE job_id=?", (job_id,))

    def job_file_referenced(self, key: str, excluding_job: str = "") -> bool:
        with self.connect() as db:
            return db.execute("SELECT 1 FROM plugin_job_files WHERE object_key=? AND job_id<>? LIMIT 1",
                              (key, excluding_job)).fetchone() is not None

    def register_upload(self, upload_id: str) -> None:
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO upload_metadata(id,created_at) VALUES (?,?)", (upload_id, time.time()))

    def upload_exists(self, upload_id: str) -> bool:
        with self.connect() as db:
            return db.execute("SELECT 1 FROM upload_metadata WHERE id=?", (upload_id,)).fetchone() is not None

    def delete_upload_metadata(self, upload_id: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM upload_metadata WHERE id=?", (upload_id,))

    def mark_plugin_job(self, plugin_id: str, job_id: str, selected: bool) -> None:
        with self.connect() as db:
            if selected:
                db.execute('INSERT OR IGNORE INTO plugin_job_marks VALUES (?, ?)', (plugin_id, job_id))
            else:
                db.execute('DELETE FROM plugin_job_marks WHERE plugin_id=? AND job_id=?', (plugin_id, job_id))

    def plugin_job_marks(self, plugin_id: str) -> set[str]:
        with self.connect() as db:
            return {row[0] for row in db.execute('SELECT job_id FROM plugin_job_marks WHERE plugin_id=?', (plugin_id,))}

    def plugin_documents(self, plugin_id: str, project_id: str, category_id: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as db:
            query = 'SELECT document_json FROM plugin_documents WHERE plugin_id=? AND project_id=?'
            params: list[Any] = [plugin_id, project_id]
            if category_id is not None:
                query += ' AND category_id=?'
                params.append(category_id)
            query += ' ORDER BY updated_at DESC'
            rows = db.execute(query, params).fetchall()
        return [json.loads(row[0]) for row in rows]

    def plugin_document(self, plugin_id: str, project_id: str, document_id: str, category_id: str | None = None) -> dict[str, Any] | None:
        with self.connect() as db:
            query = 'SELECT document_json FROM plugin_documents WHERE plugin_id=? AND project_id=? AND id=?'
            params: list[Any] = [plugin_id, project_id, document_id]
            if category_id is not None:
                query += ' AND category_id=?'
                params.append(category_id)
            row = db.execute(query, params).fetchone()
        return json.loads(row[0]) if row else None

    def save_plugin_document(self, plugin_id: str, document: dict[str, Any], references: list[str],
                             active: bool = False, selected_job_id: str | None = None) -> None:
        with self.connect() as db:
            if selected_job_id:
                if not db.execute('SELECT 1 FROM jobs WHERE id=? AND project_id=?', (selected_job_id, document['project_id'])).fetchone():
                    raise ValueError('素材不属于当前项目')
                db.execute('INSERT OR IGNORE INTO plugin_job_marks VALUES (?, ?)', (plugin_id, selected_job_id))
            category_id = document.get('category_id') or ''
            db.execute('INSERT INTO plugin_documents (plugin_id, id, project_id, category_id, document_json, references_json, active, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) '
                       'ON CONFLICT(plugin_id, project_id, category_id, id) DO UPDATE SET document_json=excluded.document_json, '
                       'references_json=excluded.references_json, active=excluded.active, updated_at=excluded.updated_at',
                       (plugin_id, document['id'], document['project_id'], category_id, json.dumps(document, ensure_ascii=False),
                        json.dumps(references), int(active), time.time()))

    def delete_plugin_document(self, plugin_id: str, project_id: str, document_id: str, category_id: str | None = None) -> None:
        with self.connect() as db:
            query = 'DELETE FROM plugin_documents WHERE plugin_id=? AND project_id=? AND id=?'
            params: list[Any] = [plugin_id, project_id, document_id]
            if category_id is not None:
                query += ' AND category_id=?'
                params.append(category_id)
            db.execute(query, params)

    def check_plugin_references(self, project_id: str, job_ids: set[str] | None = None) -> None:
        with self.connect() as db:
            rows = db.execute('SELECT references_json FROM plugin_documents WHERE project_id=? AND active=1', (project_id,)).fetchall()
        if any(job_ids is None or set(json.loads(row[0])) & job_ids for row in rows):
            raise RuntimeError('项目或素材正在被应用任务使用，请等待任务完成')

    def reset_application_activity(self) -> None:
        """Process-local tasks cannot survive restart, including disabled plugins."""
        with self.connect() as db:
            db.execute('UPDATE plugin_documents SET active=0 WHERE active=1')

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
        query += " GROUP BY p.id ORDER BY p.updated_at DESC"
        with self.connect() as db:
            return [dict(row) for row in db.execute(query).fetchall()]

    def project(self, project_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        return dict(row) if row else None

    def project_assets(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM project_assets WHERE project_id=? ORDER BY rowid DESC", (project_id,)).fetchall()
        result = []
        for row in rows:
            asset = dict(row)
            asset["media"] = json.loads(asset.pop("media_json"))
            result.append(asset)
        return result

    def save_project_asset(self, asset: dict[str, Any]) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO project_assets (id, project_id, name, kind, description, media_json) VALUES (?, ?, ?, ?, ?, ?) "
                       "ON CONFLICT(id) DO UPDATE SET name=excluded.name, kind=excluded.kind, description=excluded.description, media_json=excluded.media_json",
                       (asset["id"], asset["project_id"], asset["name"], asset["kind"], asset["description"], json.dumps(asset["media"], ensure_ascii=False)))

    def delete_project_asset(self, project_id: str, asset_id: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM project_assets WHERE project_id=? AND id=?", (project_id, asset_id))

    def project_asset_types(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT id, project_id, name, description FROM project_asset_types WHERE project_id=? ORDER BY rowid", (project_id,))]

    def save_project_asset_type(self, value: dict[str, Any], create: bool = False) -> None:
        now = time.time()
        with self.connect() as db:
            if create:
                db.execute("INSERT INTO project_asset_types (id, project_id, name, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)", (value["id"], value["project_id"], value["name"], value.get("description", ""), now, now))
            else:
                db.execute("UPDATE project_asset_types SET name=?, description=?, updated_at=? WHERE id=? AND project_id=?", (value["name"], value.get("description", ""), now, value["id"], value["project_id"]))

    def project_categories(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM project_categories WHERE project_id=? ORDER BY rowid", (project_id,))]

    def save_category(self, project_id: str, category_id: str, name: str, create: bool = False) -> None:
        with self.connect() as db:
            if create:
                db.execute("INSERT INTO project_categories (id, project_id, name) VALUES (?, ?, ?)", (category_id, project_id, name))
            else:
                db.execute("UPDATE project_categories SET name=? WHERE id=? AND project_id=?", (name, category_id, project_id))

    def delete_category(self, project_id: str, category_id: str) -> None:
        with self.connect() as db:
            db.execute("UPDATE jobs SET category_id='' WHERE project_id=? AND category_id=?", (project_id, category_id))
            db.execute("DELETE FROM plugin_documents WHERE project_id=? AND category_id=?", (project_id, category_id))
            db.execute("DELETE FROM project_categories WHERE project_id=? AND id=?", (project_id, category_id))

    def create_project(self, value: dict[str, Any]) -> dict[str, Any]:
        now = time.time()
        with self.connect() as db:
            db.execute(
                "INSERT INTO projects (id, name, output_subdir, description, content_summary, status, ai_created, created_at, updated_at, tenant_id, created_by) VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)",
                (value["id"], value["name"], value["output_subdir"], value.get("description", ""), value.get("content_summary", ""), int(bool(value.get("ai_created", False))), now, now, value.get("tenant_id", "local"), value.get("created_by", "local")),
            )
        return self.project(value["id"]) or value

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
            db.execute("DELETE FROM settings WHERE key='current_project_id' AND value=?", (project_id,))
            db.execute("DELETE FROM api_idempotency WHERE job_id IN (SELECT id FROM jobs WHERE project_id=?)", (project_id,))
            db.execute("DELETE FROM artifacts WHERE job_id IN (SELECT id FROM jobs WHERE project_id=?)", (project_id,))
            db.execute("DELETE FROM jobs WHERE project_id=?", (project_id,))
            db.execute("DELETE FROM projects WHERE id=?", (project_id,))

    def current_project(self) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT p.* FROM projects p JOIN settings s ON s.key='current_project_id' AND s.value=p.id",
            ).fetchone()
        return dict(row) if row else None

    def set_current_project(self, project_id: str) -> dict[str, Any] | None:
        now = time.time()
        with self.connect() as db:
            db.execute("INSERT INTO settings(key,value,updated_at) VALUES ('current_project_id',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at", (project_id, now))
        return self.current_project()

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

    def delete_voice_preset(self, preset_key: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM voice_presets WHERE preset_key=?", (preset_key,))

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

    def idempotent_job(self, key: str, fingerprint: str | None = None) -> str | None:
        with self.connect() as db:
            row = db.execute("SELECT job_id, fingerprint FROM api_idempotency WHERE key=?", (key,)).fetchone()
        if row and fingerprint is not None and row['fingerprint'] != fingerprint:
            raise ValueError("同一 Idempotency-Key 不能用于不同的生成请求")
        return row["job_id"] if row else None

    def save_idempotent_job(self, key: str, job_id: str, fingerprint: str = '') -> None:
        with self.connect() as db:
            db.execute("""INSERT INTO api_idempotency (key, job_id, created_at, fingerprint) VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET job_id=excluded.job_id, created_at=excluded.created_at,
                    fingerprint=excluded.fingerprint""", (key, job_id, time.time(), fingerprint))

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

    def collaborations(self, statuses: tuple[str, ...] | None = None, limit: int | None = 50, *, project_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM collaborations"
        values: list[Any] = []
        conditions = []
        if statuses:
            conditions.append(f"status IN ({','.join('?' for _ in statuses)})")
            values.extend(statuses)
        if project_id is not None:
            conditions.append("project_id = ?")
            values.append(project_id)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY updated_at DESC"
        if limit is not None:
            query += " LIMIT ?"
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

    def delete_settings(self, keys: list[str]) -> None:
        if not keys:
            return
        with self.connect() as db:
            db.executemany("DELETE FROM settings WHERE key = ?", ((key,) for key in keys))

    @staticmethod
    def _job(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item.pop('film_selected', None)
        item['application_marks'] = json.loads(item.pop('application_marks_json', '[]'))
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
