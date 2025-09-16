#!/usr/bin/env python3

import requests
import json

def test_database_cleaned():
    """Test if database is completely clean."""
    print("=== Testing Database Cleanup ===")
    
    try:
        url = "http://localhost:8000/api/v1/quizzes/debug/indexed-content-detailed"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            total_chunks = data.get("total_chunks", 0)
            
            print(f"Total chunks in database: {total_chunks}")
            
            if total_chunks == 0:
                print("✅ Database is completely clean!")
                return True
            else:
                print(f"❌ Database still has {total_chunks} chunks")
                sample_content = data.get("sample_content", [])
                if sample_content:
                    print("Sample remaining content:")
                    for i, content in enumerate(sample_content[:3]):
                        print(f"  {i+1}. {content.get('text_preview', '')[:100]}...")
                return False
        else:
            print(f"❌ API Error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_session_endpoints():
    """Test session management endpoints."""
    print("\n=== Testing Session Management ===")
    
    # Test create session
    print("1. Creating new session...")
    try:
        response = requests.post("http://localhost:8000/api/sessions/create", timeout=10)
        if response.status_code == 200:
            data = response.json()
            session_id = data.get("session_id")
            print(f"✅ Session created: {session_id}")
            
            # Test list sessions (should be empty since no content uploaded)
            print("2. Listing sessions...")
            response = requests.get("http://localhost:8000/api/sessions/list", timeout=10)
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Sessions listed: {data.get('total_count', 0)} active sessions")
            else:
                print(f"❌ List sessions failed: {response.status_code}")
            
            return session_id
        else:
            print(f"❌ Create session failed: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ Session test error: {e}")
        return None

def test_general_knowledge():
    """Test that general knowledge works without contamination."""
    print("\n=== Testing General Knowledge (No Session) ===")
    
    url = "http://localhost:8000/api/quizzes/generate"
    payload = {
        "topic": "machine learning",
        "num_questions": 2,
        "difficulty": "medium"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Quiz generated successfully!")
            
            # Check for climate contamination
            quiz_text = json.dumps(data)
            climate_words = ["climate", "greenhouse", "emission", "carbon", "global warming"]
            
            found_climate = []
            for word in climate_words:
                if word.lower() in quiz_text.lower():
                    found_climate.append(word)
            
            if found_climate:
                print(f"❌ CLIMATE CONTAMINATION FOUND: {found_climate}")
                return False
            else:
                print("✅ NO CONTAMINATION! Clean general knowledge quiz.")
                return True
        else:
            print(f"❌ Quiz generation failed: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    print("🧪 Testing Complete Fix Implementation...\n")
    
    # Test 1: Database cleanup
    database_clean = test_database_cleaned()
    
    # Test 2: Session management
    session_id = test_session_endpoints()
    
    # Test 3: General knowledge without contamination
    general_clean = test_general_knowledge()
    
    print("\n" + "="*50)
    print("📊 FINAL RESULTS:")
    print(f"Database Clean: {'✅ PASS' if database_clean else '❌ FAIL'}")
    print(f"Session Management: {'✅ PASS' if session_id else '❌ FAIL'}")
    print(f"General Knowledge Clean: {'✅ PASS' if general_clean else '❌ FAIL'}")
    
    if database_clean and session_id and general_clean:
        print("\n🎉 ALL TESTS PASSED! The fix is complete.")
        print(f"\n📝 Session ID for future use: {session_id}")
        print("\n💡 Usage Guide:")
        print("- General Knowledge: Don't include session_id in requests")
        print("- PDF Content: Use session_id from /api/sessions/create")
        print("- Manage Sessions: Use /api/sessions/* endpoints")
    else:
        print("\n❌ Some tests failed. Check the issues above.")

if __name__ == "__main__":
    main()
