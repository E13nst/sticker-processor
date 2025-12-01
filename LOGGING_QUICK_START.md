# 📝 Quick Start: Telegram API Logging

## Что добавлено?

Подробное логирование всех взаимодействий с Telegram Bot API для диагностики проблем.

---

## ⚡ Быстрый старт

### 1. Включить логирование

В `.env` файле:
```bash
TELEGRAM_API_DETAILED_LOGGING=true
```

### 2. Посмотреть логи

```bash
# Docker
docker logs -f <container_id>

# Только API запросы
docker logs -f <container_id> 2>&1 | grep -E "Telegram API|✓|✗"

# Только ошибки
docker logs -f <container_id> 2>&1 | grep "✗"
```

### 3. Проверить статистику

```bash
curl http://localhost:8081/api/stats
```

---

## 📊 Что логируется?

### ✅ Успешные запросы
```log
INFO - [getFile-AgADA2QA] ✓ getFile SUCCESS - file_id=AgADA2QA, path=stickers/file.webp, size=12456 bytes, time=145ms
INFO - [download-file.webp] ✓ downloadFile SUCCESS - size=12456 bytes, time=234ms, speed=0.05 MB/s
```

### ❌ Ошибки с деталями
```log
ERROR - [getFile-AgADA2QA] ✗ Telegram API Error - code=400, description=Bad Request: file_id is not valid, time=120ms
ERROR - [download-file.webp] ✗ FILE NOT FOUND (404) - file_path=stickers/file.webp, time=234ms
ERROR - [download-file.webp] ✗ TIMEOUT - timeout=30s, elapsed=30150ms
```

---

## 🔍 Быстрая диагностика

### Проблема: Медленные запросы
```bash
# Найти запросы > 1000ms
docker logs <container> 2>&1 | grep "time=" | grep -E "time=[0-9]{4,}ms"
```

### Проблема: Частые ошибки
```bash
# Посмотреть статистику
curl http://localhost:8081/api/stats | jq '.telegram_api_statistics.errors_by_type'
```

### Проблема: 404 Not Found
```bash
# Найти все 404
docker logs <container> 2>&1 | grep "404"
```

### Проблема: Таймауты
```bash
# Найти таймауты
docker logs <container> 2>&1 | grep "TIMEOUT"

# Решение: увеличить таймаут в .env
TELEGRAM_TIMEOUT_SEC=60
```

---

## 📈 Типичные ошибки

| Ошибка | Причина | Решение |
|--------|---------|---------|
| `HTTP_404_NOT_FOUND` | Файл не существует | Проверить file_id |
| `HTTP_403_FORBIDDEN` | Неверный bot token | Проверить TELEGRAM_BOT_TOKEN |
| `API_ERROR_400` | Невалидный file_id | Проверить формат |
| `TIMEOUT` | Медленный API/сеть | Увеличить TELEGRAM_TIMEOUT_SEC |
| `CLIENT_ERROR_*` | Сетевые проблемы | Проверить соединение |
| `FILE_TOO_LARGE` | Превышен лимит | Увеличить MAX_FILE_SIZE_MB |

---

## 🎯 Режимы логирования

### Development (все детали)
```bash
LOG_LEVEL=DEBUG
TELEGRAM_API_DETAILED_LOGGING=true
```

### Production (только важное)
```bash
LOG_LEVEL=INFO
TELEGRAM_API_DETAILED_LOGGING=false
```

---

## 📋 Итоговая статистика

При остановке сервиса выводится автоматически:

```log
================================================================================
Telegram API Statistics Summary:
  Total Requests: 1543
  Successful: 1489 (96.5%)
  Failed: 54
  Total Downloaded: 245.67 MB
  Average Response Time: 187.3ms
  Errors by Type:
    HTTP_404_NOT_FOUND: 32
    TIMEOUT: 15
================================================================================
```

---

## 🔗 Полная документация

См. `TELEGRAM_API_LOGGING.md` для подробностей.

---

## 💡 Рекомендации

- ✅ Включайте детальное логирование при проблемах
- ✅ Проверяйте `/api/stats` регулярно  
- ✅ Сохраняйте логи при странном поведении
- ⚠️ Отключайте детальное логирование если логи слишком большие

