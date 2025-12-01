# Performance Optimization Guide

## Оптимизации сервиса для обработки большего количества HTTP-запросов

Этот документ описывает все оптимизации, внесенные в сервис для значительного улучшения производительности и пропускной способности.

---

## 📊 Основные улучшения

### 1. **Multiple Worker Processes (Gunicorn + Uvicorn)**
- **До**: Один процесс uvicorn
- **После**: 4 worker-процесса (настраивается через `WORKERS`)
- **Выигрыш**: ~4x увеличение пропускной способности

#### Конфигурация:
```bash
# В Dockerfile
gunicorn app.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker
```

#### Запуск:
```bash
# Development (1 worker с auto-reload)
./run.sh dev

# Production (multiple workers)
./run.sh prod
```

---

### 2. **Connection Pooling**

#### Redis Connection Pool
- **Максимум соединений**: 50 (настраивается)
- **Keep-alive**: Включен
- **Health checks**: Каждые 30 секунд
- **Retry on timeout**: Включен

```python
# Конфигурация в config.py
REDIS_MAX_CONNECTIONS=50
REDIS_SOCKET_KEEPALIVE=true
REDIS_SOCKET_CONNECT_TIMEOUT=5
```

#### HTTP Connection Pool (aiohttp)
- **Максимум соединений**: 100 (настраивается)
- **На хост**: 30 (настраивается)
- **DNS cache TTL**: 300 секунд
- **Keepalive timeout**: 30 секунд

```python
# Конфигурация в config.py
HTTP_MAX_CONNECTIONS=100
HTTP_MAX_CONNECTIONS_PER_HOST=30
```

**Выигрыш**: Значительно снижена латентность за счет переиспользования соединений

---

### 3. **CPU-Intensive Tasks в ProcessPoolExecutor**

TGS конвертация (gzip декомпрессия) теперь выполняется в отдельных процессах, не блокируя event loop.

```python
# До: блокировала event loop
decompressed = gzip.decompress(tgs_content)

# После: выполняется в отдельном процессе
result = await loop.run_in_executor(
    self.process_pool,
    self._convert_gzip_sync,
    tgs_content
)
```

**Конфигурация**:
```bash
MAX_PROCESS_WORKERS=2  # Количество процессов для CPU-intensive задач
```

**Выигрыш**: Event loop остается свободным для обработки других запросов

---

### 4. **Rate Limiting Middleware**

Защита от перегрузки и DDoS-атак с помощью rate limiting.

```python
# Конфигурация
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=100      # Запросов
RATE_LIMIT_WINDOW_SEC=60     # За период (секунды)
```

**Возможности**:
- Лимит на IP-адрес
- Поддержка X-Forwarded-For (для reverse proxy)
- Автоматическая очистка старых записей
- HTTP 429 ответ при превышении лимита
- Заголовки с информацией о лимитах

**Выигрыш**: Защита от перегрузки, стабильная работа под нагрузкой

---

### 5. **Оптимизация Redis**

#### Конфигурация в docker-compose.yml:
```yaml
redis:
  command: >
    redis-server
    --maxmemory 512mb
    --maxmemory-policy allkeys-lru
    --save 60 1000
    --appendonly yes
    --tcp-keepalive 60
    --timeout 300
```

**Функции**:
- LRU eviction policy (автоматическое удаление старых данных)
- AOF persistence (сохранение данных на диск)
- TCP keepalive для надежности соединений

---

### 6. **Gunicorn Configuration**

Оптимальные настройки для production:
```python
workers = 4                          # Worker-процессы
worker_connections = 1000            # Соединений на worker
max_requests = 1000                  # Перезапуск worker после N запросов
max_requests_jitter = 100            # Случайный jitter для равномерной перезагрузки
timeout = 120                        # Таймаут запроса
keepalive = 5                        # HTTP keepalive
```

---

### 7. **Resource Limits в Docker**

Конфигурация ресурсов для предсказуемой производительности:

```yaml
sticker-processor:
  deploy:
    resources:
      limits:
        cpus: '2.0'
        memory: 2G
      reservations:
        cpus: '1.0'
        memory: 512M

redis:
  deploy:
    resources:
      limits:
        cpus: '1.0'
        memory: 768M
      reservations:
        cpus: '0.5'
        memory: 256M
```

---

## 🚀 Ожидаемые улучшения производительности

| Метрика | До | После | Улучшение |
|---------|-----|-------|-----------|
| **Пропускная способность (RPS)** | ~50 | ~200-300 | **4-6x** |
| **Латентность (cached)** | 10-20ms | 5-10ms | **2x** |
| **Латентность (uncached)** | 200-500ms | 100-300ms | **1.5-2x** |
| **Concurrent requests** | ~10 | ~100+ | **10x+** |
| **CPU utilization** | 25% (1 core) | 80-90% (multi-core) | **Эффективнее** |

