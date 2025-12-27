# OpenAI Sticker Generation API

## Endpoint

**POST** `/stickers/generate`

Генерирует изображение для Telegram стикера через OpenAI API по текстовому запросу.

## Request

### Headers
```
Content-Type: application/json
```

### Body (JSON)
```json
{
  "prompt": "cute cat with sunglasses",
  "quality": "high",
  "size": "512x512"
}
```

### Parameters

| Параметр | Тип | Обязательный | По умолчанию | Описание |
|----------|-----|---------------|--------------|----------|
| `prompt` | string | ✅ | - | Текстовое описание стикера (1-1000 символов) |
| `quality` | string | ❌ | `"high"` | Качество изображения: `"high"` или `"standard"` |
| `size` | string | ❌ | `"512x512"` | Размер изображения в формате `"WIDTHxHEIGHT"` (256-2048 пикселей) |

### Примеры запросов

**Минимальный запрос:**
```json
{
  "prompt": "happy robot waving"
}
```

**С параметрами:**
```json
{
  "prompt": "cute penguin with scarf",
  "quality": "high",
  "size": "1024x1024"
}
```

## Response

### Success (200 OK)

**Headers:**
- `Content-Type: image/webp`
- `X-Processing-Time-Ms: 1234` - время обработки в миллисекундах
- `X-Image-Size: 45678` - размер изображения в байтах

**Body:** WebP изображение с прозрачным фоном (binary)

### Error Responses

- **400 Bad Request** - неверные параметры (пустой prompt, неверный формат size, неверное значение quality)
- **503 Service Unavailable** - OpenAI API ключ не настроен
- **500 Internal Server Error** - ошибка OpenAI API

## Примеры использования

### cURL
```bash
curl -X POST "http://localhost:8081/stickers/generate" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "cute cat with sunglasses"}' \
  --output sticker.webp
```

### Python (requests)
```python
import requests

response = requests.post(
    "http://localhost:8081/stickers/generate",
    json={
        "prompt": "happy robot waving",
        "quality": "high",
        "size": "512x512"
    }
)

if response.status_code == 200:
    with open("sticker.webp", "wb") as f:
        f.write(response.content)
    print(f"Processing time: {response.headers.get('X-Processing-Time-Ms')}ms")
else:
    print(f"Error: {response.status_code} - {response.text}")
```

### JavaScript (fetch)
```javascript
const response = await fetch('http://localhost:8081/stickers/generate', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    prompt: 'cute penguin with scarf',
    quality: 'high',
    size: '512x512'
  })
});

if (response.ok) {
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  // Использовать blob или сохранить файл
  console.log(`Processing time: ${response.headers.get('X-Processing-Time-Ms')}ms`);
} else {
  console.error(`Error: ${response.status} - ${await response.text()}`);
}
```

## Ограничения

- `prompt`: 1-1000 символов
- `size`: от 256x256 до 2048x2048 пикселей
- `quality`: только `"high"` или `"standard"`
- Формат ответа: всегда WebP с прозрачным фоном

## Примечания

- Эндпоинт требует настройки `OPENAI_API_KEY` в переменных окружения сервиса
- Изображения генерируются через OpenAI API (модель `gpt-image-1`)
- Все изображения возвращаются в формате WebP с прозрачным фоном, оптимизированном для Telegram стикеров



