"""Registry service for WaveSpeed generation jobs."""
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

import aiosqlite

from app.config import settings


class WaveSpeedRegistryService:
    """Stores and updates WaveSpeed generation metadata."""

    def __init__(self):
        db_dir = Path(settings.disk_cache_dir).parent / "wavespeed_db"
        db_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = db_dir / "wavespeed_jobs.db"
        self._db: Optional[aiosqlite.Connection] = None

    async def _ensure_db(self):
        if self._db is None:
            await self.connect()
        try:
            await self._db.execute("SELECT 1")
        except Exception:
            await self.connect()

    async def connect(self):
        self._db = await aiosqlite.connect(str(self._db_path))
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS wavespeed_jobs (
                file_id TEXT PRIMARY KEY,
                provider_request_id TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt TEXT NOT NULL,
                remove_background INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                source_url TEXT,
                error_payload TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """
        )
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_wavespeed_jobs_status ON wavespeed_jobs(status)"
        )
        await self._db.commit()

    async def disconnect(self):
        if self._db:
            await self._db.close()
            self._db = None

    async def create_job(
        self,
        *,
        file_id: str,
        provider_request_id: str,
        model: str,
        prompt: str,
        remove_background: bool,
    ) -> None:
        await self._ensure_db()
        now = datetime.utcnow()
        expires_at = now + timedelta(hours=settings.wavespeed_registry_ttl_hours)
        await self._db.execute(
            """
            INSERT OR REPLACE INTO wavespeed_jobs (
                file_id, provider_request_id, model, prompt, remove_background,
                status, source_url, error_payload, created_at, updated_at, expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                file_id,
                provider_request_id,
                model,
                prompt,
                1 if remove_background else 0,
                "pending",
                None,
                None,
                now.isoformat(),
                now.isoformat(),
                expires_at.isoformat(),
            ),
        )
        await self._db.commit()

    async def get_job(self, file_id: str) -> Optional[Dict[str, Any]]:
        await self._ensure_db()
        async with self._db.execute(
            """
            SELECT file_id, provider_request_id, model, prompt, remove_background,
                   status, source_url, error_payload, created_at, updated_at, expires_at
            FROM wavespeed_jobs
            WHERE file_id = ?
            """,
            (file_id,),
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return None

        error_payload = json.loads(row[7]) if row[7] else None
        return {
            "file_id": row[0],
            "provider_request_id": row[1],
            "model": row[2],
            "prompt": row[3],
            "remove_background": bool(row[4]),
            "status": row[5],
            "source_url": row[6],
            "error_payload": error_payload,
            "created_at": row[8],
            "updated_at": row[9],
            "expires_at": row[10],
        }

    async def set_pending(self, file_id: str):
        await self._update_job(file_id=file_id, status="pending")

    async def set_completed(self, file_id: str, source_url: str):
        await self._update_job(file_id=file_id, status="completed", source_url=source_url, error_payload=None)

    async def set_failed(self, file_id: str, error_payload: Dict[str, Any]):
        await self._update_job(file_id=file_id, status="failed", error_payload=error_payload)

    async def set_ready(self, file_id: str, source_url: Optional[str] = None):
        await self._update_job(file_id=file_id, status="ready", source_url=source_url)

    async def _update_job(
        self,
        *,
        file_id: str,
        status: str,
        source_url: Optional[str] = None,
        error_payload: Optional[Dict[str, Any]] = None,
    ):
        await self._ensure_db()
        now = datetime.utcnow().isoformat()
        await self._db.execute(
            """
            UPDATE wavespeed_jobs
            SET status = ?,
                source_url = COALESCE(?, source_url),
                error_payload = ?,
                updated_at = ?
            WHERE file_id = ?
            """,
            (
                status,
                source_url,
                json.dumps(error_payload) if error_payload is not None else None,
                now,
                file_id,
            ),
        )
        await self._db.commit()
