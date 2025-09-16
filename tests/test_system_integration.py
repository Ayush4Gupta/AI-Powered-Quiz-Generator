#!/usr/bin/env python3
"""
Final test to generate a quiz and verify PDF content is used
"""

import requests
import json
import sys

def final_test():
    """Final test of the quiz generation with PDF content"""
    base_url = "http://localhost:8000/api/v1"
    
    print("=== FINAL TEST: PDF CONTENT IN QUIZ GENERATION ===")
    print()
    
    # Generate quiz request
    quiz_request = {
        "topic": "conference of parties",
        "num_questions": 3,
        "difficulty": "medium", 
        "employee_level": "intermediate",
        "num_variants": 1
    }
    
    try:
        print("Generating quiz with our fixes...")
        print(f"Request: {json.dumps(quiz_request, indent=2)}")
        print()
        
        response = requests.post(
            f"{base_url}/quizzes/generate",
            json=quiz_request,
            timeout=60
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Extract questions
            variants = data.get('variants', [])
            if not variants:
                print("❌ No variants in response")
                return
                
            questions = variants[0].get('questions', [])
            if not questions:
                print("❌ No questions in response")
                return
                
            print(f"✅ Generated {len(questions)} questions")
            print()
            
            # Analyze sources
            pdf_count = 0
            general_count = 0
            
            for i, question in enumerate(questions, 1):
                source = question.get('source', 'unknown')
                question_text = question.get('question', '')
                
                print(f"Question {i}:")
                print(f"  Source: {source}")
                print(f"  Text: {question_text}")
                print()
                
                if source == 'pdf':
                    pdf_count += 1
                elif source == 'general':
                    general_count += 1
            
            # Final results
            print("=" * 50)
            print("FINAL RESULTS:")
            print(f"  PDF-based questions: {pdf_count}")
            print(f"  General questions: {general_count}")
            print(f"  Total questions: {len(questions)}")
            print()
            
            if pdf_count > 0:
                print("🎉 SUCCESS! PDF content is being used for quiz generation!")
                print("✅ The search fixes are working correctly!")
            else:
                print("❌ ISSUE: Still generating only general questions")
                print("🔍 This suggests there may be an issue in the quiz generation logic")
                
        else:
            print(f"❌ API Error: {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to server")
        print("Make sure the server is running: python -m app.main")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    final_test()
