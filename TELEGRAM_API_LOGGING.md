# Telegram API Logging Guide

## 📋 Обзор

Добавлено подробное логирование всех взаимодействий с Telegram Bot API для лучшей диагностики проблем и мониторинга производительности.

---

## ✨ Новые возможности

### 1. **Детальное логирование каждого запроса**
- ✅ Уникальный request ID для отслеживания
- ✅ Время выполнения каждого запроса (в миллисекундах)
- ✅ HTTP статус коды и заголовки
- ✅ Размеры файлов и скорость скачивания
- ✅ Коды ошибок Telegram API с описаниями

### 2. **Классификация ошибок**
- HTTP ошибки (404, 403, 500 и т.д.)
- Ошибки Telegram API (с кодами)
- Таймауты
- Client errors (сетевые проблемы)
- Неожиданные ошибки

### 3. **Статистика API использования**
- Общее количество запросов
- Успешные/неудачные запросы
- Success rate (процент успешных)
- Объем скачанных данных (MB)
- Среднее время ответа
- Ошибки по типам

---

## 🔧 Конфигурация

### Включить/выключить детальное логирование

В `.env` файле:

```bash
# Включить детальное логирование (рекомендуется для development и troubleshooting)
TELEGRAM_API_DETAILED_LOGGING=true

# Отключить (для production, если логи слишком объемные)
TELEGRAM_API_DETAILED_LOGGING=false
```

**Примечание**: Даже с `false` критичные ошибки будут логироваться.

---

## 📊 Формат логов

### Успешный запрос (getFile)

```log
INFO - [getFile-AgADA2QA] Telegram API Request: getFile
DEBUG - [getFile-AgADA2QA] URL: https://api.telegram.org/bot****/getFile
DEBUG - [getFile-AgADA2QA] Params: file_id=AgADA2QAAg
DEBUG - [getFile-AgADA2QA] Response Status: 200
DEBUG - [getFile-AgADA2QA] Response Time: 145ms
INFO - [getFile-AgADA2QA] ✓ getFile SUCCESS - file_id=AgADA2QAAg, path=stickers/file_0.webp, size=12456 bytes, time=145ms
```

### Успешная загрузка файла

```log
INFO - [download-file_0.webp] Telegram API Request: downloadFile
DEBUG - [download-file_0.webp] URL: https://api.telegram.org/file/bot****/stickers/file_0.webp
DEBUG - [download-file_0.webp] Response Status: 200
DEBUG - [download-file_0.webp] Content-Type: image/webp
DEBUG - [download-file_0.webp] Content-Length: 12456 bytes
INFO - [download-file_0.webp] ✓ downloadFile SUCCESS - size=12456 bytes, time=234ms, speed=0.05 MB/s, file_path=stickers/file_0.webp
```

### Ошибка Telegram API

```log
ERROR - [getFile-AgADA2QA] ✗ Telegram API Error - code=400, description=Bad Request: file_id is not valid, file_id=AgADA2QAAg, time=120ms
ERROR - Telegram API error for AgADA2QAAg: [400] Bad Request: file_id is not valid
```

### HTTP ошибка 404

```log
ERROR - [download-file_0.webp] ✗ FILE NOT FOUND (404) - file_path=stickers/file_0.webp, time=234ms
ERROR - File not found on Telegram servers: stickers/file_0.webp
```

### Таймаут

```log
ERROR - [download-file_0.webp] ✗ TIMEOUT - file_path=stickers/file_0.webp, timeout=30s, elapsed=30150ms
ERROR - Timeout downloading file stickers/file_0.webp after 30150ms
```

### Client Error (сетевые проблемы)

```log
ERROR - [getFile-AgADA2QA] ✗ CLIENT ERROR - type=ClientConnectionError, error=Cannot connect to host api.telegram.org, file_id=AgADA2QAAg, time=5050ms
ERROR - Client error getting file info for AgADA2QAAg: ClientConnectionError - Cannot connect to host api.telegram.org
```

---

## 📈 API Статистика

### В конце работы (shutdown)

Автоматически выводится итоговая статистика:

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
    API_ERROR_400: 5
    CLIENT_ERROR_ClientConnectionError: 2
================================================================================
```

### Через API endpoint

```bash
curl http://localhost:8081/api/stats
```

**Ответ:**
```json
{
  "telegram_api_statistics": {
    "total_requests": 1543,
    "successful_requests": 1489,
    "failed_requests": 54,
    "success_rate_percent": 96.5,
    "total_downloaded_mb": 245.67,
    "average_response_time_ms": 187.3,
    "errors_by_type": {
      "HTTP_404_NOT_FOUND": 32,
      "TIMEOUT": 15,
      "API_ERROR_400": 5,
      "CLIENT_ERROR_ClientConnectionError": 2
    }
  }
}
```

---

## 🔍 Отслеживание конкретного запроса

Каждый запрос имеет уникальный `request_id` в формате:

- **getFile**: `getFile-{first_8_chars_of_file_id}`
- **downloadFile**: `download-{first_12_chars_of_filename}`

Вы можете grep логи по этому ID:

```bash
# Найти все логи для конкретного file_id
docker logs <container> 2>&1 | grep "getFile-AgADA2QA"

