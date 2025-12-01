# Tests

Comprehensive test suite for Sticker Processor Service with Allure reporting.

## 🧪 Test Structure

```
tests/
├── conftest.py              # Pytest fixtures, Allure hooks, and configuration
├── unit/                    # Unit tests (fast, no external dependencies)
│   ├── test_converter.py              # Converter service tests
│   ├── test_telegram_service.py       # Telegram service tests
│   ├── test_cache_manager.py          # Cache manager tests
│   ├── test_cache_strategy.py         # Cache strategy tests
│   ├── test_disk_cache.py             # Disk cache service tests
│   ├── test_telegram_queue.py        # Telegram request queue tests
│   └── test_rate_limit.py             # Rate limit middleware tests
├── integration/             # Integration tests (require external services)
│   ├── test_redis_integration.py      # Redis integration tests
│   ├── test_api_endpoints.py         # FastAPI endpoint tests
│   ├── test_disk_cache_fallback.py   # Disk cache fallback tests
│   ├── test_production_redis.py      # Production Redis tests
│   └── test_cache_manager_integration.py  # Cache manager integration tests
└── e2e/                      # End-to-end tests (real Telegram API)
    └── test_e2e_real_stickers.py    # E2E tests with real stickers
```

## 📦 Setup

### Install test dependencies:

```bash
venv/bin/pip install -r requirements-dev.txt
```

### Install Allure CLI (optional, for viewing reports):

**Option 1: Using npm**
```bash
npm install -g allure-commandline
```

**Option 2: Using Homebrew (macOS)**
```bash
brew install allure
```

**Option 3: Download standalone**
- Download from https://github.com/allure-framework/allure2/releases
- Extract and add to PATH

## 🚀 Running Tests

### Run all tests:
```bash
venv/bin/pytest
```

### Run only unit tests (fast, no external dependencies):
```bash
venv/bin/pytest -m unit
```

### Run only integration tests:
```bash
venv/bin/pytest -m integration
```

### Run E2E tests (requires TELEGRAM_BOT_TOKEN):
```bash
export TELEGRAM_BOT_TOKEN=your_bot_token_here
venv/bin/pytest -m e2e
```

### Run with coverage report:
```bash
venv/bin/pytest --cov=app --cov-report=html
open htmlcov/index.html
```

### Run specific test file:
```bash
venv/bin/pytest tests/unit/test_converter.py
```

### Run specific test:
```bash
venv/bin/pytest tests/unit/test_converter.py::TestConverterService::test_converter_initialization
```

### Run with verbose output:
```bash
venv/bin/pytest -v
```

### Run and stop on first failure:
```bash
venv/bin/pytest -x
```

## 📊 Allure Reports

Allure provides beautiful, interactive test reports with detailed steps, attachments, and history.

### Generate Allure Results

Tests automatically generate Allure results in `allure-results/` directory:

```bash
venv/bin/pytest --alluredir=allure-results
```

### View Allure Report

**Option 1: Serve report (recommended for development)**
```bash
allure serve allure-results
```
This starts a local web server and opens the report in your browser.

**Option 2: Generate static HTML report**
```bash
allure generate allure-results -o allure-report --clean
allure open allure-report
```

**Option 3: Open existing report**
```bash
allure open allure-report
```

### Allure Features

- **Detailed Steps**: Each test shows step-by-step execution
- **Attachments**: JSON responses, logs, and data are attached automatically
- **History**: Track test results over time
- **Categories**: Tests grouped by severity (critical, normal, minor)
- **Tags**: Filter tests by features, components, etc.
- **Timeline**: See test execution timeline
- **Graphs**: Visual representation of test results

### Allure Annotations

Tests use Allure annotations for better reporting:

- `@allure.title()` - Custom test titles
- `@allure.description()` - Detailed test descriptions
- `@allure.step()` - Step-by-step execution details
- `@allure.severity()` - Test priority (critical, normal, minor)
- `@allure.tag()` - Tags for filtering
- `@allure.feature()` - Feature grouping
- `@allure.story()` - User stories

## 🏷️ Test Markers

