# Tests

Comprehensive test suite for Sticker Processor Service.

## 🧪 Test Structure

```
tests/
├── conftest.py              # Pytest fixtures and configuration
├── unit/                    # Unit tests (fast, no external dependencies)
│   ├── test_converter.py   # Converter service tests
│   └── test_telegram_service.py  # Telegram service tests
└── integration/             # Integration tests (require external services)
    ├── test_redis_integration.py  # Redis integration tests
    └── test_api_endpoints.py      # FastAPI endpoint tests
```

## 📦 Setup

### Install test dependencies:

```bash
venv/bin/pip install -r requirements-dev.txt
```

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

## 🏷️ Test Markers

Tests are marked with pytest markers for selective running:

- `@pytest.mark.unit` - Unit tests (fast, no external dependencies)
- `@pytest.mark.integration` - Integration tests (require external services)
- `@pytest.mark.redis` - Tests requiring Redis connection
- `@pytest.mark.telegram` - Tests requiring Telegram API
- `@pytest.mark.slow` - Slow tests (may take >1s)

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
```

## 🔧 Configuration

Test configuration is in `pytest.ini`:
- Coverage settings
- Test discovery patterns
- Markers
- Default options

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

## 📝 Writing Tests

### Unit Test Example:

```python
import pytest

@pytest.mark.unit
class TestMyService:
    def test_something(self, my_service_fixture):
        result = my_service_fixture.do_something()
        assert result == expected_value
```

### Integration Test Example:

```python
import pytest

@pytest.mark.integration
@pytest.mark.redis
class TestRedisIntegration:
    @pytest.mark.asyncio
    async def test_redis_operation(self, redis_service):
        await redis_service.set_something("key", "value")
        result = await redis_service.get_something("key")
        assert result == "value"
```

### Async Test Example:

```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    result = await some_async_function()
    assert result is not None
```

## 🎯 Best Practices

1. **Use appropriate markers** - Mark tests with `unit`, `integration`, `redis`, etc.
2. **Keep unit tests fast** - No I/O, no external dependencies
3. **Use fixtures** - Reuse test setup code via fixtures in `conftest.py`
4. **Test one thing** - Each test should verify one specific behavior
5. **Descriptive names** - Test names should describe what they test
6. **Cleanup after tests** - Use fixtures for cleanup (autouse fixtures)
7. **Mock external services** - Use `fakeredis`, `respx` for unit tests
8. **Async/await** - Use `@pytest.mark.asyncio` for async tests

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
    pytest -m unit --cov=app --cov-report=xml

- name: Upload coverage
  uses: codecov/codecov-action@v3
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

## 📚 Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio documentation](https://pytest-asyncio.readthedocs.io/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [httpx documentation](https://www.python-httpx.org/)

