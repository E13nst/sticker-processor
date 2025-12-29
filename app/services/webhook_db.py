"""Service for managing webhook data in SQLite database."""
import json
import logging
from datetime import datetime
from typing import List, Optional
from pathlib import Path
import aiosqlite

from app.config import settings
from app.models.webhook import WebhookRecord

logger = logging.getLogger(__name__)


class WebhookDBService:
    """Service for managing webhook records in SQLite database."""
    
    def __init__(self):
        # Use a separate database for webhook data
        db_dir = Path(settings.disk_cache_dir).parent / "webhook_db"
        db_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = db_dir / "webhooks.db"
        self._db = None
        logger.info(f"Webhook DB service initialized: {self._db_path}")
    
    async def connect(self):
        """Connect to SQLite database and initialize tables."""
        try:
            self._db = await aiosqlite.connect(str(self._db_path))
            
            # Create table for webhook records
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS webhook_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    status TEXT NOT NULL,
                    chat_id TEXT NOT NULL,
                    style_id TEXT NOT NULL,
                    style_hash TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    original_message_id TEXT NOT NULL,
                    processing_job_id TEXT NOT NULL,
                    img_url TEXT,
                    sticker_url TEXT,
                    error_data TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes for faster queries
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_processing_job_id 
                ON webhook_records(processing_job_id)
            """)
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_job_id 
                ON webhook_records(job_id)
            """)
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_created_at 
                ON webhook_records(created_at)
            """)
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_status 
                ON webhook_records(status)
            """)
            
            await self._db.commit()
            logger.info("Webhook database initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing webhook database: {e}")
            raise
    
    async def disconnect(self):
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("Webhook database connection closed")
    
    async def save_webhook(self, webhook_data: dict) -> int:
        """Save webhook data to database. Returns record ID."""
        try:
            error_data_str = None
            if webhook_data.get("error_data"):
                error_data_str = json.dumps(webhook_data["error_data"])
            
            cursor = await self._db.execute("""
                INSERT INTO webhook_records (
                    status, chat_id, style_id, style_hash, job_id,
                    original_message_id, processing_job_id, img_url,
                    sticker_url, error_data, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                webhook_data["status"],
                webhook_data["chat_id"],
                webhook_data["style_id"],
                webhook_data["style_hash"],
                webhook_data["job_id"],
                webhook_data["original_message_id"],
                webhook_data["processing_job_id"],
                webhook_data.get("img_url"),
                webhook_data.get("sticker_url"),
                error_data_str,
                datetime.now().isoformat()
            ))
            
            await self._db.commit()
            record_id = cursor.lastrowid
            logger.info(f"Webhook record saved with ID: {record_id}")
            return record_id
        except Exception as e:
            logger.error(f"Error saving webhook record: {e}")
            raise
    
    async def get_all_records(self, limit: int = 100, offset: int = 0) -> List[WebhookRecord]:
        """Get all webhook records, ordered by created_at DESC."""
        try:
            cursor = await self._db.execute("""
                SELECT id, status, chat_id, style_id, style_hash, job_id,
                       original_message_id, processing_job_id, img_url,
                       sticker_url, error_data, created_at
                FROM webhook_records
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))
            
            rows = await cursor.fetchall()
            records = []
            
            for row in rows:
                error_data = None
                if row[10]:  # error_data
                    try:
                        error_data = json.loads(row[10])
                    except:
                        error_data = row[10]
                
                record = WebhookRecord(
                    id=row[0],
                    status=row[1],
                    chat_id=row[2],
                    style_id=row[3],
                    style_hash=row[4],
                    job_id=row[5],
                    original_message_id=row[6],
                    processing_job_id=row[7],
                    img_url=row[8],
                    sticker_url=row[9],
                    error_data=error_data,
                    created_at=datetime.fromisoformat(row[11]) if row[11] else None
                )
                records.append(record)
            
            return records
        except Exception as e:
            logger.error(f"Error fetching webhook records: {e}")
            raise
    
    async def get_record_by_job_id(self, job_id: str) -> Optional[WebhookRecord]:
        """Get webhook record by job_id."""
        try:
            cursor = await self._db.execute("""
                SELECT id, status, chat_id, style_id, style_hash, job_id,
                       original_message_id, processing_job_id, img_url,
                       sticker_url, error_data, created_at
                FROM webhook_records
                WHERE job_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            """, (job_id,))
            
            row = await cursor.fetchone()
            if not row:
                return None
            
            error_data = None
            if row[10]:  # error_data
                try:
                    error_data = json.loads(row[10])
                except:
                    error_data = row[10]
            
            return WebhookRecord(
                id=row[0],
                status=row[1],
                chat_id=row[2],
                style_id=row[3],
                style_hash=row[4],
                job_id=row[5],
                original_message_id=row[6],
                processing_job_id=row[7],
                img_url=row[8],
                sticker_url=row[9],
                error_data=error_data,
                created_at=datetime.fromisoformat(row[11]) if row[11] else None
            )
        except Exception as e:
            logger.error(f"Error fetching webhook record by job_id: {e}")
            raise
    
    async def get_count(self) -> int:
        """Get total count of webhook records."""
        try:
            cursor = await self._db.execute("SELECT COUNT(*) FROM webhook_records")
            row = await cursor.fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"Error getting webhook count: {e}")
            return 0