Tests are marked with pytest markers for selective running:

- `@pytest.mark.unit` - Unit tests (fast, no external dependencies)
- `@pytest.mark.integration` - Integration tests (require external services)
- `@pytest.mark.e2e` - End-to-end tests with real services
- `@pytest.mark.slow` - Slow tests (may take >1s)
- `@pytest.mark.redis` - Tests requiring Redis connection
- `@pytest.mark.telegram` - Tests requiring Telegram API
- `@pytest.mark.real_api` - Tests using real external APIs
- `@pytest.mark.critical` - Critical tests that MUST pass

### Examples:

```bash
# Run only unit tests
pytest -m unit

# Run only Redis integration tests
pytest -m redis

# Run all tests except slow ones
pytest -m "not slow"

# Run integration tests but skip Redis tests
pytest -m "integration and not redis"

# Run E2E tests only
pytest -m e2e

# Run critical tests
pytest -m critical
```

## 🔧 Configuration

Test configuration is in `pytest.ini`:
- Coverage settings
- Test discovery patterns
- Markers
- Default options
- Allure results directory

## 📊 Coverage Reports

Coverage reports are generated in multiple formats:
- **Terminal**: Shows missing lines directly in terminal
- **HTML**: Interactive report in `htmlcov/` directory
- **XML**: For CI/CD integration

## 🐳 Running Tests with Docker

### Build and run tests in container:
```bash
docker-compose run --rm sticker-processor pytest
```

### Run specific test markers in container:
```bash
docker-compose run --rm sticker-processor pytest -m unit
```

## 🧹 Redis for Integration Tests

Integration tests require Redis connection. By default, tests use:
- **Host**: `localhost` (or from `REDIS_HOST` env var)
- **Port**: `6379`
- **Database**: `1` (separate from production DB 0)
- **SSL**: Disabled for local testing

### Using local Redis:
```bash
# Start Redis with Docker
docker run -d -p 6379:6379 redis:7-alpine

# Run integration tests
pytest -m integration
```

### Using remote Redis:
```bash
# Set environment variables
export REDIS_HOST=your-redis-host
export REDIS_PORT=6379
export REDIS_PASSWORD=your-password
export REDIS_SSL_ENABLED=true

# Run tests
pytest -m integration
```

### Skip integration tests if Redis unavailable:
Integration tests will automatically skip if Redis is not available.

## 🎯 E2E Tests

E2E tests use real Telegram Bot API to test with actual stickers.

### Requirements:
- `TELEGRAM_BOT_TOKEN` environment variable must be set
- Service must be running (or use `client` fixture for in-process testing)

### Test Coverage:
- **TGS Animation Stickers**: Tests loading and conversion of TGS stickers from `worldart` pack
- **Video Stickers**: Tests loading video stickers from video sticker pack
- **Cache Performance**: Verifies that cached requests are faster

### Running E2E Tests:
```bash
# Set bot token
export TELEGRAM_BOT_TOKEN=your_bot_token_here

# Run E2E tests
pytest -m e2e

# Run specific E2E test
pytest tests/e2e/test_e2e_real_stickers.py::TestE2ERealStickers::test_tgs_animation_stickers
```

### E2E Test Packs:
- TGS animations: `https://t.me/addstickers/worldart`
- Video stickers: `https://t.me/addstickers/pack_1_40802189314_5786_155347765_by_sticker_bot`

## 📝 Writing Tests

### Unit Test Example:

```python
import pytest
import allure

@allure.feature("My Feature")
@allure.tag("my-tag", "unit")
@pytest.mark.unit
class TestMyService:
    @allure.title("Test something important")
    @allure.description("Detailed description of what this test does")
    @allure.severity(allure.severity_level.NORMAL)
    def test_something(self, my_service_fixture):
        with allure.step("Step 1: Do something"):
            result = my_service_fixture.do_something()
        
        with allure.step("Step 2: Verify result"):
            assert result == expected_value
```

### Integration Test Example:

