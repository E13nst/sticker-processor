# Руководство по Оптимизации Производительности

## Обзор

Этот документ описывает оптимизации для максимальной параллельной обработки запросов к `/stickers/{file_id}` и эффективной работы с Telegram Bot API.

## Архитектура

### 1. Глобальная Очередь Telegram API

Все запросы к Telegram Bot API проходят через **глобальную очередь** в пределах каждого worker процесса:

- ✅ **Единая очередь на worker** - предотвращает дублирование rate limiting
- ✅ **Адаптивное замедление** - автоматически увеличивает задержку при 429 ошибках
- ✅ **Постепенное ускорение** - уменьшает задержку при успешных запросах

### 2. Многоуровневое Кэширование

**Redis Cache (самый быстрый):**
- In-memory кэш для часто запрашиваемых файлов
- Операции < 10ms для кэш-хитов
- Автоматическое исключение больших файлов (>5MB)

**Disk Cache (средняя скорость):**
- Постоянное хранилище для долгосрочного кэширования
- Операции ~50-200ms для кэш-хитов
- Автоматическая очистка старых файлов

**Telegram API (самый медленный):**
- Используется только при cache miss
- Проходит через очередь с rate limiting
- Автоматическое замедление при 429 ошибках

## Настройки Параллельности

### Gunicorn Workers

```python
# gunicorn.conf.py
workers = multiprocessing.cpu_count() * 2 + 1
worker_connections = 2048  # Максимум параллельных соединений на worker
max_requests = 10000  # Уменьшает overhead от перезапуска workers
```

**Рекомендации:**
- **workers**: `CPU_COUNT * 2 + 1` - оптимальный баланс
- **worker_connections**: `2048` - позволяет обрабатывать много одновременных запросов
- **keepalive**: `30` секунд - лучшее переиспользование соединений

### Telegram API Queue

```env
# config.env.example
TELEGRAM_MAX_CONCURRENT_REQUESTS=2  # На каждый worker
TELEGRAM_REQUEST_DELAY_MS=150        # ~6.6 запросов/секунду на worker
```

**Важно:**
- С 4 workers и 2 concurrent requests на worker = **8 параллельных запросов** к Telegram API
- При 150ms задержке = **~6.6 req/s на worker** = **~26 req/s общий**
- Это безопасный лимит для Telegram Bot API (обычно лимит ~30 req/s)

### HTTP Connection Pool

```python
# app/config.py
http_max_connections = 200           # Всего соединений в пуле
http_max_connections_per_host = 50   # Соединений к Telegram API
```

**Рекомендации:**
- `http_max_connections_per_host` должен быть >= `telegram_max_concurrent_requests * workers`
- Больше соединений = лучшее переиспользование при высокой нагрузке

## Адаптивное Rate Limiting

### Как работает адаптивное замедление:

1. **При получении 429 ошибки:**
   - Увеличивает задержку экспоненциально: `delay = base_delay * 2^consecutive_429`
   - Активирует rate limit на период: `duration = consecutive_429 * 5` секунд (макс 60s)
   - Логирует предупреждение с новыми настройками

2. **При успешных запросах:**
   - Постепенно уменьшает счетчик `consecutive_429`
   - Медленно снижает задержку до базовой (но не ниже)

### Примеры поведения:

```
Базовая задержка: 150ms
├─ 1-я 429 ошибка: 300ms (2x), wait 5s
├─ 2-я 429 ошибка: 600ms (4x), wait 10s
├─ 3-я 429 ошибка: 1200ms (8x), wait 15s
└─ Успешные запросы: постепенное снижение до 150ms
```

## Оптимизация Кэша

### Redis Cache

**Быстрая отдача (цель: < 10ms):**
- ✅ Использует connection pooling
- ✅ Pipeline операции для batch запросов
- ✅ Автоматическое исключение больших файлов (>5MB)
- ✅ TTL для автоматической очистки

**Настройки:**
```env
REDIS_MAX_CONNECTIONS=50
REDIS_SOCKET_KEEPALIVE=true
REDIS_SOCKET_CONNECT_TIMEOUT=5
```

### Disk Cache

**Средняя отдача (цель: < 200ms):**
- ✅ Оптимизированный поиск файлов
- ✅ Async I/O операции
- ✅ Автоматическая очистка старых файлов
- ✅ Кэширование метаданных

**Настройки:**
```env
DISK_CACHE_DIR=/tmp/sticker_cache
DISK_CACHE_MAX_SIZE_MB=1000
DISK_CACHE_TTL_DAYS=30
```