# Найти все логи для конкретного файла
docker logs <container> 2>&1 | grep "download-file_0.webp"
```

---

## 🎯 Использование логов для диагностики

### Проблема: Медленная загрузка стикеров

```bash
# Найти все запросы с временем > 1000ms
docker logs <container> 2>&1 | grep "time=" | awk -F'time=' '{print $2}' | awk '{print $1}' | sort -n
```

### Проблема: Частые ошибки

```bash
# Посмотреть статистику ошибок
curl http://localhost:8081/api/stats | jq '.telegram_api_statistics.errors_by_type'
```

### Проблема: Файлы не найдены

```bash
# Найти все 404 ошибки
docker logs <container> 2>&1 | grep "FILE NOT FOUND"
```

### Проблема: Проблемы с сетью

```bash
# Найти все таймауты и client errors
docker logs <container> 2>&1 | grep -E "TIMEOUT|CLIENT ERROR"
```

---

## 🚨 Типы ошибок и их причины

### `HTTP_404_NOT_FOUND`
**Причина**: Файл не существует на серверах Telegram (истек, удален или никогда не существовал)
**Решение**: Проверить корректность file_id, возможно файл устарел

### `HTTP_403_FORBIDDEN`
**Причина**: Недостаточно прав для доступа (проблема с bot token)
**Решение**: Проверить TELEGRAM_BOT_TOKEN в .env

### `API_ERROR_400`
**Причина**: Невалидный file_id или параметры запроса
**Решение**: Проверить формат file_id

### `TIMEOUT`
**Причина**: Telegram API не ответил в течение `TELEGRAM_TIMEOUT_SEC`
**Решение**: 
- Увеличить `TELEGRAM_TIMEOUT_SEC` в .env
- Проверить сетевое соединение
- Возможно, Telegram API перегружен

### `CLIENT_ERROR_*`
**Причина**: Сетевые проблемы (DNS, connection refused, etc.)
**Решение**:
- Проверить интернет соединение
- Проверить DNS разрешение api.telegram.org
- Проверить firewall/proxy настройки

### `FILE_TOO_LARGE`
**Причина**: Файл превышает `MAX_FILE_SIZE_MB`
**Решение**: Увеличить лимит в .env или отклонить запрос

---

## ⚙️ Настройка уровня логирования

### Development (максимально подробно)

```bash
LOG_LEVEL=DEBUG
TELEGRAM_API_DETAILED_LOGGING=true
```

Покажет:
- Все запросы с параметрами
- Все ответы с заголовками
- Response bodies для ошибок
- Подробные stack traces

### Production (умеренно)

```bash
LOG_LEVEL=INFO
TELEGRAM_API_DETAILED_LOGGING=true
```

Покажет:
- Успешные запросы (краткая информация)
- Все ошибки с деталями
- Статистику

### Production (минимально)

```bash
LOG_LEVEL=INFO
TELEGRAM_API_DETAILED_LOGGING=false
```

Покажет:
- Только ошибки
- Критичные проблемы
- Финальную статистику при shutdown

---

## 📝 Примеры использования

### Мониторинг в реальном времени

```bash
# Следить за всеми API запросами
docker logs -f <container> 2>&1 | grep -E "Telegram API|✓|✗"

# Только ошибки
docker logs -f <container> 2>&1 | grep "✗"

# Только успешные
docker logs -f <container> 2>&1 | grep "✓"
```

### Анализ производительности

```bash
# Средняя скорость загрузки
docker logs <container> 2>&1 | grep "speed=" | awk -F'speed=' '{print $2}' | awk '{print $1}' | awk '{s+=$1; c++} END {print s/c " MB/s"}'

# Самые медленные запросы
docker logs <container> 2>&1 | grep "time=" | sort -t'=' -k2 -n | tail -10
```

### Сохранение логов для анализа

```bash
# Сохранить последние 1000 строк
docker logs <container> 2>&1 | tail -1000 > telegram_api_logs.txt

# Сохранить только API логи
docker logs <container> 2>&1 | grep -E "Telegram API|✓|✗" > telegram_api_requests.txt
```

---

## 🎨 Легенда символов

- ✓ - Успешный запрос
- ✗ - Ошибка
- ⚠ - Предупреждение (например, файл слишком большой)

---

## 💡 Советы

1. **Используйте детальное логирование в development** - это поможет быстро найти проблемы
2. **Отключите детальное логирование в production** - если объем логов становится проблемой
3. **Регулярно проверяйте `/api/stats`** - чтобы отслеживать health API
4. **Настройте алерты** на высокий процент ошибок (> 5%)
5. **Используйте request_id** для отслеживания проблемных запросов

---

## 🔗 Связанные endpoints

- `GET /health` - Health check сервиса
- `GET /api/stats` - Статистика Telegram API
- `GET /cache/stats` - Статистика кэша

---

## 📚 См. также

- `PERFORMANCE_OPTIMIZATION.md` - Общая оптимизация сервиса
- `config.env.example` - Все доступные параметры конфигурации
- [Telegram Bot API Documentation](https://core.telegram.org/bots/api)

