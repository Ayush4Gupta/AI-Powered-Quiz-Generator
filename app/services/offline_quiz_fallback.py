"""
Offline quiz generation fallback
Used when network connectivity is unavailable
"""

import random
from typing import List, Dict, Any

# Offline quiz templates
OFFLINE_TEMPLATES = {'python': [{'stem': 'What is the correct way to define a function in Python?', 'options': [{'text': 'def function_name():'}, {'text': 'function function_name()'}, {'text': 'def function_name[]'}, {'text': 'function_name() def'}], 'correct_index': 0, 'explanation': "Functions in Python are defined using the 'def' keyword followed by the function name and parentheses.", 'source': 'general'}, {'stem': 'Which of the following is used to handle exceptions in Python?', 'options': [{'text': 'try-catch'}, {'text': 'try-except'}, {'text': 'try-finally'}, {'text': 'catch-throw'}], 'correct_index': 1, 'explanation': 'Python uses try-except blocks to handle exceptions.', 'source': 'general'}], 'general': [{'stem': 'What is the primary purpose of version control systems?', 'options': [{'text': 'To track changes in code over time'}, {'text': 'To compile code faster'}, {'text': 'To debug applications'}, {'text': 'To optimize performance'}], 'correct_index': 0, 'explanation': 'Version control systems track changes in code, allowing developers to manage different versions and collaborate effectively.', 'source': 'general'}, {'stem': 'Which of the following is a best practice for writing clean code?', 'options': [{'text': 'Use meaningful variable names'}, {'text': 'Write very long functions'}, {'text': 'Avoid comments entirely'}, {'text': 'Use single-letter variable names'}], 'correct_index': 0, 'explanation': 'Using meaningful variable names makes code more readable and maintainable.', 'source': 'general'}]}

def generate_offline_quiz(topic: str, n: int, difficulty: str = "medium") -> List[Dict[str, Any]]:
    """
    Generate quiz questions using offline templates
    """
    # Determine which template to use based on topic
    if "python" in topic.lower():
        template_key = "python"
    else:
        template_key = "general"
    
    templates = OFFLINE_TEMPLATES.get(template_key, OFFLINE_TEMPLATES["general"])
    
    # Generate questions by repeating templates if needed
    questions = []
    for i in range(n):
        template = templates[i % len(templates)]
        # Modify question slightly to avoid exact duplicates
        question = template.copy()
        if i >= len(templates):
            question["stem"] = f"[Question {i+1}] " + question["stem"]
        questions.append(question)
    
    return questions

def is_network_available() -> bool:
    """Check if network is available for API calls"""
    try:
        import socket
        socket.gethostbyname('api.groq.com')
        return True
    except (socket.gaierror, socket.error):
        return False
