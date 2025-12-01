# Sticker Processor Service

Python microservice for processing and caching Telegram stickers with format conversion support.

## Features

- **TGS to Lottie JSON conversion** using multiple methods:
  - Direct gzip decompression (fastest)
  - Python `lottie` library
  - Node.js `tgs2json` CLI tool (optional)
- **Redis caching** with configurable TTL
- **Async processing** with FastAPI
- **Swagger UI** documentation at `/docs`
- **Comprehensive metadata** in response headers
- **Error handling** with fallback to original files

## Supported Formats

| Input Format | Output Format | Conversion |
|-------------|---------------|------------|
| TGS         | Lottie JSON   | ✅ Converted |
| WebM        | WebM          | ❌ No conversion |
| WebP        | WebP          | ❌ No conversion |
| PNG         | PNG           | ❌ No conversion |
| JPG         | JPG           | ❌ No conversion |

## API Endpoints

- `GET /stickers/{file_id}` - Get sticker file
- `GET /health` - Health check
- `GET /cache/stats` - Cache statistics
- `GET /api/stats` - Telegram API usage statistics
- `DELETE /cache/{file_id}` - Delete specific file from cache
- `DELETE /cache/all` - Clear all cache
- `GET /formats` - Supported formats
- `GET /docs` - Swagger UI documentation

## Environment Variables

Copy `config.env.example` to `.env` and configure:

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DATABASE=1
SERVER_HOST=0.0.0.0
SERVER_PORT=8081
LOG_LEVEL=INFO
MAX_FILE_SIZE_MB=20
CONVERSION_TIMEOUT_SEC=30
CACHE_TTL_DAYS=7
```

## Quick Start

### Using Docker Compose (Recommended)

```bash
# Set your bot token
export TELEGRAM_BOT_TOKEN=your_bot_token_here

# Start services
docker-compose up -d

# Check logs
docker-compose logs -f sticker-processor
```

### Manual Installation

```bash
# Install Python dependencies
pip install -r requirements.txt

# Optional: Install Node.js tgs2json tool for additional TGS conversion support
npm install -g tgs2json

# Run the service
python -m app.main
```

**Note:** The service works with just the Python `lottie` library. The `tgs2json` tool is optional and provides an additional conversion method.

## Response Headers

The service returns comprehensive metadata in response headers:

```
X-Cache-Status: MISS/HIT
X-File-ID: CAACAgIAAxUAAWjHy8...
X-Original-Format: tgs
X-Output-Format: lottie
X-File-Size: 12345
X-Is-Converted: true
X-Conversion-Time-Ms: 150
Cache-Control: max-age=604800, public
```

## Error Handling

- **File not found**: Returns 404
- **Conversion failed**: Returns original file with warning log
- **Redis unavailable**: Continues without caching
- **File too large**: Returns 413 (configurable limit)

## Testing

### Quick Start

```bash
# Install test dependencies
venv/bin/pip install -r requirements-dev.txt

# Run unit tests (fast, no external dependencies)
venv/bin/pytest -v -m unit

# Run integration tests with production Redis
venv/bin/pytest -v -m "integration and redis"

# 🔴 Run CRITICAL tests (MUST pass for production)
venv/bin/pytest -v -m critical -s
```

### Test Coverage

- **Unit tests** (16 tests): Fast, no external dependencies, ~0.2s
- **Integration tests** (14 tests): Require Redis connection
- **Critical tests** (9 tests): 🔴 MUST pass - verify production Redis connectivity

**Total: 38 automated tests with ~42% code coverage**

### Testing Framework Stack

- **pytest** - Main testing framework
- **pytest-asyncio** - Async test support
- **httpx** - HTTP client for API testing
- **fakeredis** - Redis mocking for unit tests
- **pytest-cov** - Code coverage reports

See [TESTING_QUICK_START.md](TESTING_QUICK_START.md) for detailed testing guide.

### Using Makefile

```bash
make test-unit           # Unit tests only
make test-integration    # Integration tests
make test-cov           # With coverage HTML report
make redis-local        # Start local Redis for testing
```

## Development

```bash
# Install development dependencies
pip install -r requirements.txt

# Run with auto-reload
uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload

# Access Swagger UI
open http://localhost:8081/docs
```

## Production Deployment

The service is designed to be deployed separately from the main Spring Boot application:

1. Build Docker image
2. Deploy to your container platform
3. Configure environment variables
4. Set up Redis instance
5. Update main application to proxy requests to this service

## Monitoring

- **Health check**: `GET /health`
- **Cache stats**: `GET /cache/stats` - Redis cache usage
- **API stats**: `GET /api/stats` - Telegram API statistics (requests, errors, performance)
- **Detailed logging**: Set `TELEGRAM_API_DETAILED_LOGGING=true` for verbose API logs
- Application logs include:
  - Conversion times
  - Cache hit rates
  - API request/response times
  - Error classification and tracking

See `TELEGRAM_API_LOGGING.md` for details on logging capabilities.
