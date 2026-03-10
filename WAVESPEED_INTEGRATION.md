# Интеграция с WaveSpeed Endpoint-ами

Этот документ описывает, как другому сервису интегрироваться с новыми асинхронными endpoint-ами генерации стикеров через WaveSpeed.

## Endpoint-ы

- `POST /stickers/wavespeed/generate` - отправка задачи генерации, получение синтетического `ws_...` file id
- `GET /stickers/wavespeed/{file_id}` - получение готового стикера (`image/webp`) или текущего статуса задачи
- `POST /stickers/wavespeed/save-to-set` - дождаться готовности `ws_...` и сохранить в Telegram sticker set

Пример локового base URL: `http://127.0.0.1:8081`

## Рекомендуемый flow интеграции

1. Отправить задачу через `POST /stickers/wavespeed/generate`
2. Сохранить возвращённый `file_id` (`ws_...`) в своей системе
3. Выполнять polling `GET /stickers/wavespeed/{file_id}` с retry/backoff
4. Если ответ `200`, сохранить/передать байты WebP
5. Если ответ `202`, продолжать polling
6. Если ответ terminal `4xx/5xx` (`404`, `410`, `422`, `424`) - завершить задачу как failed
7. (Опционально) Вызвать `POST /stickers/wavespeed/save-to-set` для автоматического добавления в стикерсет

## Модель запроса: `POST /stickers/wavespeed/generate`

### Обязательные поля

- `prompt: string`
- `model: "flux-schnell" | "nanabanana"`

### Опциональные поля

- `size: string` (по умолчанию: `"512*512"`)
- `seed: int` (по умолчанию: `-1`)
- `num_images: int` (сейчас должен быть `1`)
- `strength: float` (по умолчанию: `0.8`)
- `remove_background: bool` (по умолчанию: `false`)
- `source_image_url: string` (опционально, для img2img/edit)
- `source_image_base64: string` (опционально, для img2img/edit)
- `image: string` (legacy-алиас; для новых интеграций не рекомендуется)

### Выбор режима Nano Banana

Для `model="nanabanana"` режим выбирается автоматически:

- если передан source image (`source_image_url` или `source_image_base64`) -> режим image edit
- если source image не передан -> режим text-to-image

## Модель ответа: `POST /stickers/wavespeed/generate`

Успех (`202 Accepted`):

```json
{
  "file_id": "ws_1e6a2979a4d45754c16f9e97",
  "status": "pending",
  "provider_request_id": "288f54cbd97747d0a9ed993ced8b6a9f"
}
```

Ошибка валидации/провайдера (`400`):

```json
{
  "detail": "..."
}
```

Внутренняя ошибка (`500`):

```json
{
  "detail": "Failed to submit WaveSpeed generation: ..."
}
```

## Поведение ответа: `GET /stickers/wavespeed/{file_id}`

- `200 OK` -> тело ответа это бинарный `image/webp` (совместим с Telegram sticker)
- `202 Accepted` -> задача ещё обрабатывается:
  ```json
  {"file_id":"ws_...","status":"pending"}
  ```
- `400 Bad Request` -> некорректный формат `file_id` (должен начинаться с `ws_`)
- `404 Not Found` -> задача не найдена
- `410 Gone` -> задача просрочена (TTL истёк)
- `422 Unprocessable Entity` -> семантическая ошибка обработки
- `424 Failed Dependency` -> ошибка upstream/post-processing (generation/download/background removal)

Для failed-задач `detail` обычно содержит:

```json
{
  "detail": {
    "code": "generation_failed|download_failed|background_removal_failed|...",
    "message": "человекочитаемая причина"
  }
}
```

## Автосохранение в стикерсет: `POST /stickers/wavespeed/save-to-set`

Endpoint принимает `ws_` `file_id`, ждёт готовности стикера (до `wait_timeout_sec`) и затем:

- если стикерсет уже существует -> добавляет стикер;
- если стикерсета нет -> создаёт новый набор (`name` + `title`) и добавляет первый стикер.
- при необходимости автоматически нормализует `name`: добавляет суффикс `_by_<TELEGRAM_BOT_USERNAME>`.

Поля запроса:

- `file_id: string` (обязательно, `ws_...`)
- `user_id: int` (обязательно, владелец стикерсета в Telegram)
- `name: string` (обязательно, short name стикерсета)
- `title: string` (обязательно, title для создания набора)
- `emoji: string` (опционально, emoji, который привязывается к стикеру; по умолчанию `😀`)
- `wait_timeout_sec: int` (опционально, по умолчанию `60`)

Ответы:

- `200` - стикер успешно сохранён/добавлен в набор
- `202` - генерация ещё не готова в пределах `wait_timeout_sec`
- `404` - `ws_` job не найден
- `410` - `ws_` job истёк
- `422` - неподдерживаемый формат для сохранения (ожидается static `image/webp`)
- `424` - ошибка генерации/post-processing перед сохранением

## Стратегия polling для production

Используйте ограниченные retries с exponential backoff и jitter.

Рекомендуемые значения:

- начальная задержка: `1s`
- множитель: `1.5` или `2.0`
- максимальная задержка: `10s`
- общий timeout budget: `60-120s`

Псевдо-flow:

```text
submit -> получить ws_file_id
loop до дедлайна:
  GET /stickers/wavespeed/{file_id}
  if 200: done
  if 202: wait(backoff+jitter), continue
  if 404/410/422/424: terminal fail
  else: retry по вашей platform policy
```

## Примеры cURL

### 1) flux-schnell text-to-image

```bash
curl -X POST "http://127.0.0.1:8081/stickers/wavespeed/generate" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "gold dragonfly sticker, transparent background",
    "model": "flux-schnell",
    "size": "512*512",
    "seed": -1,
    "num_images": 1,
    "strength": 0.8,
    "remove_background": true
  }'
```

### 2) nanabanana text-to-image

```bash
curl -X POST "http://127.0.0.1:8081/stickers/wavespeed/generate" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "fat gold cat with rick and morty style",
    "model": "nanabanana",
    "remove_background": false
  }'
```

### 3) nanabanana image edit (source URL)

```bash
curl -X POST "http://127.0.0.1:8081/stickers/wavespeed/generate" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Turn this image into telegram sticker style",
    "model": "nanabanana",
    "source_image_url": "https://example.com/input.png",
    "remove_background": true
  }'
```

### 4) polling/скачивание готового стикера

```bash
# Замените ws_xxx на file_id из ответа POST
curl -v "http://127.0.0.1:8081/stickers/wavespeed/ws_xxx" --output sticker.webp
```

### 5) сохранить готовый `ws_` стикер в Telegram set

```bash
curl -X POST "http://127.0.0.1:8081/stickers/wavespeed/save-to-set" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "file_id": "ws_xxx",
    "user_id": 123456789,
    "name": "my_pack_by_your_bot",
    "title": "My Pack",
    "emoji": "😀",
    "wait_timeout_sec": 60
  }'
```

Примечания:

- Если ответ `202`, файл изображения ещё не готов.
- Если ответ `200`, `sticker.webp` готов к использованию в Telegram sticker flow.

## Важные примечания для интеграции

- `file_id` синтетический и namespaced (`ws_...`), это не Telegram `file_id`.
- Финальный результат нормализуется в Telegram-compatible WebP (canvas 512x512 с сохранением пропорций).
- Сгенерированные файлы кешируются; повторные `GET` для готовых задач быстрые.
- В production-клиентах не отправляйте Swagger placeholder-строки вроде `"source_image_url": "string"`.
