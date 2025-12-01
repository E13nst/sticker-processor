#!/usr/bin/env python3
"""
Test script to verify disk cache functionality with Redis disabled.

This script:
1. Starts the service locally with Redis disabled
2. Makes requests for test file IDs (first pass - should hit Telegram API)
3. Makes the same requests again (second pass - should hit disk cache)
4. Collects and displays statistics to verify disk cache is working

Usage:
    REDIS_ENABLED=false venv/bin/python3.13 test_disk_cache_stats.py
"""

import asyncio
import subprocess
import time
import sys
import os
from pathlib import Path
import httpx
import json
from datetime import datetime


# Configuration
SERVICE_URL = "http://127.0.0.1:8081"
STATS_URL = f"{SERVICE_URL}/cache/stats"
TEST_FILE_IDS_PATH = "test_file_ids.txt"
START_SERVICE = False  # Set to False if service is already running


class Colors:
    """ANSI color codes for terminal output."""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_header(text):
    """Print colored header."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}\n")


def print_success(text):
    """Print success message."""
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")


def print_error(text):
    """Print error message."""
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")


def print_info(text):
    """Print info message."""
    print(f"{Colors.OKCYAN}ℹ {text}{Colors.ENDC}")


def print_warning(text):
    """Print warning message."""
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")


def load_test_file_ids():
    """Load test file IDs from file."""
    if not Path(TEST_FILE_IDS_PATH).exists():
        print_error(f"Test file not found: {TEST_FILE_IDS_PATH}")
        sys.exit(1)
    
    with open(TEST_FILE_IDS_PATH, 'r') as f:
        file_ids = [line.strip() for line in f if line.strip()]
    
    print_info(f"Loaded {len(file_ids)} test file IDs")
    return file_ids


async def get_stats():
    """Get cache statistics from service."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(STATS_URL)
            if response.status_code == 200:
                return response.json()
            else:
                print_error(f"Failed to get stats: HTTP {response.status_code}")
                return None
        except Exception as e:
            print_error(f"Failed to get stats: {e}")
            return None


async def fetch_sticker(client, file_id):
    """Fetch a single sticker."""
    url = f"{SERVICE_URL}/stickers/{file_id}"
    try:
        response = await client.get(url)
        return {
            'file_id': file_id,
            'status': response.status_code,
            'size': len(response.content) if response.status_code == 200 else 0,
            'success': response.status_code == 200
        }
    except Exception as e:
        return {
            'file_id': file_id,
            'status': 0,
            'size': 0,
            'success': False,
            'error': str(e)
        }


async def fetch_all_stickers(file_ids, pass_name):
    """Fetch all stickers and collect results."""
    print_header(f"Pass {pass_name}: Fetching {len(file_ids)} stickers")
    
    results = []
    success_count = 0
    failed_count = 0
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, file_id in enumerate(file_ids, 1):
            result = await fetch_sticker(client, file_id)
            results.append(result)
            
            if result['success']:
                success_count += 1
                print(f"  [{i}/{len(file_ids)}] ✓ {file_id[:20]}... ({result['size']} bytes)")
            else:
                failed_count += 1
                error_msg = result.get('error', f"HTTP {result['status']}")
                print(f"  [{i}/{len(file_ids)}] ✗ {file_id[:20]}... ({error_msg})")
            
            # Small delay to avoid overwhelming the service
            await asyncio.sleep(0.1)
    
    print(f"\n{Colors.BOLD}Results:{Colors.ENDC}")
    print_success(f"Successful: {success_count}/{len(file_ids)}")
    if failed_count > 0:
        print_error(f"Failed: {failed_count}/{len(file_ids)}")
    
    return results


def print_stats_comparison(stats_before, stats_after):
    """Print statistics comparison."""
    print_header("Statistics Comparison")
    
    # Disk cache stats
    disk_before = stats_before.get('disk', {})
    disk_after = stats_after.get('disk', {})
    
    print(f"{Colors.BOLD}Disk Cache:{Colors.ENDC}")
    print(f"  Total Files:     {disk_before.get('total_files', 0)} → {disk_after.get('total_files', 0)} "
          f"(+{disk_after.get('total_files', 0) - disk_before.get('total_files', 0)})")
    print(f"  Cache Hits:      {disk_before.get('cache_hits', 0)} → {disk_after.get('cache_hits', 0)} "
          f"(+{disk_after.get('cache_hits', 0) - disk_before.get('cache_hits', 0)})")
    print(f"  Cache Misses:    {disk_before.get('cache_misses', 0)} → {disk_after.get('cache_misses', 0)} "
          f"(+{disk_after.get('cache_misses', 0) - disk_before.get('cache_misses', 0)})")
    print(f"  Hit Rate:        {disk_before.get('cache_hit_rate', 0):.1f}% → {disk_after.get('cache_hit_rate', 0):.1f}%")
    print(f"  Files Created:   {disk_before.get('files_created', 0)} → {disk_after.get('files_created', 0)} "
          f"(+{disk_after.get('files_created', 0) - disk_before.get('files_created', 0)})")
    print(f"  Size (MB):       {disk_before.get('total_size_mb', 0):.2f} → {disk_after.get('total_size_mb', 0):.2f}")
    
    # Overall stats
    print(f"\n{Colors.BOLD}Overall Cache Manager:{Colors.ENDC}")
    print(f"  Disk Hits:       {stats_before.get('disk_hits', 0)} → {stats_after.get('disk_hits', 0)} "
          f"(+{stats_after.get('disk_hits', 0) - stats_before.get('disk_hits', 0)})")
    print(f"  Disk Misses:     {stats_before.get('disk_misses', 0)} → {stats_after.get('disk_misses', 0)} "
          f"(+{stats_after.get('disk_misses', 0) - stats_before.get('disk_misses', 0)})")
    print(f"  Telegram Calls:  {stats_before.get('telegram_api_calls', 0)} → {stats_after.get('telegram_api_calls', 0)} "
          f"(+{stats_after.get('telegram_api_calls', 0) - stats_before.get('telegram_api_calls', 0)})")
    print(f"  Conversions:     {stats_before.get('conversions_performed', 0)} → {stats_after.get('conversions_performed', 0)} "
          f"(+{stats_after.get('conversions_performed', 0) - stats_before.get('conversions_performed', 0)})")
    
    # Redis check
    redis_status = stats_after.get('redis', {})
    if redis_status.get('available'):
        print_warning("Redis is ENABLED - this may affect disk cache test results!")
    else:
        print_success("Redis is DISABLED - disk cache test is valid")


