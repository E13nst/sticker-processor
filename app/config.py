import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Telegram Bot Configuration
    telegram_bot_token: str
    
    # Redis Configuration
    redis_enabled: bool = True  # Enable/disable Redis cache entirely
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: Optional[str] = None
    redis_database: int = 1
    redis_ssl_enabled: bool = False
    redis_max_connections: int = 50
    redis_socket_keepalive: bool = True
    redis_socket_connect_timeout: int = 5
    
    # Server Configuration
    server_host: str = "0.0.0.0"
    server_port: int = 8081
    log_level: str = "INFO"
    workers: int = 4  # Number of worker processes
    
    # File Processing Configuration
    max_file_size_mb: int = 20
    conversion_timeout_sec: int = 30
    cache_ttl_days: int = 7
    max_process_workers: int = 2  # For CPU-intensive tasks
    endpoint_timeout_sec: int = 30  # Overall timeout for endpoint requests (should be < gateway timeout)
    
    # Telegram Bot API Configuration
    telegram_api_base_url: str = "https://api.telegram.org"
    telegram_download_base_url: str = "https://api.telegram.org/file/bot"
    telegram_timeout_sec: int = 30
    telegram_api_detailed_logging: bool = True  # Enable detailed API logging
    
    # Telegram API Request Queue Configuration
    # Note: With multiple workers, each worker can make this many concurrent requests
    # Total = telegram_max_concurrent_requests * workers
    # Recommended: 2-3 per worker to avoid 429 errors across all workers
    telegram_max_concurrent_requests: int = 2  # Maximum concurrent API requests per worker
    telegram_request_delay_ms: int = 150  # Delay between requests in milliseconds (150ms = ~6 req/s)
    
    # HTTP Connection Pool Configuration
    # Increased for better parallel request handling
    http_max_connections: int = 200  # Total connections in pool
    http_max_connections_per_host: int = 50  # Connections per host (Telegram API)
    
    # Rate Limiting Configuration
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 100  # requests per time window
    rate_limit_window_sec: int = 60  # time window in seconds
    
    # Disk Cache Configuration
    disk_cache_dir: str = "/tmp/sticker_cache"
    disk_cache_max_size_mb: int = 1000  # Maximum disk cache size in MB
    disk_cache_ttl_days: int = 30  # TTL for disk cache files
    disk_cache_cleanup_interval_hours: int = 24  # How often to run cleanup
    disk_cache_enabled: bool = True  # Enable/disable disk cache
    
    # Retry Configuration
    max_retries: int = 3  # Maximum retry attempts for API calls
    base_retry_delay: float = 1.0  # Base delay in seconds for exponential backoff
    max_retry_delay: float = 60.0  # Maximum delay in seconds
    
    # Cache Strategy Configuration
    redis_max_file_size_mb: int = 5  # Maximum file size for Redis cache (MB)
    redis_preferred_formats: list = ['lottie', 'webp', 'png', 'jpg']  # Preferred formats for Redis
    redis_excluded_formats: list = ['tgs']  # Formats excluded from Redis cache
    disk_max_file_size_mb: int = 50  # Maximum file size for disk cache (MB)
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()
