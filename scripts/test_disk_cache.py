#!/usr/bin/env python3
"""
Скрипт для тестирования disk cache локально
Использует реальные file_id из production статистики
"""

import asyncio
import aiohttp
import json
import os
import time
from pathlib import Path

# Новые file_id для тестирования disk cache (которых еще нет в кеше)
TEST_FILE_IDS = [
    "CAACAgIAAxUAAWjyeZrtaxJ04nOMzSpUw6Xh1WtKAAI5PgAC1MSQSECuGgLSGbpBNgQ",
    "CAACAgIAAxUAAWjyeaKkg9gZX7rFdsGWoOXXE6h4AAJOAQAClp-MDkjw4Fjn-TUiNgQ",
    "CAACAgIAAxUAAWjyeYrjUjKL7VsVurppVrIxxUfGAAKVAAOvxlEaD5o3KRDg-JQ2BA",
    "CAACAgIAAxUAAWjyeZpIREA2mFuv6iObrsRa1PyXAAJSFQACqYbhSVDx_lQe_fn7NgQ",
    "CAACAgIAAxUAAWjyeamq_4UJPAqAmwTWhrn9zneiAAIrBQACP5XMCr1sVg0qokP6NgQ",
    "CAACAgIAAxUAAWjyeYyh4jekpUMINQiveJRXU3qVAAKQEwACV5bISYXv8C1i2ZPCNgQ",
    "CAACAgIAAxUAAWjyeZ5p-FRN-YhL3lsKHaLWlQfxAAL0EwACNXkAAUrhooHDIvFuNjYE"
]

SERVICE_URL = "http://127.0.0.1:8081"
DISK_CACHE_DIR = "/tmp/sticker_cache"

