import os
import hashlib
import shutil
import asyncio
import logging
from collections import defaultdict
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
import aiofiles
import aiosqlite

from app.config import settings

logger = logging.getLogger(__name__)


class DiskCacheService:
    """Service for managing disk-based file cache with TTL and cleanup."""
    
    def __init__(self):
        self.cache_dir = Path(settings.disk_cache_dir)
        self.max_cache_size_mb = settings.disk_cache_max_size_mb
        self.ttl_days = settings.disk_cache_ttl_days
        self.cleanup_interval_hours = settings.disk_cache_cleanup_interval_hours
        
        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # SQLite database connection
        self._metadata_db = None
        self._db_path = None
        
        # Statistics
        self.stats = {
            'total_files': 0,
            'total_size_bytes': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'files_created': 0,
            'files_deleted': 0,
            'cleanup_runs': 0,
            'last_cleanup': None,
        }
        
        logger.info(f"Disk cache initialized: {self.cache_dir}")
        logger.info(f"Max cache size: {self.max_cache_size_mb} MB")
        logger.info(f"TTL: {self.ttl_days} days")
    
    def _get_file_hash(self, file_id: str) -> str:
        """Generate a hash for the file ID to use as filename."""
        return hashlib.md5(file_id.encode()).hexdigest()
    
    def _get_metadata_db_path(self) -> Path:
        """Determine path to SQLite database.
        
        Priority:
        1. /data/sticker_cache_metadata.db (production - persistent storage)
        2. {disk_cache_dir}/sticker_cache_metadata.db (local/dev - fallback)
        """
        # Check if /data directory exists and is writable (production)
        data_dir = Path("/data")
        if data_dir.exists() and os.access(data_dir, os.W_OK):
            data_dir.mkdir(parents=True, exist_ok=True)
            return data_dir / "sticker_cache_metadata.db"
        
        # Fallback to disk_cache_dir (local development)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        return self.cache_dir / "sticker_cache_metadata.db"
    
    def _get_cache_path(self, file_id: str, file_format: str) -> Path:
        """Get the cache file path with hierarchical structure.
        
        Uses 2-level hierarchy: format/hash[0:2]/hash[2:4]/filename
        This distributes 50k files across ~256 directories for better FS performance.
        """
        file_hash = self._get_file_hash(file_id)
        # Create hierarchical structure: format/hash[0:2]/hash[2:4]/filename
        format_dir = self.cache_dir / file_format
        subdir1 = format_dir / file_hash[:2]
        subdir2 = subdir1 / file_hash[2:4]
        return subdir2 / f"{file_hash}.{file_format}"
    
    async def _ensure_db_connection(self):
        """Ensure database connection is active."""
        if self._metadata_db is None:
            await self._init_metadata_db()
        # Reconnect if connection lost
        try:
            await self._metadata_db.execute("SELECT 1")
        except Exception:
            await self._init_metadata_db()
    
    async def _init_metadata_db(self):
        """Initialize SQLite database for metadata."""
        try:
            self._db_path = self._get_metadata_db_path()
            self._metadata_db = await aiosqlite.connect(str(self._db_path))
            
            # Create table for cache metadata
            await self._metadata_db.execute("""
                CREATE TABLE IF NOT EXISTS cache_metadata (
                    file_id TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    file_format TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    original_size INTEGER,
                    converted INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    PRIMARY KEY (file_id, file_format)
                )
            """)
            
            # Create indexes for fast queries
            await self._metadata_db.execute("""
                CREATE INDEX IF NOT EXISTS idx_expires_at ON cache_metadata(expires_at)
            """)
            await self._metadata_db.execute("""
                CREATE INDEX IF NOT EXISTS idx_created_at ON cache_metadata(created_at)
            """)
            await self._metadata_db.execute("""
                CREATE INDEX IF NOT EXISTS idx_file_hash ON cache_metadata(file_hash)
            """)
            
            await self._metadata_db.commit()
            logger.info(f"SQLite metadata database initialized: {self._db_path}")
        except Exception as e:
            logger.error(f"Error initializing metadata database: {e}")
            raise
    
    async def close_db(self):
        """Close database connection."""
        if self._metadata_db:
            await self._metadata_db.close()
            self._metadata_db = None
            logger.info("SQLite metadata database connection closed")
    
    async def store_file(self, file_id: str, content: bytes, file_format: str, 
                        original_size: int = None, converted: bool = False) -> bool:
        """Store file content in disk cache."""
        try:
            await self._ensure_db_connection()
            
            cache_path = self._get_cache_path(file_id, file_format)
            
            # Ensure directory exists
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if file already exists
            if cache_path.exists():
                logger.debug(f"File {file_id} already exists in disk cache")
                return True
            
            # Write file content
            async with aiofiles.open(cache_path, 'wb') as f:
                await f.write(content)
            
            # Store metadata in database
            file_hash = self._get_file_hash(file_id)
            created_at = datetime.now().isoformat()
            expires_at = (datetime.now() + timedelta(days=self.ttl_days)).isoformat()
            
            await self._metadata_db.execute("""
                INSERT OR REPLACE INTO cache_metadata 
                (file_id, file_hash, file_format, size, original_size, converted, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                file_id,
                file_hash,
                file_format,
                len(content),
                original_size or len(content),
                1 if converted else 0,
                created_at,
                expires_at
            ))
            await self._metadata_db.commit()
            
            # Update statistics
            self.stats['total_files'] += 1
            self.stats['total_size_bytes'] += len(content)
            self.stats['files_created'] += 1
            
            logger.debug(f"Stored file {file_id} in disk cache: {len(content)} bytes")
            return True
            
        except Exception as e:
            logger.error(f"Error storing file {file_id} in disk cache: {e}")
            return False
    
    async def get_file(self, file_id: str, file_format: str) -> Optional[bytes]:
        """Retrieve file content from disk cache."""
        try:
            await self._ensure_db_connection()
            
            cache_path = self._get_cache_path(file_id, file_format)
            
            if not cache_path.exists():
                self.stats['cache_misses'] += 1
                return None
            
            # Check metadata for expiration from database
            async with self._metadata_db.execute("""
                SELECT expires_at FROM cache_metadata 
                WHERE file_id = ? AND file_format = ?
            """, (file_id, file_format)) as cursor:
                row = await cursor.fetchone()
                
            if row:
                expires_at_str = row[0]
                expires_at = datetime.fromisoformat(expires_at_str)
                if datetime.now() > expires_at:
                    # File expired, remove it
                    await self.delete_file(file_id, file_format)
                    self.stats['cache_misses'] += 1
                    return None
            else:
                # No metadata in DB, file might be orphaned, check file age
                file_stat = cache_path.stat()
                file_age = datetime.now() - datetime.fromtimestamp(file_stat.st_mtime)
                if file_age > timedelta(days=self.ttl_days):
                    await self.delete_file(file_id, file_format)
                    self.stats['cache_misses'] += 1
                    return None
            
            # Read file content
            async with aiofiles.open(cache_path, 'rb') as f:
                content = await f.read()
            
            self.stats['cache_hits'] += 1
            logger.debug(f"Retrieved file {file_id} from disk cache: {len(content)} bytes")
            return content
            
        except Exception as e:
            logger.error(f"Error retrieving file {file_id} from disk cache: {e}")
            self.stats['cache_misses'] += 1
            return None
    
    async def delete_file(self, file_id: str, file_format: str) -> bool:
        """Delete file from disk cache."""
        try:
            await self._ensure_db_connection()
            
            cache_path = self._get_cache_path(file_id, file_format)
            
            # Get file size before deletion
            file_size = 0
            if cache_path.exists():
                file_size = cache_path.stat().st_size
                cache_path.unlink()
            
            # Remove metadata from database
            await self._metadata_db.execute("""
                DELETE FROM cache_metadata 
                WHERE file_id = ? AND file_format = ?
            """, (file_id, file_format))
            await self._metadata_db.commit()
            
            # Update statistics
            if file_size > 0:
                self.stats['total_files'] = max(0, self.stats['total_files'] - 1)
                self.stats['total_size_bytes'] = max(0, self.stats['total_size_bytes'] - file_size)
                self.stats['files_deleted'] += 1
            
            logger.debug(f"Deleted file {file_id} from disk cache")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting file {file_id} from disk cache: {e}")
            return False
    
    async def cleanup_expired_files(self, batch_size: int = 1000) -> int:
        """Remove expired files from disk cache using database index."""
        try:
            await self._ensure_db_connection()
            
            removed_count = 0
            current_time = datetime.now().isoformat()
            
            # Query expired files in batches
            while True:
                async with self._metadata_db.execute("""
                    SELECT file_id, file_format FROM cache_metadata 
                    WHERE expires_at < ? 
                    LIMIT ?
                """, (current_time, batch_size)) as cursor:
                    expired_files = await cursor.fetchall()
                
                if not expired_files:
                    break
                
                # Delete files in parallel batches
                tasks = []
                for file_id, file_format in expired_files:
                    tasks.append(self.delete_file(file_id, file_format))
                
                if tasks:
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    batch_removed = sum(1 for r in results if r is True)
                    removed_count += batch_removed
            
            self.stats['cleanup_runs'] += 1
            self.stats['last_cleanup'] = current_time
            
            if removed_count > 0:
                logger.info(f"Cleaned up {removed_count} expired files from disk cache")
            
            return removed_count
            
        except Exception as e:
            logger.error(f"Error during disk cache cleanup: {e}")
            return 0
    
    async def cleanup_oldest_files(self, target_size_mb: int, max_workers: int = 10) -> int:
        """Remove oldest files to reduce cache size to target using database."""
        try:
            await self._ensure_db_connection()
            
            target_size_bytes = target_size_mb * 1024 * 1024
            
            # Get current total size from database
            async with self._metadata_db.execute("""
                SELECT SUM(size) FROM cache_metadata
            """) as cursor:
                row = await cursor.fetchone()
                current_size = row[0] if row and row[0] else 0
            
            if current_size <= target_size_bytes:
                return 0
            
            # Get files sorted by creation time (oldest first) with their sizes
            async with self._metadata_db.execute("""
                SELECT file_id, file_format, size, created_at 
                FROM cache_metadata 
                ORDER BY created_at ASC
            """) as cursor:
                files_to_delete = []
                total_to_delete = current_size - target_size_bytes
                accumulated_size = 0
                
                async for row in cursor:
                    file_id, file_format, file_size, created_at = row
                    files_to_delete.append((file_id, file_format))
                    accumulated_size += file_size
                    if accumulated_size >= total_to_delete:
                        break
            
            if not files_to_delete:
                return 0
            
            # Process deletions in parallel batches with semaphore
            semaphore = asyncio.Semaphore(max_workers)
            
            async def delete_with_limit(file_id, file_format):
                async with semaphore:
                    return await self.delete_file(file_id, file_format)
            
            tasks = [delete_with_limit(fid, fmt) for fid, fmt in files_to_delete]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            removed_count = sum(1 for r in results if r is True)
            
            if removed_count > 0:
                logger.info(f"Removed {removed_count} oldest files to reduce cache size")
            
            return removed_count
            
        except Exception as e:
            logger.error(f"Error during disk cache size cleanup: {e}")
            return 0
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get disk cache statistics from database."""
        try:
            await self._ensure_db_connection()
            
            # Fast query from database using SQL aggregations
            async with self._metadata_db.execute("""
                SELECT 
                    COUNT(*) as total_files,
                    COALESCE(SUM(size), 0) as total_size_bytes,
                    file_format,
                    COUNT(*) as format_count
                FROM cache_metadata
                GROUP BY file_format
            """) as cursor:
                rows = await cursor.fetchall()
            
            total_files = 0
            total_size_bytes = 0
            file_types = {}
            
            for row in rows:
                count, size, file_format, format_count = row
                total_files += count
                total_size_bytes += size or 0
                file_types[file_format] = format_count
            
            # Update in-memory stats
            self.stats['total_files'] = total_files
            self.stats['total_size_bytes'] = total_size_bytes
            
            # Calculate additional stats
            cache_hit_rate = 0
            if self.stats['cache_hits'] + self.stats['cache_misses'] > 0:
                cache_hit_rate = (self.stats['cache_hits'] / (self.stats['cache_hits'] + self.stats['cache_misses'])) * 100
            
            return {
                'total_files': total_files,
                'total_size_bytes': total_size_bytes,
                'total_size_mb': round(total_size_bytes / (1024 * 1024), 2),
                'cache_hits': self.stats['cache_hits'],
                'cache_misses': self.stats['cache_misses'],
                'cache_hit_rate': round(cache_hit_rate, 1),
                'files_created': self.stats['files_created'],
                'files_deleted': self.stats['files_deleted'],
                'cleanup_runs': self.stats['cleanup_runs'],
                'last_cleanup': self.stats['last_cleanup'],
                'max_size_mb': self.max_cache_size_mb,
                'ttl_days': self.ttl_days,
                'file_types': file_types,
            }
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            # Return fallback stats
            return {
                'total_files': self.stats['total_files'],
                'total_size_bytes': self.stats['total_size_bytes'],
                'total_size_mb': round(self.stats['total_size_bytes'] / (1024 * 1024), 2),
                'cache_hits': self.stats['cache_hits'],
                'cache_misses': self.stats['cache_misses'],
                'cache_hit_rate': 0,
                'files_created': self.stats['files_created'],
                'files_deleted': self.stats['files_deleted'],
                'cleanup_runs': self.stats['cleanup_runs'],
                'last_cleanup': self.stats['last_cleanup'],
                'max_size_mb': self.max_cache_size_mb,
                'ttl_days': self.ttl_days,
                'file_types': {},
            }
    
    async def clear_cache(self) -> int:
        """Clear all files from disk cache."""
        try:
            await self._ensure_db_connection()
            
            # Get all files from database
            async with self._metadata_db.execute("""
                SELECT file_id, file_format FROM cache_metadata
            """) as cursor:
                all_files = await cursor.fetchall()
            
            removed_count = 0
            
            # Delete all files
            for file_id, file_format in all_files:
                if await self.delete_file(file_id, file_format):
                    removed_count += 1
            
            # Clear database
            await self._metadata_db.execute("DELETE FROM cache_metadata")
            await self._metadata_db.commit()
            
            # Reset statistics
            self.stats = {
                'total_files': 0,
                'total_size_bytes': 0,
                'cache_hits': 0,
                'cache_misses': 0,
                'files_created': 0,
                'files_deleted': 0,
                'cleanup_runs': 0,
                'last_cleanup': None,
            }
            
            logger.info(f"Cleared disk cache: removed {removed_count} files")
            return removed_count
            
        except Exception as e:
            logger.error(f"Error clearing disk cache: {e}")
            return 0
