import os
import asyncio
import aiofiles
import json
import time
import shutil
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from pathlib import Path
from app.config import settings

logger = logging.getLogger(__name__)

class DiskCacheService:
    """Enhanced disk cache service with format-specific directories."""
    
    def __init__(self):
        self.cache_dir = Path(settings.disk_cache_dir)
        self.max_cache_size_mb = settings.disk_cache_max_size_mb
        self.ttl_days = settings.disk_cache_ttl_days
        self.cleanup_interval_hours = settings.disk_cache_cleanup_interval_hours
        self.enabled = settings.disk_cache_enabled
        
        self.stats = {
            'cache_hits': 0,
            'cache_misses': 0,
            'files_created': 0,
            'files_deleted': 0,
            'cleanup_runs': 0,
            'last_cleanup': None,
        }
        
        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            # Create format-specific directories
            self._create_format_directories()
            logger.info(f"Enhanced disk cache initialized: {self.cache_dir}")
            logger.info(f"Max cache size: {self.max_cache_size_mb} MB")
            logger.info(f"TTL: {self.ttl_days} days")
            logger.info("Format-specific directories created")
        else:
            logger.info("Disk cache is DISABLED")
    
    def _create_format_directories(self):
        """Create directories for each supported format."""
        formats = ['tgs', 'lottie', 'webp', 'webm', 'png', 'jpg']
        for format_name in formats:
            format_dir = self.cache_dir / format_name
            format_dir.mkdir(exist_ok=True)
            logger.debug(f"Created directory: {format_dir}")
    
    def _get_file_hash(self, file_id: str) -> str:
        """Generate a hash for the file ID to use as filename."""
        return hashlib.md5(file_id.encode()).hexdigest()
    
    def _get_file_path(self, file_id: str, output_format: str) -> Path:
        """Get file path with format-specific directory structure."""
        file_hash = self._get_file_hash(file_id)
        format_dir = self.cache_dir / output_format
        return format_dir / f"{file_hash}.{output_format}"
    
    def _get_metadata_path(self, file_id: str, output_format: str) -> Path:
        """Get metadata path with format-specific directory structure."""
        file_hash = self._get_file_hash(file_id)
        format_dir = self.cache_dir / output_format
        return format_dir / f"{file_hash}.{output_format}.meta"
    
    async def get_file(self, file_id: str, output_format: str) -> Optional[bytes]:
        """Get file from disk cache with format-specific lookup."""
        if not self.enabled:
            return None
        
        file_path = self._get_file_path(file_id, output_format)
        meta_path = self._get_metadata_path(file_id, output_format)
        
        if not file_path.exists() or not meta_path.exists():
            self.stats['cache_misses'] += 1
            logger.debug(f"Disk cache miss: {file_id}.{output_format}")
            return None
        
        try:
            async with aiofiles.open(meta_path, 'r') as f:
                meta = json.loads(await f.read())
            
            expires_at_str = meta.get('expires_at', '')
            if expires_at_str:
                expires_at = datetime.fromisoformat(expires_at_str)
            else:
                expires_at = datetime.now() + timedelta(days=self.ttl_days)
            
            if datetime.now() > expires_at:
                logger.info(f"Disk cache: {file_id}.{output_format} expired. Deleting.")
                await self.delete_file(file_id, output_format)
                self.stats['cache_misses'] += 1
                return None
            
            async with aiofiles.open(file_path, 'rb') as f:
                content = await f.read()
            
            self.stats['cache_hits'] += 1
            logger.debug(f"Disk cache hit: {file_id}.{output_format}")
            return content
        except Exception as e:
            logger.error(f"Error reading from disk cache for {file_id}.{output_format}: {e}")
            self.stats['cache_misses'] += 1
            return None
    
    async def set_file(self, file_id: str, output_format: str, content: bytes, mime_type: str) -> bool:
        """Store file in disk cache with format-specific directory."""
        if not self.enabled:
            return False
        
        file_path = self._get_file_path(file_id, output_format)
        meta_path = self._get_metadata_path(file_id, output_format)
        
        try:
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(content)
            
            expires_at = datetime.now() + timedelta(days=self.ttl_days)
            meta = {
                'file_id': file_id,
                'output_format': output_format,
                'mime_type': mime_type,
                'file_size': len(content),
                'created_at': datetime.now().isoformat(),
                'expires_at': expires_at.isoformat(),
                'last_accessed': datetime.now().isoformat()
            }
            async with aiofiles.open(meta_path, 'w') as f:
                await f.write(json.dumps(meta))
            
            self.stats['files_created'] += 1
            logger.debug(f"Stored in disk cache: {file_id}.{output_format} ({len(content)} bytes)")
            return True
        except Exception as e:
            logger.error(f"Error writing to disk cache for {file_id}.{output_format}: {e}")
            return False
    
    async def delete_file(self, file_id: str, output_format: str) -> bool:
        """Delete file from disk cache."""
        if not self.enabled:
            return False
        
        file_path = self._get_file_path(file_id, output_format)
        meta_path = self._get_metadata_path(file_id, output_format)
        
        deleted_count = 0
        for path in [file_path, meta_path]:
            if path.exists():
                try:
                    path.unlink()
                    deleted_count += 1
                except OSError as e:
                    logger.error(f"Error deleting file {path} from disk cache: {e}")
        
        if deleted_count > 0:
            self.stats['files_deleted'] += 1
            logger.debug(f"Deleted from disk cache: {file_id}.{output_format}")
            return True
        return False
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics with format breakdown."""
        if not self.enabled:
            return {
                'enabled': False,
                'total_files': 0,
                'total_size_bytes': 0,
                'total_size_mb': 0,
                'formats': {}
            }
        
        total_files = 0
        total_size_bytes = 0
        format_stats = {}
        
        # Scan all format directories
        for format_dir in self.cache_dir.iterdir():
            if not format_dir.is_dir():
                continue
            
            format_name = format_dir.name
            format_files = 0
            format_size = 0
            
            for file_path in format_dir.iterdir():
                if file_path.is_file() and not file_path.name.endswith('.meta'):
                    try:
                        format_files += 1
                        format_size += file_path.stat().st_size
                    except OSError:
                        pass
            
            format_stats[format_name] = {
                'files': format_files,
                'size_bytes': format_size,
                'size_mb': round(format_size / (1024 * 1024), 2)
            }
            
            total_files += format_files
            total_size_bytes += format_size
        
        current_stats = self.stats.copy()
        current_stats.update({
            'enabled': True,
            'total_files': total_files,
            'total_size_bytes': total_size_bytes,
            'total_size_mb': round(total_size_bytes / (1024 * 1024), 2),
            'max_size_mb': self.max_cache_size_mb,
            'ttl_days': self.ttl_days,
            'formats': format_stats
        })
        
        total_requests = current_stats['cache_hits'] + current_stats['cache_misses']
        current_stats['cache_hit_rate'] = (current_stats['cache_hits'] / total_requests * 100) if total_requests > 0 else 0
        
        return current_stats
    
    async def cleanup_expired_files(self) -> int:
        """Clean up expired files from all format directories."""
        if not self.enabled:
            return 0
        
        removed_count = 0
        current_time = datetime.now()
        
        for format_dir in self.cache_dir.iterdir():
            if not format_dir.is_dir():
                continue
            
            for file_path in format_dir.iterdir():
                if file_path.name.endswith('.meta'):
                    try:
                        async with aiofiles.open(file_path, 'r') as f:
                            metadata = json.loads(await f.read())
                        
                        expires_at_str = metadata.get('expires_at', '')
                        if expires_at_str:
                            expires_at = datetime.fromisoformat(expires_at_str)
                        else:
                            expires_at = current_time + timedelta(days=self.ttl_days)
                        
                        file_id = metadata.get('file_id', '')
                        file_format = metadata.get('output_format', '')
                        
                        if current_time > expires_at:
                            # File expired, remove it
                            if await self.delete_file(file_id, file_format):
                                removed_count += 1
                                
                    except Exception as e:
                        logger.error(f"Error processing metadata file {file_path}: {e}")
                        continue
        
        if removed_count > 0:
            logger.info(f"Disk cache cleanup: Removed {removed_count} expired files.")
        self.stats['cleanup_runs'] += 1
        self.stats['last_cleanup'] = current_time.isoformat()
        return removed_count
    
    async def cleanup_oldest_files(self, target_size_mb: int) -> int:
        """Clean up oldest files to reduce cache size."""
        if not self.enabled:
            return 0
        
        current_stats = await self.get_cache_stats()
        current_size_mb = current_stats['total_size_mb']
        
        if current_size_mb <= target_size_mb:
            return 0
        
        logger.info(f"Disk cache exceeding max size. Current: {current_size_mb:.2f}MB, Target: {target_size_mb}MB. Cleaning oldest files.")
        
        # Collect all files with their access times
        files_to_delete = []
        for format_dir in self.cache_dir.iterdir():
            if not format_dir.is_dir():
                continue
            
            for file_path in format_dir.iterdir():
                if file_path.name.endswith('.meta'):
                    try:
                        async with aiofiles.open(file_path, 'r') as f:
                            metadata = json.loads(await f.read())
                        
                        last_accessed_str = metadata.get('last_accessed', '')
                        if last_accessed_str:
                            last_accessed = datetime.fromisoformat(last_accessed_str)
                        else:
                            last_accessed = datetime.now()
                        
                        file_id = metadata.get('file_id', '')
                        file_format = metadata.get('output_format', '')
                        file_size = metadata.get('file_size', 0)
                        
                        files_to_delete.append((last_accessed, file_id, file_format, file_size))
                    except Exception as e:
                        logger.error(f"Error processing metadata file {file_path}: {e}")
                        continue
        
        # Sort by last accessed (oldest first)
        files_to_delete.sort()
        
        deleted_count = 0
        deleted_size_bytes = 0
        
        for _, file_id, file_format, file_size in files_to_delete:
            if current_size_mb - (deleted_size_bytes / (1024 * 1024)) <= target_size_mb:
                break
            
            if await self.delete_file(file_id, file_format):
                deleted_count += 1
                deleted_size_bytes += file_size
        
        if deleted_count > 0:
            logger.info(f"Disk cache cleanup: Removed {deleted_count} oldest files, freed {deleted_size_bytes / (1024 * 1024):.2f} MB.")
        return deleted_count
    
    async def clear_cache(self) -> int:
        """Clear all files from disk cache."""
        if not self.enabled:
            return 0
        
        deleted_count = 0
        for format_dir in self.cache_dir.iterdir():
            if format_dir.is_dir():
                for file_path in format_dir.iterdir():
                    if file_path.is_file():
                        try:
                            file_path.unlink()
                            deleted_count += 1
                        except OSError as e:
                            logger.error(f"Error clearing file {file_path} from disk cache: {e}")
        
        logger.info(f"Disk cache cleared. Removed {deleted_count} files.")
        self.stats = {
            'cache_hits': 0, 'cache_misses': 0, 'files_created': 0,
            'files_deleted': 0, 'cleanup_runs': 0, 'last_cleanup': None,
        }
        return deleted_count
    
    # Legacy methods for backward compatibility
    async def store_file(self, file_id: str, content: bytes, file_format: str, 
                        original_size: int = None, converted: bool = False) -> bool:
        """Legacy method for backward compatibility."""
        mime_type = self._get_mime_type(file_format)
        return await self.set_file(file_id, file_format, content, mime_type)
    
    def _get_mime_type(self, file_format: str) -> str:
        """Get MIME type for file format."""
        mime_types = {
            'tgs': 'application/gzip',
            'lottie': 'application/json',
            'webp': 'image/webp',
            'webm': 'video/webm',
            'png': 'image/png',
            'jpg': 'image/jpeg'
        }
        return mime_types.get(file_format, 'application/octet-stream')