```python
import pytest
import allure

@allure.feature("Integration")
@allure.tag("integration", "redis")
@pytest.mark.integration
@pytest.mark.redis
class TestRedisIntegration:
    @allure.title("Test Redis operation")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.asyncio
    async def test_redis_operation(self, redis_service):
        with allure.step("Store data in Redis"):
            await redis_service.set_something("key", "value")
        
        with allure.step("Retrieve data from Redis"):
            result = await redis_service.get_something("key")
            assert result == "value"
```

### E2E Test Example:

```python
import pytest
import allure

@allure.feature("E2E Tests")
@allure.tag("e2e", "telegram", "real-api")
@pytest.mark.e2e
@pytest.mark.telegram
@pytest.mark.real_api
class TestE2E:
    @allure.title("E2E: Test real API")
    @allure.description("Test with real external API")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.asyncio
    async def test_real_api(self, client):
        with allure.step("Call real API"):
            response = await client.get("/api/endpoint")
            allure.attach(
                response.text,
                "API Response",
                allure.attachment_type.TEXT
            )
            assert response.status_code == 200
```

### Async Test Example:

```python
import pytest
import allure

@allure.feature("Async Operations")
@pytest.mark.asyncio
async def test_async_function():
    with allure.step("Execute async operation"):
        result = await some_async_function()
        assert result is not None
```

## 🎯 Best Practices

1. **Use appropriate markers** - Mark tests with `unit`, `integration`, `e2e`, `redis`, etc.
2. **Keep unit tests fast** - No I/O, no external dependencies
3. **Use fixtures** - Reuse test setup code via fixtures in `conftest.py`
4. **Test one thing** - Each test should verify one specific behavior
5. **Descriptive names** - Test names should describe what they test
6. **Cleanup after tests** - Use fixtures for cleanup (autouse fixtures)
7. **Mock external services** - Use `fakeredis`, `respx` for unit tests
8. **Async/await** - Use `@pytest.mark.asyncio` for async tests
9. **Allure annotations** - Add `@allure.step()`, `@allure.title()`, etc. for better reports
10. **Attach data** - Use `allure.attach()` for JSON responses, logs, etc.

## 🔍 Debugging Tests

### Run with print statements:
```bash
pytest -s
```

### Run with debugger:
```bash
pytest --pdb
```

### Show local variables on failure:
```bash
pytest -l
```

### Run last failed tests:
```bash
pytest --lf
```

### Run tests that failed, then rest:
```bash
pytest --ff
```

## 📈 CI/CD Integration

### GitHub Actions example:

```yaml
- name: Run tests
  run: |
    pip install -r requirements-dev.txt
    pytest -m unit --cov=app --cov-report=xml --alluredir=allure-results

- name: Generate Allure Report
  run: |
    allure generate allure-results -o allure-report --clean

- name: Upload coverage
  uses: codecov/codecov-action@v3

- name: Upload Allure Report
  uses: actions/upload-artifact@v3
  with:
    name: allure-report
    path: allure-report
```

## 🆘 Troubleshooting

### Issue: Tests fail with "Redis connection refused"
**Solution**: Start local Redis or skip integration tests: `pytest -m "not redis"`

### Issue: Import errors
**Solution**: Ensure you're using the venv: `venv/bin/pytest`

### Issue: Async warnings
**Solution**: Make sure `pytest-asyncio` is installed and tests use `@pytest.mark.asyncio`

### Issue: Coverage not showing
**Solution**: Run with `--cov=app` flag and check `pytest.ini` configuration

### Issue: Allure not generating reports
**Solution**: 
1. Ensure `allure-pytest` is installed: `pip install allure-pytest`
2. Check that `--alluredir=allure-results` is in `pytest.ini` or command line
3. Verify Allure CLI is installed: `allure --version`

### Issue: E2E tests skip
**Solution**: Set `TELEGRAM_BOT_TOKEN` environment variable

## 📚 Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio documentation](https://pytest-asyncio.readthedocs.io/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [httpx documentation](https://www.python-httpx.org/)
- [Allure Framework](https://docs.qameta.io/allure/)
- [Allure Python](https://github.com/allure-framework/allure-python)
