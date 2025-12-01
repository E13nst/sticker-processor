import asyncio
import json
import logging
import tempfile
import os
import gzip
import subprocess
import shutil
from typing import Optional, Tuple
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from app.config import settings

logger = logging.getLogger(__name__)


class ConverterService:
    """Service for converting sticker formats."""
    
    def __init__(self):
        self.timeout = settings.conversion_timeout_sec
        self._check_available_tools()
        # Create process pool for CPU-intensive tasks (optional, may not work on some systems)
        self.process_pool = None
        try:
            # Only try to create ProcessPoolExecutor if we're not in a restricted environment
            import os
            if os.getenv('DISABLE_PROCESS_POOL', 'false').lower() != 'true':
                self.process_pool = ProcessPoolExecutor(max_workers=settings.max_process_workers)
                logger.info(f"Initialized ProcessPoolExecutor with {settings.max_process_workers} workers")
            else:
                logger.info("ProcessPoolExecutor disabled by environment variable")
        except (PermissionError, OSError, Exception) as e:
            logger.warning(f"ProcessPoolExecutor not available: {e}. Will use sync processing.")
            self.process_pool = None
    
    def __del__(self):
        """Cleanup process pool on deletion."""
        if hasattr(self, 'process_pool') and self.process_pool:
            self.process_pool.shutdown(wait=False)
    
    def _check_available_tools(self):
        """Check which conversion tools are available."""
        self.tgs2json_available = shutil.which('tgs2json') is not None
        self.lottie_available = False
        
        try:
            import lottie
            self.lottie_available = True
            logger.info("lottie library is available")
        except ImportError:
            logger.warning("lottie library not available")
        
        if self.tgs2json_available:
            logger.info("tgs2json CLI tool is available")
        else:
            logger.warning("tgs2json CLI tool not available")
    
    async def convert_tgs_to_lottie(self, tgs_content: bytes) -> Optional[Tuple[str, bytes]]:
        """Convert TGS file to Lottie JSON using multiple methods."""
        try:
            # Method 1: Direct gzip decompression (fastest)
            result = await self._convert_via_gzip(tgs_content)
            if result:
                return result
            
            # Method 2: Using lottie library
            if self.lottie_available:
                result = await self._convert_via_lottie_library(tgs_content)
                if result:
                    return result
            
            # Method 3: Using tgs2json CLI tool
            if self.tgs2json_available:
                result = await self._convert_via_tgs2json(tgs_content)
                if result:
                    return result
            
            logger.error("All TGS conversion methods failed")
            return None
                    
        except Exception as e:
            logger.error(f"Error converting TGS to Lottie: {e}")
            return None
    
    @staticmethod
    def _convert_gzip_sync(tgs_content: bytes) -> Optional[Tuple[str, bytes]]:
        """Convert TGS using direct gzip decompression (CPU-intensive, runs in separate process)."""
        try:
            # Decompress TGS content
            decompressed = gzip.decompress(tgs_content)
            
            # Try to parse as JSON
            lottie_data = json.loads(decompressed.decode('utf-8'))
            
            # Validate that it's a valid Lottie animation
            required_fields = ['v', 'fr', 'w', 'h']
            if all(field in lottie_data for field in required_fields):
                # Convert back to JSON bytes
                lottie_json = json.dumps(lottie_data, separators=(',', ':')).encode('utf-8')
                return 'lottie', lottie_json
            else:
                return None
                
        except (gzip.BadGzipFile, json.JSONDecodeError, UnicodeDecodeError):
            return None
    
    async def _convert_via_gzip(self, tgs_content: bytes) -> Optional[Tuple[str, bytes]]:
        """Convert TGS using direct gzip decompression (offloaded to process pool if available)."""
        try:
            # Run CPU-intensive decompression in process pool if available, otherwise sync
            if self.process_pool:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    self.process_pool,
                    self._convert_gzip_sync,
                    tgs_content
                )
            else:
                # Fallback to sync execution if process pool not available
                result = self._convert_gzip_sync(tgs_content)
            
            if result:
                logger.info("Successfully converted TGS to Lottie JSON using gzip decompression")
                return result
            else:
                logger.warning("TGS file doesn't contain valid Lottie animation data")
                return None
                
        except Exception as e:
            logger.warning(f"Direct TGS decompression failed: {e}")
            return None
    
    async def _convert_via_lottie_library(self, tgs_content: bytes) -> Optional[Tuple[str, bytes]]:
        """Convert TGS using lottie library."""
        try:
            import lottie
            
            # Create temporary file
            with tempfile.NamedTemporaryFile(suffix='.tgs', delete=False) as tgs_file:
                tgs_file.write(tgs_content)
                tgs_path = tgs_file.name
            
            try:
                # Load TGS file using lottie library
                animation = lottie.parsers.tgs.load_tgs(tgs_path)
                
                if animation:
                    # Export as JSON
                    lottie_json = json.dumps(animation.export_dict(), separators=(',', ':')).encode('utf-8')
                    logger.info("Successfully converted TGS to Lottie JSON using lottie library")
                    return 'lottie', lottie_json
                else:
                    logger.error("Failed to load TGS file with lottie library")
                    return None
                    
            finally:
                # Clean up temporary file
                try:
                    os.unlink(tgs_path)
                except OSError:
                    pass
                    
        except Exception as e:
            logger.error(f"lottie library conversion failed: {e}")
            return None
    
    async def _convert_via_tgs2json(self, tgs_content: bytes) -> Optional[Tuple[str, bytes]]:
        """Convert TGS using tgs2json CLI tool."""
        try:
            # Create temporary files
            with tempfile.NamedTemporaryFile(suffix='.tgs', delete=False) as tgs_file:
                tgs_file.write(tgs_content)
                tgs_path = tgs_file.name
            
            with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as json_file:
                json_path = json_file.name
            
            try:
                # Run tgs2json command
                process = await asyncio.create_subprocess_exec(
                    'tgs2json', tgs_path, '-o', json_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), 
                    timeout=self.timeout
                )
                
                if process.returncode == 0 and os.path.exists(json_path):
                    # Read the converted JSON
                    with open(json_path, 'rb') as f:
                        lottie_json = f.read()
                    
                    logger.info("Successfully converted TGS to Lottie JSON using tgs2json")
                    return 'lottie', lottie_json
                else:
                    logger.error(f"tgs2json conversion failed: {stderr.decode()}")
                    return None
                    
            finally:
                # Clean up temporary files
                for path in [tgs_path, json_path]:
                    try:
                        if os.path.exists(path):
                            os.unlink(path)
                    except OSError:
                        pass
                        
        except asyncio.TimeoutError:
            logger.error("tgs2json conversion timed out")
            return None
        except Exception as e:
            logger.error(f"tgs2json conversion failed: {e}")
            return None
    
    def _is_valid_lottie(self, data: dict) -> bool:
        """Check if data is a valid Lottie animation."""
        required_fields = ['v', 'fr', 'w', 'h']
        return all(field in data for field in required_fields)
    
    async def process_sticker(self, content: bytes, file_format: str) -> Tuple[str, bytes, bool]:
        """
        Process sticker content based on format.
        Returns: (output_format, processed_content, was_converted)
        """
        if file_format == 'tgs':
            result = await self.convert_tgs_to_lottie(content)
            if result:
                output_format, converted_content = result
                return output_format, converted_content, True
            else:
                # Fallback to original
                logger.warning("TGS conversion failed, returning original file")
                return file_format, content, False
        else:
            # No conversion needed
            return file_format, content, False
    
    def get_output_mime_type(self, output_format: str) -> str:
        """Get MIME type for output format."""
        mime_types = {
            'lottie': 'application/json',
            'webm': 'video/webm',
            'webp': 'image/webp',
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'tgs': 'application/gzip'
        }
        return mime_types.get(output_format, 'application/octet-stream')
