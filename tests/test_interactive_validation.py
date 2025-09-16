#!/usr/bin/env python3
"""
Manual Test Script for Search Fixes

Run this script to test if the search fixes are working.
This script will output results to both console and a log file.
"""

import sys
import os
import json
import traceback
from datetime import datetime

# Add the app directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def write_log(message, log_file="manual_test_log.txt"):
    """Write message to both console and log file"""
    print(message)
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(message + "\n")

def test_search_fixes():
    """Test the search functionality fixes"""
    log_file = "manual_test_log.txt"
    
    # Clear previous log
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"Search Fixes Test - {datetime.now()}\n")
        f.write("=" * 60 + "\n\n")
    
    write_log("=== TESTING SEARCH FIXES ===")
    
    try:
        write_log("\n1. Testing module imports...")
        
        # Test basic imports
        from app.core.settings import get_settings
        write_log("   ✓ Settings import successful")
        
        import weaviate
        write_log("   ✓ Weaviate import successful")
        
        # Test search module import
        from app.services.search import relevant_passages
        write_log("   ✓ Search module import successful")
        
        write_log("\n2. Testing Weaviate connectivity...")
        settings = get_settings()
        client = weaviate.Client(settings.weaviate_url)
        
        if client.is_ready():
            write_log("   ✓ Weaviate is ready")
            
            # Get document count
            count_result = client.query.aggregate("DocumentChunk").with_meta_count().do()
            total_docs = count_result.get('data', {}).get('Aggregate', {}).get('DocumentChunk', [{}])[0].get('meta', {}).get('count', 0)
            write_log(f"   ✓ Total documents in Weaviate: {total_docs}")
            
        else:
            write_log("   ✗ Weaviate is not ready")
            return
        
        write_log("\n3. Testing search function directly...")
        
        # Test the search function with different queries
        test_queries = [
            ("conference of parties", None),  # No chapter filter
            ("conference of parties", 1),     # With chapter filter  
            ("climate change", None),
            ("greenhouse gas", None),
            ("COP meetings", None)
        ]
        
        for query, chapter in test_queries:
            write_log(f"\n   Testing: '{query}' (chapter={chapter})")
            
            try:
                passages = relevant_passages(query, chapter)
                write_log(f"   Result: {len(passages)} passages found")
                
                if passages:
                    write_log("   ✓ SUCCESS: Search returned results!")
                    # Show first passage preview
                    preview = passages[0][:150].replace('\n', ' ')
                    write_log(f"   First passage: {preview}...")
                else:
                    write_log("   ✗ No passages found")
                    
            except Exception as e:
                write_log(f"   ✗ Error: {e}")
                write_log(f"   Traceback: {traceback.format_exc()}")
        
        write_log("\n4. Testing with API simulation...")
        
        # Simulate what the API does
        from app.services.quiz_generation import generate_quiz
        
        # Create a request like the API would
        test_request = {
            "topic": "conference of parties",
            "num_questions": 2,
            "difficulty": "medium",
            "employee_level": "intermediate"
        }
        
        write_log(f"   Simulating API call with: {json.dumps(test_request, indent=2)}")
        
        try:
            # This should use our fixed search function
            quiz_content = generate_quiz(
                topic=test_request["topic"],
                n=test_request["num_questions"],
                diff=test_request["difficulty"],
                level=test_request["employee_level"],
                chapter=None  # No chapter filter
            )
            
            write_log(f"   Quiz generation result: {len(quiz_content)} questions")
            
            # Check sources
            pdf_count = 0
            general_count = 0
            
            for i, question in enumerate(quiz_content):
                source = question.get('source', 'unknown')
                if source == 'pdf':
                    pdf_count += 1
                elif source == 'general':
                    general_count += 1
                    
                write_log(f"   Q{i+1}: source={source}")
                write_log(f"        {question.get('question', '')[:80]}...")
            
            write_log(f"\n   Summary:")
            write_log(f"   PDF-based questions: {pdf_count}")
            write_log(f"   General questions: {general_count}")
            
            if pdf_count > 0:
                write_log("   ✓ SUCCESS: PDF content is being used for quiz generation!")
            else:
                write_log("   ✗ ISSUE: Still generating only general questions")
                write_log("   This suggests the search fixes may not be working as expected")
                
        except Exception as e:
            write_log(f"   ✗ Quiz generation error: {e}")
            write_log(f"   Traceback: {traceback.format_exc()}")
        
        write_log("\n=== TEST COMPLETED ===")
        write_log(f"Full log saved to: {log_file}")
        
    except Exception as e:
        write_log(f"\n✗ CRITICAL ERROR: {e}")
        write_log(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    test_search_fixes()
