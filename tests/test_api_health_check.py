#!/usr/bin/env python3
"""
Test the running server to verify PDF content is used in quiz generation
"""

import requests
import json
import time

def test_live_server():
    """Test the live server API"""
    base_url = "http://localhost:8000/api/v1"
    
    print("Testing Live Server API")
    print("=" * 40)
    
    try:
        # Test 1: Health check
        print("1. Health check...")
        health = requests.get(f"{base_url}/health", timeout=5)
        print(f"   Status: {health.status_code}")
        
        # Test 2: Search debug endpoint
        print("\n2. Testing search debug...")
        search = requests.get(f"{base_url}/quizzes/debug/search/conference%20of%20parties", timeout=10)
        print(f"   Status: {search.status_code}")
        
        if search.status_code == 200:
            search_data = search.json()
            print(f"   Passages found: {search_data.get('passages_found', 0)}")
            print(f"   Has content: {search_data.get('has_content', False)}")
        
        # Test 3: Generate quiz
        print("\n3. Generating quiz...")
        quiz_request = {
            "topic": "conference of parties",
            "num_questions": 3,
            "difficulty": "medium",
            "employee_level": "intermediate",
            "num_variants": 1
        }
        
        quiz = requests.post(f"{base_url}/quizzes/generate", json=quiz_request, timeout=60)
        print(f"   Status: {quiz.status_code}")
        
        if quiz.status_code == 200:
            quiz_data = quiz.json()
            variants = quiz_data.get('variants', [])
            
            if variants:
                questions = variants[0].get('questions', [])
                print(f"   Generated: {len(questions)} questions")
                
                pdf_count = 0
                general_count = 0
                
                for i, q in enumerate(questions):
                    source = q.get('source', 'unknown')
                    if source == 'pdf':
                        pdf_count += 1
                    elif source == 'general':
                        general_count += 1
                    
                    print(f"   Q{i+1}: source={source}")
                    print(f"        {q.get('question', '')[:100]}...")
                
                print(f"\n   RESULTS:")
                print(f"   PDF questions: {pdf_count}")
                print(f"   General questions: {general_count}")
                
                if pdf_count > 0:
                    print("   🎉 SUCCESS: PDF content is being used!")
                else:
                    print("   ❌ ISSUE: Still only general questions")
            else:
                print("   No variants in response")
        else:
            print(f"   Error: {quiz.text}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Server not running. Start with: python -m app.main")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_live_server()