async def wait_for_service(max_attempts=30):
    """Wait for service to be ready."""
    print_info("Waiting for service to start...")
    
    async with httpx.AsyncClient() as client:
        for attempt in range(max_attempts):
            try:
                response = await client.get(f"{SERVICE_URL}/health", timeout=2.0)
                if response.status_code == 200:
                    print_success("Service is ready!")
                    return True
            except:
                pass
            
            await asyncio.sleep(1)
            print(f"  Attempt {attempt + 1}/{max_attempts}...", end='\r')
    
    print_error("Service failed to start")
    return False


async def main():
    """Main test function."""
    print_header("Disk Cache Test with Redis Disabled")
    
    # Check if Redis is disabled
    redis_enabled = os.getenv('REDIS_ENABLED', 'true').lower()
    if redis_enabled != 'false':
        print_error("REDIS_ENABLED is not set to 'false'")
        print_info("Please run with: REDIS_ENABLED=false venv/bin/python3.13 test_disk_cache_stats.py")
        sys.exit(1)
    
    print_success("REDIS_ENABLED=false confirmed")
    
    # Load test file IDs
    file_ids = load_test_file_ids()
    
    # Start service if needed
    service_process = None
    if START_SERVICE:
        print_info("Starting service locally...")
        # Use separate test cache directory to avoid mixing with production
        test_cache_dir = "/tmp/sticker_cache_test"
        os.makedirs(test_cache_dir, exist_ok=True)
        print_info(f"Using test cache directory: {test_cache_dir}")
        
        service_process = subprocess.Popen(
            ["venv/bin/python3.13", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8081"],
            env={**os.environ, 'REDIS_ENABLED': 'false', 'DISK_CACHE_DIR': test_cache_dir},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Wait for service to be ready
        if not await wait_for_service():
            if service_process:
                service_process.terminate()
            sys.exit(1)
    
    try:
        # Get initial stats
        print_info("Getting initial statistics...")
        stats_initial = await get_stats()
        if not stats_initial:
            print_error("Failed to get initial stats")
            return
        
        print(f"Initial disk cache files: {stats_initial.get('disk', {}).get('total_files', 0)}")
        print(f"Initial disk cache hits: {stats_initial.get('disk', {}).get('cache_hits', 0)}")
        
        # First pass - should fetch from Telegram and cache to disk
        results_pass1 = await fetch_all_stickers(file_ids, "1 (Cache MISS expected)")
        stats_after_pass1 = await get_stats()
        
        # Wait a bit before second pass
        print_info("Waiting 2 seconds before second pass...")
        await asyncio.sleep(2)
        
        # Second pass - should fetch from disk cache
        results_pass2 = await fetch_all_stickers(file_ids, "2 (Cache HIT expected)")
        stats_after_pass2 = await get_stats()
        
        # Print comparison
        print_stats_comparison(stats_initial, stats_after_pass2)
        
        # Analyze results
        print_header("Analysis")
        
        disk_hits_increase = stats_after_pass2.get('disk_hits', 0) - stats_initial.get('disk_hits', 0)
        telegram_calls_increase = stats_after_pass2.get('telegram_api_calls', 0) - stats_initial.get('telegram_api_calls', 0)
        
        success_pass1 = sum(1 for r in results_pass1 if r['success'])
        success_pass2 = sum(1 for r in results_pass2 if r['success'])
        
        print(f"Pass 1 successful requests: {success_pass1}/{len(file_ids)}")
        print(f"Pass 2 successful requests: {success_pass2}/{len(file_ids)}")
        print(f"Disk cache hits gained: {disk_hits_increase}")
        print(f"Telegram API calls made: {telegram_calls_increase}")
        
        # Verdict
        print_header("Verdict")
        
        if disk_hits_increase >= success_pass2 * 0.8:  # At least 80% hit rate
            print_success(f"PASS: Disk cache is working! {disk_hits_increase} hits gained")
        else:
            print_error(f"FAIL: Disk cache hit rate is too low! Only {disk_hits_increase} hits vs {success_pass2} requests")
            print_warning("Possible issues:")
            print("  - Disk cache may not be storing files correctly")
            print("  - File ID format mismatch")
            print("  - Cache lookup logic issue")
        
        if telegram_calls_increase <= success_pass1:
            print_success(f"PASS: Telegram API was called only on first pass ({telegram_calls_increase} calls)")
        else:
            print_warning(f"WARNING: Telegram API called more than expected ({telegram_calls_increase} calls)")
    
    finally:
        # Stop service if we started it
        if service_process:
            print_info("Stopping service...")
            service_process.terminate()
            service_process.wait(timeout=5)
            print_success("Service stopped")


if __name__ == "__main__":
    asyncio.run(main())

