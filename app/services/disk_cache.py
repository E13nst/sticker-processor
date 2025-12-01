import os
import hashlib
import shutil
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
import aiofiles

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
    
    def _get_cache_path(self, file_id: str, file_format: str) -> Path:
        """Get the cache file path for a given file ID and format."""
        file_hash = self._get_file_hash(file_id)
        # Create separate directories for each file format
        format_dir = self.cache_dir / file_format
        return format_dir / f"{file_hash}.{file_format}"
    
    def _get_metadata_path(self, file_id: str, file_format: str = None) -> Path:
        """Get the metadata file path for a given file ID."""
        file_hash = self._get_file_hash(file_id)
        if file_format:
            # Store metadata in the same format directory
            format_dir = self.cache_dir / file_format
            return format_dir / f"{file_hash}.meta"
        else:
            # Fallback to root directory for backward compatibility
            return self.cache_dir / f"{file_hash}.meta"
    
    async def _write_metadata(self, file_id: str, metadata: Dict[str, Any], file_format: str = None) -> None:
        """Write metadata to disk."""
        metadata_path = self._get_metadata_path(file_id, file_format)
        # Ensure directory exists
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(metadata_path, 'w') as f:
            await f.write(str(metadata))
    
    async def _read_metadata(self, file_id: str, file_format: str = None) -> Optional[Dict[str, Any]]:
        """Read metadata from disk."""
        metadata_path = self._get_metadata_path(file_id, file_format)
        if not metadata_path.exists():
            return None
        
        try:
            async with aiofiles.open(metadata_path, 'r') as f:
                content = await f.read()
                # Simple metadata parsing (in production, use JSON)
                metadata = {}
                for line in content.strip().split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        metadata[key.strip()] = value.strip()
                return metadata
        except Exception as e:
            logger.error(f"Error reading metadata for {file_id}: {e}")
            return None
    
    async def store_file(self, file_id: str, content: bytes, file_format: str, 
                        original_size: int = None, converted: bool = False) -> bool:
        """Store file content in disk cache."""
        try:
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
            
            # Write metadata
            metadata = {
                'file_id': file_id,
                'format': file_format,
                'size': len(content),
                'original_size': original_size or len(content),
                'converted': converted,
                'created_at': datetime.now().isoformat(),
                'expires_at': (datetime.now() + timedelta(days=self.ttl_days)).isoformat(),
            }
            await self._write_metadata(file_id, metadata, file_format)
            
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
            cache_path = self._get_cache_path(file_id, file_format)
            
            if not cache_path.exists():
                self.stats['cache_misses'] += 1
                return None
            
            # Check metadata for expiration
            metadata = await self._read_metadata(file_id, file_format)
            if metadata:
                expires_at_str = metadata.get('expires_at', '')
                if expires_at_str:
                    expires_at = datetime.fromisoformat(expires_at_str)
                else:
                    expires_at = datetime.now() + timedelta(days=self.ttl_days)
                if datetime.now() > expires_at:
                    # File expired, remove it
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
            cache_path = self._get_cache_path(file_id, file_format)
            metadata_path = self._get_metadata_path(file_id)
            
            # Get file size before deletion
            file_size = 0
            if cache_path.exists():
                file_size = cache_path.stat().st_size
                cache_path.unlink()
            
            if metadata_path.exists():
                metadata_path.unlink()
            
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
    
    async def cleanup_expired_files(self) -> int:
        """Remove expired files from disk cache."""
        try:
            removed_count = 0
            current_time = datetime.now()
            
            for file_path in self.cache_dir.rglob("*.meta"):
                try:
                    # Read metadata
                    async with aiofiles.open(file_path, 'r') as f:
                        content = await f.read()
                    
                    # Parse metadata
                    metadata = {}
                    for line in content.strip().split('\n'):
                        if ':' in line:
                            key, value = line.split(':', 1)
                            metadata[key.strip()] = value.strip()
                    
                    expires_at_str = metadata.get('expires_at', '')
                    if expires_at_str:
                        expires_at = datetime.fromisoformat(expires_at_str)
                    else:
                        expires_at = datetime.now() + timedelta(days=self.ttl_days)
                    
                    file_id = metadata.get('file_id', '')
                    file_format = metadata.get('format', '')
                    
                    if current_time > expires_at:
                        # File expired, remove it
                        if await self.delete_file(file_id, file_format):
                            removed_count += 1
                            
                except Exception as e:
                    logger.error(f"Error processing metadata file {file_path}: {e}")
                    continue
            
            self.stats['cleanup_runs'] += 1
            self.stats['last_cleanup'] = current_time.isoformat()
            
            if removed_count > 0:
                logger.info(f"Cleaned up {removed_count} expired files from disk cache")
            
            return removed_count
            
        except Exception as e:
            logger.error(f"Error during disk cache cleanup: {e}")
            return 0
    
    async def cleanup_oldest_files(self, target_size_mb: int) -> int:
        """Remove oldest files to reduce cache size to target."""
        try:
            target_size_bytes = target_size_mb * 1024 * 1024
            
            if self.stats['total_size_bytes'] <= target_size_bytes:
                return 0
            
            # Collect all files with their metadata
            files_info = []
            for file_path in self.cache_dir.rglob("*.meta"):
                try:
                    metadata = await self._read_metadata("")
                    if metadata:
                        file_id = metadata.get('file_id', '')
                        file_format = metadata.get('format', '')
                        created_at_str = metadata.get('created_at', '')
                        if created_at_str:
                            created_at = datetime.fromisoformat(created_at_str)
                        else:
                            created_at = datetime.now()
                        
                        cache_path = self._get_cache_path(file_id, file_format)
                        if cache_path.exists():
                            file_size = cache_path.stat().st_size
                            files_info.append((created_at, file_id, file_format, file_size))
                            
                except Exception as e:
                    logger.error(f"Error processing file {file_path}: {e}")
                    continue
            
            # Sort by creation time (oldest first)
            files_info.sort(key=lambda x: x[0])
            
            # Remove files until we reach target size
            removed_count = 0
            for created_at, file_id, file_format, file_size in files_info:
                if self.stats['total_size_bytes'] <= target_size_bytes:
                    break
                
                if await self.delete_file(file_id, file_format):
                    removed_count += 1
            
            if removed_count > 0:
                logger.info(f"Removed {removed_count} oldest files to reduce cache size")
            
            return removed_count
            
        except Exception as e:
            logger.error(f"Error during disk cache size cleanup: {e}")
            return 0
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get disk cache statistics."""
        # Recalculate stats from actual files
        total_files = 0
        total_size_bytes = 0
        file_types = {}
        
        # Search in subdirectories for each format
        for file_path in self.cache_dir.rglob("*"):
            if file_path.is_file() and not file_path.name.endswith('.meta'):
                total_files += 1
                total_size_bytes += file_path.stat().st_size
                
                # Extract file type from extension
                file_extension = file_path.suffix.lower().lstrip('.')
                if file_extension:
                    file_types[file_extension] = file_types.get(file_extension, 0) + 1
        
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
    
    async def clear_cache(self) -> int:
        """Clear all files from disk cache."""
        try:
            removed_count = 0
            
            for file_path in self.cache_dir.glob("*"):
                if file_path.is_file():
                    file_path.unlink()
                    removed_count += 1
            
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