## Мониторинг Производительности

### Ключевые Метрики

1. **Cache Hit Rate:**
   ```
   GET /cache/stats
   ```
   - Цель: > 85% cache hits
   - Redis hits должны быть > 60%
   - Disk hits должны быть > 25%

2. **Время Отклика:**
   - Redis cache: < 10ms
   - Disk cache: < 200ms
   - Telegram API: 500-5000ms (зависит от размера файла)

3. **429 Ошибки:**
   ```bash
   docker logs <container> 2>&1 | grep "Rate limit detected"
   ```
   - Цель: < 1% от всех запросов к Telegram API
   - Если больше - уменьшить `TELEGRAM_MAX_CONCURRENT_REQUESTS`

4. **Параллельность:**
   - Проверяйте количество одновременных запросов
   - Мониторьте использование CPU и памяти

### Логирование

Все медленные операции логируются:

```bash
# Медленные запросы (>5 секунд)
docker logs <container> 2>&1 | grep "Slow request"

# Медленные Telegram API запросы (>10 секунд)
docker logs <container> 2>&1 | grep "Slow Telegram API"

# Rate limiting события
docker logs <container> 2>&1 | grep "Rate limit detected"

# Cache статистика
docker logs <container> 2>&1 | grep "CACHE:"
```

## Рекомендации по Настройке

### Для Высокой Нагрузки

```env
# Увеличить параллельность
WORKERS=8
TELEGRAM_MAX_CONCURRENT_REQUESTS=2  # Всего 16 параллельных запросов
HTTP_MAX_CONNECTIONS=400
HTTP_MAX_CONNECTIONS_PER_HOST=100

# Оптимизировать кэш
REDIS_MAX_CONNECTIONS=100
DISK_CACHE_MAX_SIZE_MB=2000

# Увеличить timeout для медленных запросов
ENDPOINT_TIMEOUT_SEC=45
TELEGRAM_TIMEOUT_SEC=30
```

### Для Низкой Нагрузки

```env
# Экономия ресурсов
WORKERS=2
TELEGRAM_MAX_CONCURRENT_REQUESTS=3  # Всего 6 параллельных запросов
HTTP_MAX_CONNECTIONS=100
HTTP_MAX_CONNECTIONS_PER_HOST=20

# Меньший кэш
REDIS_MAX_CONNECTIONS=25
DISK_CACHE_MAX_SIZE_MB=500
```

## Решение Проблем

### Проблема: Много 429 ошибок

**Решение:**
1. Уменьшить `TELEGRAM_MAX_CONCURRENT_REQUESTS` до 1-2
2. Увеличить `TELEGRAM_REQUEST_DELAY_MS` до 200-300ms
3. Проверить логи на адаптивное замедление

### Проблема: Медленные ответы из кэша

**Решение:**
1. Проверить нагрузку на Redis/Disk
2. Оптимизировать запросы к кэшу (использовать pipeline)
3. Увеличить `REDIS_MAX_CONNECTIONS` при необходимости

### Проблема: Низкий cache hit rate

**Решение:**
1. Увеличить `CACHE_TTL_DAYS`
2. Проверить, что Redis доступен
3. Увеличить `DISK_CACHE_MAX_SIZE_MB`

### Проблема: Высокое использование памяти

**Решение:**
1. Уменьшить `DISK_CACHE_MAX_SIZE_MB`
2. Уменьшить `REDIS_MAX_CONNECTIONS`
3. Уменьшить количество workers

## Тестирование Производительности

### Load Testing

```bash
# Установить Apache Bench или wrk
brew install httpd wrk

# Тест параллельных запросов (100 параллельных, 10000 запросов)
ab -n 10000 -c 100 https://your-service.com/stickers/CAACAgIAAxkBAAIBYGV...
```

### Мониторинг в реальном времени

```bash
# Смотреть логи в реальном времени
docker logs -f <container>

# Мониторинг статистики
watch -n 5 'curl -s http://localhost:8081/cache/stats | jq'
```

## Дополнительные Оптимизации

### Future Improvements

1. **Redis-based global queue** - координация между worker процессами
2. **CDN integration** - кэширование на edge nodes
3. **Pre-warming cache** - предварительная загрузка популярных файлов
4. **Compression** - сжатие больших файлов перед кэшированием

## Связанные Документы

- `GATEWAY_TIMEOUT_FIX.md` - исправление 504 ошибок
- `PERFORMANCE_OPTIMIZATION.md` - общие рекомендации
- `TELEGRAM_QUEUE_SOLUTION.md` - детали реализации очереди

