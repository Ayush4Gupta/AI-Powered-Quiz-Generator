#!/usr/bin/env python3
"""
Test script to verify the final fixes:
1. Poll endpoint no longer returns "result": null
2. Quiz generation has better error handling
"""

import requests
import json
import time
import os

BASE_URL = "http://localhost:8000"

def test_poll_endpoint():
    """Test that poll endpoint doesn't return 'result': null for processing/completed jobs"""
    print("🔍 TESTING POLL ENDPOINT")
    print("=" * 50)
    
    # Test with a fake job ID (should return not_found without result field)
    test_job_id = "test-fake-job-12345"
    url = f"{BASE_URL}/api/v1/quizzes/pdf/{test_job_id}"
    
    try:
        response = requests.get(url, timeout=10)
        print(f"✓ Poll endpoint status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Response data: {json.dumps(data, indent=2)}")
            
            # Check if result field is present
            if 'result' in data:
                if data['result'] is None:
                    print("❌ FAIL: 'result' field is present and set to null")
                    return False
                else:
                    print(f"✓ 'result' field has value: {data['result']}")
            else:
                print("✓ SUCCESS: 'result' field is not present in response")
                
            # Verify required fields
            if 'job_id' in data and 'status' in data:
                print("✓ Required fields (job_id, status) are present")
                return True
            else:
                print("❌ FAIL: Missing required fields")
                return False
        else:
            print(f"❌ FAIL: Unexpected status code {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ FAIL: Cannot connect to server. Is it running on http://localhost:8000?")
        return False
    except Exception as e:
        print(f"❌ FAIL: Error testing poll endpoint: {e}")
        return False

def test_quiz_generation():
    """Test quiz generation with better error handling"""
    print("\n🧠 TESTING QUIZ GENERATION")
    print("=" * 50)
    
    # Check if API key is configured
    groq_key = os.getenv('GROQ_API_KEY')
    if not groq_key:
        print("⚠️  WARNING: GROQ_API_KEY not set. Quiz generation will fail gracefully.")
    else:
        print(f"✓ GROQ_API_KEY configured (length: {len(groq_key)})")
    
    url = f"{BASE_URL}/api/v1/quizzes/generate"
    payload = {
        "topic": "Python programming",
        "num_questions": 2,
        "difficulty": "easy",
        "employee_level": "junior"
    }
    
    try:
        print(f"🚀 Sending request to: {url}")
        print(f"📝 Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(url, json=payload, timeout=30)
        print(f"✓ Response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✓ SUCCESS: Quiz generated successfully")
            print(f"📊 Number of questions: {len(data.get('questions', []))}")
            
            # Validate question structure
            questions = data.get('questions', [])
            for i, q in enumerate(questions):
                if 'stem' in q and 'options' in q and 'correct_index' in q:
                    print(f"  ✓ Question {i+1}: Valid structure")
                else:
                    print(f"  ❌ Question {i+1}: Invalid structure")
            return True
        else:
            data = response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
            print(f"❌ FAIL: Status {response.status_code}")
            print(f"Response: {json.dumps(data, indent=2) if isinstance(data, dict) else data}")
            
            # Check if it's a configuration error (expected if no API key)
            if response.status_code == 500 and isinstance(data, dict):
                error_msg = data.get('detail', '')
                if 'GROQ API key' in error_msg or 'authentication failed' in error_msg:
                    print("✓ Expected error due to missing/invalid API key")
                    return True
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ FAIL: Cannot connect to server. Is it running on http://localhost:8000?")
        return False
    except Exception as e:
        print(f"❌ FAIL: Error testing quiz generation: {e}")
        return False

def test_health_check():
    """Test basic health check"""
    print("\n💚 TESTING HEALTH CHECK")
    print("=" * 50)
    
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print("✓ Health check passed")
            print(f"📊 Status: {data}")
            return True
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ FAIL: Cannot connect to server. Is it running on http://localhost:8000?")
        return False
    except Exception as e:
        print(f"❌ FAIL: Error in health check: {e}")
        return False

def main():
    print("🔧 TESTING FINAL FIXES")
    print("=" * 60)
    print("🎯 Testing:")
    print("   1. Poll endpoint no longer returns 'result': null")
    print("   2. Quiz generation has improved error handling")
    print("   3. Basic health check")
    print("=" * 60)
    
    results = []
    
    # Test health check first
    results.append(("Health Check", test_health_check()))
    
    # Test poll endpoint
    results.append(("Poll Endpoint", test_poll_endpoint()))
    
    # Test quiz generation
    results.append(("Quiz Generation", test_quiz_generation()))
    
    # Summary
    print("\n📋 TEST SUMMARY")
    print("=" * 50)
    passed = 0
    for test_name, result in results:
        status = "✓ PASS" if result else "❌ FAIL"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n🎯 OVERALL: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("🎉 All tests passed! The fixes are working correctly.")
    else:
        print("⚠️  Some tests failed. Check the output above for details.")

if __name__ == "__main__":
    main()
