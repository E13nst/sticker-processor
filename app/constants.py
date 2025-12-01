"""Application constants."""
# Performance thresholds
SLOW_REQUEST_THRESHOLD_MS = 5000  # Log warnings for requests > 5s
SLOW_REDIS_QUERY_THRESHOLD_MS = 100  # Log warnings for Redis queries > 100ms
SLOW_DISK_CACHE_THRESHOLD_MS = 500  # Log warnings for disk cache checks > 500ms
SLOW_TELEGRAM_API_THRESHOLD_MS = 10000  # Log warnings for Telegram API calls > 10s

# Cache formats
CACHE_FORMATS_TO_TRY = ['lottie', 'webp', 'png', 'jpg', 'webm']

# MIME types
MIME_TYPE_JSON = 'application/json'
MIME_TYPE_TGS = 'application/gzip'
MIME_TYPE_WEBM = 'video/webm'
MIME_TYPE_WEBP = 'image/webp'
MIME_TYPE_PNG = 'image/png'
MIME_TYPE_JPEG = 'image/jpeg'

# File formats
FORMAT_TGS = 'tgs'
FORMAT_LOTTIE = 'lottie'
FORMAT_WEBM = 'webm'
FORMAT_WEBP = 'webp'
FORMAT_PNG = 'png'
FORMAT_JPG = 'jpg'

# Statistics timeout
STATS_TIMEOUT_SECONDS = 5.0

# Cache cleanup
CACHE_CLEANUP_TARGET_PERCENT = 0.8  # Clean to 80% of max size

