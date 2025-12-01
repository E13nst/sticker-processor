# 🧪 Test Commands Cheatsheet

## Quick Commands

### ⚡️ Run Unit Tests (FAST - 0.2s)
```bash
venv/bin/pytest -v -m unit
```

### 🔴 Run Critical Tests (Production Redis)
```bash
venv/bin/pytest -v -m critical -s
```
**Important**: Make sure `.env` has correct production Redis settings!

### 🔗 Run All Integration Tests
```bash
venv/bin/pytest -v -m integration
```

### 🎯 Run Specific Test File
```bash
venv/bin/pytest -v tests/unit/test_converter.py
```

### 🎨 Run With Coverage Report
```bash
venv/bin/pytest --cov=app --cov-report=html
open htmlcov/index.html
```

### 🚀 Run All Tests
```bash
venv/bin/pytest -v
```

## Test Markers

Run specific types of tests:

```bash
# Only unit tests
pytest -m unit

# Only Redis integration tests  
pytest -m redis

# Critical tests (production Redis)
pytest -m critical

# Integration but NOT critical
pytest -m "integration and not critical"

# All except slow tests
pytest -m "not slow"
```

## Debugging

### Show print() output
```bash
pytest -v -s
```

### Stop on first failure
```bash
pytest -x
```

### Run last failed tests
```bash
pytest --lf
```

### Full traceback
```bash
pytest --tb=long
```

### Specific test
```bash
pytest tests/unit/test_converter.py::TestConverterService::test_process_sticker_tgs -v -s
```

## Makefile Shortcuts

```bash
make test-unit           # Unit tests
make test-integration    # Integration tests
make test-cov           # With HTML coverage report
make test-failed        # Re-run last failed tests
make redis-local        # Start local Redis
make clean              # Clean test artifacts
```

## Expected Results

### ✅ Unit Tests (16 tests)
- All should PASS
- Time: ~0.2s
- No external dependencies

### ✅ Integration Tests (14 tests)
- Require Redis connection
- Auto-skip if Redis unavailable
- Time: ~1-2s with Redis

### 🔴 Critical Tests (9 tests)
- **MUST PASS** before deploying
- Verify production Redis works
- Check SSL, authentication, operations
- Time: ~2-3s

## CI/CD Usage

For GitHub Actions / GitLab CI:

```yaml
# Run unit tests only (fast)
- pytest -m unit --cov=app --cov-report=xml

# Run with local Redis for integration
- pytest -m "unit or integration" --cov=app
```

## Test Statistics

**Total Tests**: 38
- Unit: 16 tests
- Integration: 14 tests (inc. 9 critical)
- API: 4 tests

**Coverage**: ~42% (unit tests only)
**Execution Time**: 
- Unit only: ~0.2s
- All tests: ~3-5s (with Redis)

## Common Issues

### Tests skipped?
→ External service (Redis) not available. This is OK for unit tests.

### Import errors?
→ Run: `venv/bin/pip install -r requirements-dev.txt`

### Redis connection refused?
→ Check `.env` file or start local Redis: `make redis-local`

### All tests failing?
→ Recreate venv: `rm -rf venv && python3.13 -m venv venv && venv/bin/pip install -r requirements.txt -r requirements-dev.txt`