async def test_disk_cache():
    """Тестирует disk cache локально"""
    print("🧪 ТЕСТИРОВАНИЕ DISK CACHE ЛОКАЛЬНО")
    print("=" * 60)
    
    # Проверяем, что сервис запущен
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{SERVICE_URL}/health") as response:
                if response.status != 200:
                    print("❌ Сервис не запущен или недоступен")
                    return
                print("✅ Сервис запущен и доступен")
    except Exception as e:
        print(f"❌ Ошибка подключения к сервису: {e}")
        return
    
    # Получаем начальную статистику кеша
    print("\n📊 НАЧАЛЬНАЯ СТАТИСТИКА КЕША:")
    initial_stats = await get_cache_stats()
    print_cache_stats(initial_stats)
    
    # Проверяем disk cache директорию
    print(f"\n📁 DISK CACHE ДИРЕКТОРИЯ: {DISK_CACHE_DIR}")
    if os.path.exists(DISK_CACHE_DIR):
        files_count = len([f for f in os.listdir(DISK_CACHE_DIR) if not f.endswith('.meta')])
        print(f"✅ Директория существует, файлов: {files_count}")
    else:
        print("❌ Директория disk cache не существует")
    
    # Запрашиваем файлы
    print(f"\n🔄 ЗАПРАШИВАЕМ {len(TEST_FILE_IDS)} ФАЙЛОВ:")
    print("-" * 60)
    
    successful_requests = 0
    failed_requests = 0
    
    async with aiohttp.ClientSession() as session:
        for i, file_id in enumerate(TEST_FILE_IDS, 1):
            print(f"[{i:2d}/{len(TEST_FILE_IDS)}] Запрашиваем {file_id[:20]}...")
            
            try:
                start_time = time.time()
                async with session.get(f"{SERVICE_URL}/stickers/{file_id}") as response:
                    elapsed = int((time.time() - start_time) * 1000)
                    
                    if response.status == 200:
                        content_length = len(await response.read())
                        print(f"    ✅ Успех: {response.status}, размер: {content_length} байт, время: {elapsed}ms")
                        successful_requests += 1
                    else:
                        print(f"    ❌ Ошибка: {response.status}")
                        failed_requests += 1
                        
            except Exception as e:
                print(f"    ❌ Исключение: {e}")
                failed_requests += 1
            
            # Небольшая пауза между запросами
            await asyncio.sleep(0.5)
    
    print(f"\n📈 РЕЗУЛЬТАТЫ ЗАПРОСОВ:")
    print(f"✅ Успешных: {successful_requests}")
    print(f"❌ Неудачных: {failed_requests}")
    
    # Получаем финальную статистику кеша
    print(f"\n📊 ФИНАЛЬНАЯ СТАТИСТИКА КЕША:")
    final_stats = await get_cache_stats()
    print_cache_stats(final_stats)
    
    # Проверяем disk cache директорию после запросов
    print(f"\n📁 DISK CACHE ДИРЕКТОРИЯ ПОСЛЕ ЗАПРОСОВ:")
    if os.path.exists(DISK_CACHE_DIR):
        files_count = len([f for f in os.listdir(DISK_CACHE_DIR) if not f.endswith('.meta')])
        meta_files_count = len([f for f in os.listdir(DISK_CACHE_DIR) if f.endswith('.meta')])
        print(f"✅ Файлов: {files_count}")
        print(f"✅ Мета-файлов: {meta_files_count}")
        
        # Показываем размер директории
        total_size = sum(os.path.getsize(os.path.join(DISK_CACHE_DIR, f)) 
                        for f in os.listdir(DISK_CACHE_DIR) 
                        if os.path.isfile(os.path.join(DISK_CACHE_DIR, f)))
        print(f"✅ Общий размер: {total_size / 1024 / 1024:.2f} MB")
        
        # Показываем примеры файлов
        if files_count > 0:
            print(f"\n📋 ПРИМЕРЫ ФАЙЛОВ В DISK CACHE:")
            for i, filename in enumerate(os.listdir(DISK_CACHE_DIR)[:5]):
                if not filename.endswith('.meta'):
                    file_path = os.path.join(DISK_CACHE_DIR, filename)
                    file_size = os.path.getsize(file_path)
                    print(f"    {filename}: {file_size} байт")
    else:
        print("❌ Директория disk cache не существует")
    
    # Анализируем изменения в статистике
    print(f"\n📊 АНАЛИЗ ИЗМЕНЕНИЙ:")
    if initial_stats and final_stats:
        redis_hits_diff = final_stats.get('redis_hits', 0) - initial_stats.get('redis_hits', 0)
        disk_hits_diff = final_stats.get('disk_hits', 0) - initial_stats.get('disk_hits', 0)
        telegram_api_diff = final_stats.get('telegram_api_calls', 0) - initial_stats.get('telegram_api_calls', 0)
        
        print(f"🔄 Redis hits: +{redis_hits_diff}")
        print(f"🔄 Disk hits: +{disk_hits_diff}")
        print(f"🔄 Telegram API calls: +{telegram_api_diff}")
        
        if disk_hits_diff > 0:
            print("✅ Disk cache работает! Файлы найдены в disk cache")
        else:
            print("⚠️  Disk cache не используется. Все запросы идут в Telegram API")
    
    print(f"\n🎯 ТЕСТИРОВАНИЕ ЗАВЕРШЕНО!")

async def get_cache_stats():
    """Получает статистику кеша"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{SERVICE_URL}/cache/stats") as response:
                if response.status == 200:
                    return await response.json()
                else:
                    print(f"❌ Ошибка получения статистики: {response.status}")
                    return None
    except Exception as e:
        print(f"❌ Ошибка запроса статистики: {e}")
        return None

def print_cache_stats(stats):
    """Выводит статистику кеша"""
    if not stats:
        print("❌ Статистика недоступна")
        return
    
    print(f"  Redis hits: {stats.get('redis_hits', 0)}")
    print(f"  Redis misses: {stats.get('redis_misses', 0)}")
    print(f"  Disk hits: {stats.get('disk_hits', 0)}")
    print(f"  Disk misses: {stats.get('disk_misses', 0)}")
    print(f"  Telegram API calls: {stats.get('telegram_api_calls', 0)}")
    print(f"  Total requests: {stats.get('total_requests', 0)}")
    
    if 'overall_cache_hit_rate' in stats:
        print(f"  Overall cache hit rate: {stats['overall_cache_hit_rate']:.1f}%")
    
    # Disk cache детали
    if 'disk' in stats:
        disk_stats = stats['disk']
        print(f"  Disk cache files: {disk_stats.get('total_files', 0)}")
        print(f"  Disk cache size: {disk_stats.get('total_size_mb', 0):.2f} MB")

if __name__ == "__main__":
    asyncio.run(test_disk_cache())
