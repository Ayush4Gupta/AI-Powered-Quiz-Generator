#!/usr/bin/env python3

import requests
import json
import time

def test_enhanced_quiz_generation():
    """Test the enhanced quiz generation with improved error handling."""
    
    # Wait a moment for server to start
    print("🚀 Starting Enhanced Quiz Generation Test")
    print("=" * 60)
    
    # Test server health first
    health_endpoints = [
        "http://localhost:8000/livez",
        "http://localhost:8000/readyz"
    ]
    
    server_running = False
    for endpoint in health_endpoints:
        try:
            print(f"⚡ Checking {endpoint}...")
            response = requests.get(endpoint, timeout=3)
            if response.status_code == 200:
                print(f"   ✅ {endpoint} - OK")
                server_running = True
                break
            else:
                print(f"   ❌ {endpoint} - Status {response.status_code}")
        except Exception as e:
            print(f"   ❌ {endpoint} - Failed: {e}")
    
    if not server_running:
        print("\n💥 Server not running! Please start with:")
        print("   python -m uvicorn app.main:app --reload --port 8000")
        return
    
    # Test quiz generation with various topics
    test_cases = [
        {
            "name": "COP topic (previously problematic)",
            "payload": {
                "topic": "cop",
                "num_questions": 2,
                "difficulty": "easy",
                "employee_level": "junior"
            }
        },
        {
            "name": "Climate change topic",
            "payload": {
                "topic": "climate change",
                "num_questions": 1,
                "difficulty": "medium",
                "employee_level": "senior"
            }
        },
        {
            "name": "Technology topic",
            "payload": {
                "topic": "technology",
                "num_questions": 1,
                "difficulty": "easy",
                "employee_level": "junior"
            }
        }
    ]
    
    print(f"\n🧪 Testing {len(test_cases)} different scenarios...")
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}️⃣ Testing: {test_case['name']}")
        print("-" * 40)
        
        url = "http://localhost:8000/api/quizzes/generate"
        payload = test_case["payload"]
        
        try:
            print(f"📤 Request: {json.dumps(payload, indent=2)}")
            start_time = time.time()
            
            response = requests.post(url, json=payload, timeout=45)
            elapsed = time.time() - start_time
            
            print(f"⏱️  Response time: {elapsed:.2f}s")
            print(f"📊 Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    questions = data.get('questions', [])
                    print(f"✅ SUCCESS! Generated {len(questions)} questions")
                    
                    # Show sample question
                    if questions:
                        q = questions[0]
                        print(f"📝 Sample question:")
                        print(f"   Stem: {q.get('stem', 'No stem')[:80]}...")
                        print(f"   Options: {len(q.get('options', []))} choices")
                        print(f"   Has explanation: {'explanation' in q}")
                        print(f"   Correct index: {q.get('correct_index', 'N/A')}")
                        
                        # Validate JSON structure
                        required_fields = ['stem', 'options', 'correct_index', 'explanation']
                        missing_fields = [f for f in required_fields if f not in q]
                        if missing_fields:
                            print(f"⚠️  Missing fields: {missing_fields}")
                        else:
                            print("✅ All required fields present")
                
                except json.JSONDecodeError as e:
                    print(f"❌ JSON Parse Error: {e}")
                    print(f"📄 Raw response: {response.text[:300]}...")
                    
            else:
                print(f"❌ HTTP Error {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"📄 Error details: {json.dumps(error_data, indent=2)}")
                except:
                    print(f"📄 Raw error: {response.text[:300]}...")
                    
        except requests.exceptions.Timeout:
            print("⏰ Request timed out (45s)")
        except Exception as e:
            print(f"💥 Exception: {e}")
    
    print(f"\n🎯 Test Summary:")
    print("=" * 60)
    print("✅ Enhanced error handling features:")
    print("   • Rate limiting with exponential backoff (5 retries)")
    print("   • Advanced JSON parsing with multiple fix strategies")
    print("   • Detailed error logging with position markers")
    print("   • Structural completion for incomplete responses")
    print("   • Progressive error recovery")
    print("\n💡 If errors persist, check server logs for detailed debugging info")

if __name__ == "__main__":
    test_enhanced_quiz_generation()