---

## 📝 Настройка для разных нагрузок

### Низкая нагрузка (<100 RPS)
```bash
WORKERS=2
MAX_PROCESS_WORKERS=1
REDIS_MAX_CONNECTIONS=20
HTTP_MAX_CONNECTIONS=50
```

### Средняя нагрузка (100-500 RPS)
```bash
WORKERS=4
MAX_PROCESS_WORKERS=2
REDIS_MAX_CONNECTIONS=50
HTTP_MAX_CONNECTIONS=100
```

### Высокая нагрузка (>500 RPS)
```bash
WORKERS=8
MAX_PROCESS_WORKERS=4
REDIS_MAX_CONNECTIONS=100
HTTP_MAX_CONNECTIONS=200
HTTP_MAX_CONNECTIONS_PER_HOST=50
```

---

## 🔧 Мониторинг и метрики

### Health Check
```bash
curl http://localhost:8081/health
```

### Cache Statistics
```bash
curl http://localhost:8081/cache/stats
```

### Rate Limit Headers
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Window: 60
```

### Response Headers
```
X-Cache-Status: HIT/MISS
X-Conversion-Time-Ms: 150
X-Original-Format: tgs
X-Output-Format: lottie
```

---

## 🐳 Запуск

### Development
```bash
# С auto-reload
./run.sh dev

# Или напрямую
uvicorn app.main:app --reload
```

### Production
```bash
# Локально
./run.sh prod

# Docker Compose
docker-compose up -d

# Docker с масштабированием
docker-compose up -d --scale sticker-processor=3
```

---

## 📊 Load Testing

### Простой тест с Apache Bench
```bash
# 1000 запросов, 10 одновременных
ab -n 1000 -c 10 http://localhost:8081/health
```

### Более продвинутый тест с wrk
```bash
# 10 секунд, 10 потоков, 100 соединений
wrk -t10 -c100 -d10s http://localhost:8081/stickers/YOUR_FILE_ID
```

### Тест с Locust (Python)
```python
from locust import HttpUser, task, between

class StickerUser(HttpUser):
    wait_time = between(0.1, 0.5)
    
    @task
    def get_sticker(self):
        self.client.get("/stickers/YOUR_FILE_ID")
```

---

## ⚡ Best Practices

1. **Используйте кэширование**: Redis кэш значительно ускоряет повторные запросы
2. **Настройте rate limiting**: Защищает от злоупотреблений
3. **Мониторьте ресурсы**: Используйте `docker stats` для отслеживания использования
4. **Настройте логирование**: Уровень INFO для production, DEBUG для разработки
5. **Используйте reverse proxy**: Nginx/Traefik перед сервисом для SSL и балансировки

---

## 🔍 Troubleshooting

### Высокая латентность
- Проверьте кэш Redis (должен быть HIT rate >80%)
- Увеличьте количество workers
- Проверьте сетевое соединение с Telegram API

### Ошибки соединения
- Увеличьте connection pool limits
- Проверьте Redis connectivity
- Увеличьте timeout настройки

### Высокое использование памяти
- Уменьшите количество workers
- Уменьшите Redis max_connections
- Настройте Redis eviction policy

### CPU близко к 100%
- Это нормально при высокой нагрузке
- Если постоянно - добавьте больше workers или масштабируйте горизонтально

---

## 📈 Дальнейшие улучшения

1. **Horizontal Scaling**: Несколько инстансов сервиса за load balancer
2. **Redis Cluster**: Для высоких нагрузок и HA
3. **CDN**: Для статического контента (если применимо)
4. **Database Connection Pool**: Если добавите PostgreSQL/MySQL
5. **Metrics & Monitoring**: Prometheus + Grafana
6. **Distributed Tracing**: OpenTelemetry/Jaeger
7. **Auto-scaling**: Kubernetes HPA

---

## 💡 Ключевые выводы

✅ **Multiple workers** - самое важное улучшение для пропускной способности  
✅ **Connection pooling** - критично для низкой латентности  
✅ **ProcessPoolExecutor** - важно для CPU-интенсивных задач  
✅ **Rate limiting** - необходимо для защиты от перегрузок  
✅ **Мониторинг** - обязательно для понимания поведения под нагрузкой  

---

## 📚 Полезные ссылки

- [Gunicorn Settings](https://docs.gunicorn.org/en/stable/settings.html)
- [Uvicorn Deployment](https://www.uvicorn.org/deployment/)
- [FastAPI Performance](https://fastapi.tiangolo.com/deployment/concepts/)
- [Redis Configuration](https://redis.io/docs/manual/config/)
- [aiohttp Best Practices](https://docs.aiohttp.org/en/stable/client_advanced.html)

