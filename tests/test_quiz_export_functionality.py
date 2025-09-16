#!/usr/bin/env python3
"""
Test the new export functionality that exports the last generated quiz
"""

import requests
import json
import time

def test_export_last_quiz():
    """Test the new export last quiz functionality"""
    base_url = "http://localhost:8000/api/v1"
    
    print("=== TESTING EXPORT LAST QUIZ FUNCTIONALITY ===")
    print()
    
    try:
        # Step 1: Generate a quiz first
        print("1. Generating a quiz...")
        quiz_request = {
            "topic": "conference of parties",
            "num_questions": 3,
            "difficulty": "medium",
            "employee_level": "intermediate",
            "num_variants": 1
        }
        
        quiz_response = requests.post(f"{base_url}/quizzes/generate", json=quiz_request, timeout=60)
        
        if quiz_response.status_code == 200:
            print("   ✅ Quiz generated successfully!")
            quiz_data = quiz_response.json()
            variants = quiz_data.get('variants', [])
            if variants:
                questions = variants[0].get('questions', [])
                print(f"   Generated {len(questions)} questions")
                
                # Show question sources
                for i, q in enumerate(questions, 1):
                    source = q.get('source', 'unknown')
                    print(f"     Q{i}: source={source}")
        else:
            print(f"   ❌ Quiz generation failed: {quiz_response.status_code}")
            return
        
        # Step 2: Check last quiz info
        print("\n2. Checking last quiz info...")
        last_info_response = requests.get(f"{base_url}/quizzes/last")
        
        if last_info_response.status_code == 200:
            last_info = last_info_response.json()
            print("   ✅ Last quiz info retrieved:")
            print(f"     Topic: {last_info.get('topic')}")
            print(f"     Questions: {last_info.get('num_questions')}")
            print(f"     Difficulty: {last_info.get('difficulty')}")
            print(f"     Available for export: {last_info.get('available_for_export')}")
        else:
            print(f"   ❌ Failed to get last quiz info: {last_info_response.status_code}")
        
        # Step 3: Export the last quiz without providing data
        print("\n3. Exporting last quiz to TXT...")
        export_response = requests.post(f"{base_url}/quizzes/export/txt/last")
        
        if export_response.status_code == 200:
            export_data = export_response.json()
            print("   ✅ Export successful!")
            print(f"     Filename: {export_data.get('filename')}")
            print(f"     File path: {export_data.get('file_path')}")
            print(f"     Message: {export_data.get('message')}")
            
            # Try to read the exported file
            try:
                file_path = export_data.get('file_path')
                if file_path:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    print(f"\n   📄 File content preview (first 500 chars):")
                    print(content[:500] + "..." if len(content) > 500 else content)
            except Exception as e:
                print(f"   ⚠️  Could not read exported file: {e}")
        else:
            print(f"   ❌ Export failed: {export_response.status_code}")
            print(f"   Response: {export_response.text}")
        
        # Step 4: Test export with custom filename
        print("\n4. Exporting with custom filename...")
        custom_export_response = requests.post(f"{base_url}/quizzes/export/txt/last?filename=my_custom_quiz")
        
        if custom_export_response.status_code == 200:
            custom_data = custom_export_response.json()
            print("   ✅ Custom filename export successful!")
            print(f"     Filename: {custom_data.get('filename')}")
        else:
            print(f"   ❌ Custom export failed: {custom_export_response.status_code}")
        
        print("\n🎉 Test completed!")
        print("\nNow you can use:")
        print(f"  GET  {base_url}/quizzes/last - to check last quiz info")
        print(f"  POST {base_url}/quizzes/export/txt/last - to export last quiz")
        print(f"  POST {base_url}/quizzes/export/txt/last?filename=myquiz - with custom filename")
        
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to server. Make sure it's running: python -m app.main")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_export_last_quiz()
