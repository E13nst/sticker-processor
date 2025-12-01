#!/usr/bin/env python3
"""
Test script for Sticker Processor Service
"""

import requests
import json
import sys

BASE_URL = "http://localhost:8081"

def test_health():
    """Test health endpoint."""
    print("🔍 Testing health endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            print("✅ Health check passed")
            print(f"   Response: {response.json()}")
        else:
            print(f"❌ Health check failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Health check error: {e}")

def test_formats():
    """Test formats endpoint."""
    print("\n🔍 Testing formats endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/formats")
        if response.status_code == 200:
            print("✅ Formats endpoint working")
            print(f"   Supported formats: {json.dumps(response.json(), indent=2)}")
        else:
            print(f"❌ Formats endpoint failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Formats endpoint error: {e}")

def test_sticker(file_id):
    """Test sticker endpoint."""
    print(f"\n🔍 Testing sticker endpoint with file_id: {file_id}")
    try:
        response = requests.get(f"{BASE_URL}/stickers/{file_id}")
        
        print(f"   Status: {response.status_code}")
        print(f"   Headers:")
        for key, value in response.headers.items():
            if key.startswith('X-'):
                print(f"     {key}: {value}")
        
        if response.status_code == 200:
            print("✅ Sticker endpoint working")
            print(f"   Content-Type: {response.headers.get('Content-Type')}")
            print(f"   Content-Length: {len(response.content)} bytes")
        else:
            print(f"❌ Sticker endpoint failed: {response.status_code}")
            print(f"   Response: {response.text}")
    except Exception as e:
        print(f"❌ Sticker endpoint error: {e}")

def test_cache_stats():
    """Test cache stats endpoint."""
    print("\n🔍 Testing cache stats endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/cache/stats")
        if response.status_code == 200:
            print("✅ Cache stats endpoint working")
            print(f"   Stats: {json.dumps(response.json(), indent=2)}")
        else:
            print(f"❌ Cache stats endpoint failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Cache stats endpoint error: {e}")

def main():
    """Run all tests."""
    print("🧪 Sticker Processor Service Test Suite")
    print("=" * 50)
    
    # Test basic endpoints
    test_health()
    test_formats()
    test_cache_stats()
    
    # Test sticker endpoint if file_id provided
    if len(sys.argv) > 1:
        file_id = sys.argv[1]
        test_sticker(file_id)
    else:
        print("\n💡 To test sticker endpoint, provide a file_id:")
        print("   python test.py CAACAgIAAxUAAWjHy8-7nswFB8-VN4L9rSQKzXhOAAJIdwACDCH4SPHcLlCb9Eb9NgQ")
    
    print("\n🎯 Test completed!")
    print(f"📖 Swagger UI: {BASE_URL}/docs")

if __name__ == "__main__":
    main()
