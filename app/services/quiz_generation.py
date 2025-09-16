import httpx, structlog, json, re, time, random
from app.core.settings import get_settings
from .search import relevant_passages
from .offline_quiz_fallback import generate_offline_quiz, is_network_available

settings = get_settings()
log = structlog.get_logger()

def extract_main_topics_from_content(content_preview: str) -> list:
    """Extract main topics from content using simple keyword analysis"""
    try:
        # Simple topic extraction using common keywords and patterns
        content_lower = content_preview.lower()
        
        # Common topic indicators
        topic_keywords = {
            'programming': ['python', 'javascript', 'code', 'programming', 'function', 'class', 'variable'],
            'business': ['business', 'management', 'strategy', 'market', 'customer', 'sales'],
            'science': ['research', 'study', 'experiment', 'analysis', 'data', 'theory'],
            'technology': ['technology', 'software', 'system', 'network', 'computer', 'digital'],
            'health': ['health', 'medical', 'patient', 'treatment', 'disease', 'medicine'],
            'finance': ['finance', 'money', 'investment', 'financial', 'cost', 'budget'],
            'education': ['education', 'learning', 'student', 'course', 'training', 'knowledge']
        }
        
        topic_scores = {}
        for topic, keywords in topic_keywords.items():
            score = sum(content_lower.count(keyword) for keyword in keywords)
            if score > 0:
                topic_scores[topic] = score
        
        # Sort by score and return top topics
        sorted_topics = sorted(topic_scores.items(), key=lambda x: x[1], reverse=True)
        return [topic.title() for topic, score in sorted_topics[:5]] or ["Mixed Topics"]
        
    except Exception as e:
        log.warning("topic_extraction.failed", error=str(e))
        return ["Mixed Topics"]

def check_topic_relevance_score(requested_topic: str, passages: list) -> float:
    """Check how relevant the content is to the requested topic (0.0-1.0)"""
    try:
        if not requested_topic or not passages:
            return 0.0
        
        topic_lower = requested_topic.lower()
        content_text = " ".join(passages[:5]).lower()  # Use first 5 passages
        
        # Direct keyword matching
        topic_words = topic_lower.split()
        matches = sum(content_text.count(word) for word in topic_words if len(word) > 2)
        
        # Normalize by content length (rough approximation)
        content_word_count = len(content_text.split())
        if content_word_count == 0:
            return 0.0
        
        relevance_score = min(matches / max(content_word_count * 0.1, 1), 1.0)
        return relevance_score
        
    except Exception as e:
        log.warning("topic_relevance.failed", error=str(e))
        return 0.0

def extract_topic_from_user_context(user_input: str = None) -> str:
    """Extract potential topic from user input or context"""
    try:
        if not user_input:
            return None
        
        # Common topic patterns in user requests
        user_lower = user_input.lower()
        
        # Look for explicit topic mentions
        topic_patterns = {
            'general knowledge': ['general knowledge', 'general', 'mixed topics', 'various topics'],
            'programming': ['programming', 'coding', 'python', 'javascript', 'software'],
            'business': ['business', 'management', 'marketing', 'sales'],
            'science': ['science', 'biology', 'chemistry', 'physics'],
            'technology': ['technology', 'tech', 'computer', 'software'],
            'health': ['health', 'medical', 'healthcare'],
            'finance': ['finance', 'financial', 'accounting', 'economics']
        }
        
        for topic, keywords in topic_patterns.items():
            if any(keyword in user_lower for keyword in keywords):
                return topic.title()
        
        return "General Knowledge"  # Default fallback
        
    except Exception as e:
        log.warning("topic_extraction_from_user.failed", error=str(e))
        return "General Knowledge"

PROMPT_TMPL = """
You are an expert examiner creating {n} multiple‑choice questions on "{topic}"
for a {level} employee. Difficulty: {difficulty}. 

CONTENT FROM UPLOADED SOURCES:
\"\"\"{context}\"\"\"

CRITICAL INSTRUCTIONS:
1. **PRIORITIZE UPLOADED CONTENT**: The above content comes from uploaded sources (PDFs, articles, documents) through semantic search
   - This content is highly relevant to "{topic}" and should be your PRIMARY source
   - Questions based on this content should be marked with "source": "{content_source_type}"
   - Only use "source": "general" when the uploaded content is insufficient

2. **GENERATION STRATEGY**:
   - Generate approximately {content_ratio}% questions from the provided uploaded content above ("source": "{content_source_type}")
   - Generate approximately {general_ratio}% questions from general knowledge ("source": "general")
   - **PREFER UPLOADED CONTENT**: If the uploaded content is substantial, generate as many questions as possible from it

3. **QUALITY REQUIREMENTS**:
   - Vary correct_index across all positions (0, 1, 2, 3)
   - Include brief explanations (1-2 sentences)
   - Make all 4 options plausible but only one clearly correct
   - Use specific facts and details from the uploaded content when available

4. **CONTENT UTILIZATION**:
   - Look for specific facts, figures, definitions, and concepts in the uploaded content
   - Create questions that test understanding of the provided material
   - Use direct quotes or paraphrases from the uploaded content when relevant

5. **STRICT JSON FORMAT**:
   - Return ONLY a valid JSON array, nothing else
   - Each question must have exactly these fields: "stem", "options", "correct_index", "explanation", "source"
   - Each option must be exactly: {{"text": "option text"}}
   - Ensure all quotes are properly escaped and closed
   - No trailing commas anywhere
   - No extra text, markdown, or thinking tags
   - Complete all explanations with proper closing quotes
   - End with a complete, valid JSON array

Return EXACTLY this format (complete and valid JSON):
[
  {{
    "stem": "Question text here?",
    "options": [
      {{"text": "Option 1"}},
      {{"text": "Option 2"}},
      {{"text": "Option 3"}},
      {{"text": "Option 4"}}
    ],
    "correct_index": 0,
    "explanation": "Brief explanation here.",
    "source": "{content_source_type}"
  }}
]

CRITICAL: Ensure the JSON is complete and valid. Do not include any <think> tags or incomplete fields.
"""

def check_network_connectivity() -> bool:
    """Check if we can reach external APIs"""
    try:
        # Try to resolve DNS first
        import socket
        socket.gethostbyname('api.groq.com')
        return True
    except (socket.gaierror, socket.error):
        return False

def call_deepseek(prompt: str, num_questions: int = 5, max_retries: int = 5) -> str:
    """Call Deepseek API with robust retry logic for rate limiting"""
    
    for attempt in range(max_retries):
        try:
            # Check network connectivity first
            if not check_network_connectivity():
                raise Exception("Network connectivity issue: Cannot resolve external API hostnames. Please check your internet connection.")
            
            estimated_tokens = num_questions * 300 + 500
            max_tokens = min(max(estimated_tokens, 2048), 8192)
            
            # Add some randomness to temperature for variants
            base_temp = 0.4
            temp_variation = 0.1 * (attempt / max_retries)  # Slight variation per attempt
            temperature = base_temp + temp_variation
            
            body = {
                "model": "deepseek-r1-distill-llama-70b",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            headers = {
                "Authorization": f"Bearer {settings.groq_api_key}",
                "Content-Type": "application/json"
            }

            if not settings.groq_api_key or settings.groq_api_key.strip() == "":
                raise Exception("GROQ API key is not configured.")

            log.info("llm.request.attempt", attempt=attempt+1, max_retries=max_retries, temperature=temperature)

            resp = httpx.post("https://api.groq.com/openai/v1/chat/completions",
                              json=body, headers=headers, timeout=60)

            if resp.status_code == 401:
                raise Exception("Unauthorized: Invalid GROQ API key.")
            elif resp.status_code == 429:
                # Rate limit - implement exponential backoff
                if attempt < max_retries - 1:
                    # Exponential backoff: 1s, 2s, 4s, 8s, 16s + random jitter
                    base_delay = 2 ** attempt
                    jitter = random.uniform(0.1, 0.9)  # Add randomness to prevent thundering herd
                    delay = base_delay + jitter
                    
                    log.warning("llm.rate_limit.retry", 
                              attempt=attempt+1, 
                              delay=delay, 
                              next_attempt=attempt+2)
                    
                    time.sleep(delay)
                    continue
                else:
                    raise Exception("Rate limit exceeded after all retries.")
            elif resp.status_code != 200:
                raise Exception(f"Unexpected error: {resp.status_code} - {resp.text}")

            try:
                resp_data = resp.json()
            except json.JSONDecodeError as e:
                raise Exception(f"Invalid JSON in response: {str(e)}")

            choice = resp_data.get("choices", [{}])[0]
            content = choice.get("message", {}).get("content", "").strip()
            
            log.info("llm.request.success", attempt=attempt+1, content_length=len(content))
            return content

        except Exception as e:
            if "Rate limit exceeded" in str(e) and attempt < max_retries - 1:
                # Continue retry loop for rate limits
                continue
            elif attempt == max_retries - 1:
                # Last attempt failed
                log.error("llm.request.failed_all_retries", error=str(e), total_attempts=max_retries)
                raise Exception(f"LLM request failed after {max_retries} attempts: {str(e)}")
            else:
                # Non-rate-limit error, fail immediately
                raise Exception(f"LLM request failed: {str(e)}")
    
    # Should never reach here
    raise Exception("Unexpected error in retry logic")

def generate_quiz_with_variants(topic: str, n: int, diff: str, level: str, num_variants: int = 1, session_id: str = None, use_all_content: bool = False):
    """Generate multiple quiz variants for different people with rate limiting and source diversification
    
    Args:
        topic: Topic for the quiz (can be ignored if use_all_content=True, but used as hint)
        n: Number of questions per variant
        diff: Difficulty level
        level: Employee level
        num_variants: Number of variants to generate
        session_id: Session ID for content filtering
        use_all_content: If True, generate quiz from all indexed content, using topic as hint
    """
    try:
        variants = []
        
        # Extract user's topic hint for intelligent fallback
        user_topic_hint = None
        if use_all_content and topic:
            user_topic_hint = extract_topic_from_user_context(topic)
            log.info("quiz.variants.topic_hint_extracted", 
                    original_topic=topic, 
                    extracted_hint=user_topic_hint,
                    use_all_content=use_all_content)
        
        # Check if we have content available for source diversification
        has_content = False
        if session_id:
            if use_all_content:
                # Get all content from the session regardless of topic
                from .search import get_all_session_content
                all_passages = get_all_session_content(session_id)
                has_content = all_passages and len(all_passages) > 0
                log.info("quiz.variants.all_content_availability", 
                        has_content=has_content, 
                        passages_count=len(all_passages) if all_passages else 0,
                        use_all_content=use_all_content)
            else:
                # Get topic-specific content
                test_passages = relevant_passages(topic, session_id)
                has_content = test_passages and len(test_passages) > 0 and check_topic_relevance(topic, test_passages)
                log.info("quiz.variants.topic_content_availability", 
                        has_content=has_content, 
                        passages_count=len(test_passages) if test_passages else 0,
                        topic=topic)
        
        # Use different temperature/randomness for each variant
        for variant_id in range(1, num_variants + 1):
            log.info("quiz.variant.start", 
                    variant_id=variant_id, 
                    topic=topic, 
                    total_variants=num_variants, 
                    has_content=has_content,
                    use_all_content=use_all_content)
            
            # Add delay between variants to prevent rate limiting (except for first variant)
            if variant_id > 1:
                delay = 2.0 + random.uniform(0.5, 1.5)  # 2-3.5 second delay between variants
                log.info("quiz.variant.delay", variant_id=variant_id, delay=delay)
                time.sleep(delay)
            
            # Generate questions for this variant with variant-specific preferences
            if use_all_content:
                questions = generate_quiz_from_all_content(n, diff, level, session_id, variant_id, user_topic_hint)
            else:
                questions = generate_quiz_with_variant_preference(topic, n, diff, level, session_id, variant_id, has_content)
            
            # Add some variation to the questions if we have multiple variants
            if num_variants > 1:
                questions = add_variation_to_questions(questions, variant_id)
            
            variants.append({
                "variant_id": variant_id,
                "questions": questions
            })
            
            log.info("quiz.variant.complete", variant_id=variant_id, question_count=len(questions))
        
        # Determine the effective topic for the response
        effective_topic = "All Indexed Content" if use_all_content else topic
        
        return {
            "topic": effective_topic,
            "num_questions": n,
            "difficulty": diff,
            "employee_level": level,
            "variants": variants
        }
    
    except Exception as e:
        raise Exception(f"Quiz variants generation failed: {str(e)}")

def generate_quiz_from_all_content(n: int, diff: str, level: str, session_id: str, variant_id: int = 1, user_requested_topic: str = None):
    """
    Generate quiz from all indexed content in a session (ignoring topic) with smart fallback logic
    
    Args:
        n: Number of questions to generate
        diff: Difficulty level
        level: Employee level
        session_id: Session ID containing the content
        variant_id: Variant number for variation
        user_requested_topic: Optional topic mentioned by user (e.g., "General Knowledge")
    
    Returns:
        List of question objects
    """
    try:
        log.info("quiz.all_content.start", 
                session_id=session_id, 
                num_questions=n, 
                variant_id=variant_id,
                user_requested_topic=user_requested_topic)
        
        # Import here to avoid circular imports
        from .search import get_all_session_content
        
        # Get all content from the session
        passages = get_all_session_content(session_id, k=50)
        
        # Edge Case 1: No context available but user requested a topic
        if not passages:
            log.warning("quiz.all_content.no_passages", 
                       session_id=session_id, 
                       user_requested_topic=user_requested_topic)
            
            fallback_topic = user_requested_topic or "General Knowledge"
            log.info("quiz.all_content.fallback_to_general", 
                    fallback_topic=fallback_topic,
                    reason="no_indexed_content")
            
            # Fall back to general knowledge quiz with the requested topic
            return generate_quiz_with_variant_preference(
                fallback_topic, n, diff, level, None, variant_id, False
            )
        
        # Edge Case 2: Very little context (less than 3 passages)
        if len(passages) < 3:
            log.warning("quiz.all_content.insufficient_content", 
                       session_id=session_id, 
                       passages_count=len(passages),
                       user_requested_topic=user_requested_topic)
            
            # If user requested a specific topic and we have little content, 
            # use the requested topic with general knowledge
            if user_requested_topic and user_requested_topic.lower() != "all indexed content":
                log.info("quiz.all_content.fallback_to_requested_topic", 
                        requested_topic=user_requested_topic,
                        reason="insufficient_indexed_content")
                return generate_quiz_with_variant_preference(
                    user_requested_topic, n, diff, level, None, variant_id, False
                )
        
        # Detect content source type and analyze content themes
        content_source_type = detect_content_source_type(session_id)
        
        # Extract main topics from the content for intelligent topic detection
        content_preview = "\n".join(passages[:5])  # First 5 passages for topic analysis
        detected_topics = extract_main_topics_from_content(content_preview)
        
        log.info("quiz.all_content.content_analysis", 
                session_id=session_id, 
                content_source_type=content_source_type,
                passages_count=len(passages),
                detected_topics=detected_topics[:3])  # Log top 3 topics
        
        # Edge Case 3: User requested topic doesn't match content AND we have good content
        content_topic_relevance = 0
        if user_requested_topic and user_requested_topic.lower() not in ["general knowledge", "all indexed content"]:
            content_topic_relevance = check_topic_relevance_score(user_requested_topic, passages[:10])
            log.info("quiz.all_content.topic_relevance_check",
                    user_requested_topic=user_requested_topic,
                    relevance_score=content_topic_relevance)
        
        # Determine the effective topic and strategy
        if content_topic_relevance < 0.3 and user_requested_topic and len(passages) >= 3:
            # Content doesn't match user's requested topic, but we have good content
            # Use a hybrid approach: some from content, some from requested topic
            effective_topic = f"{user_requested_topic} (with additional context)"
            content_ratio = 60  # 60% from uploaded content
            general_ratio = 40  # 40% from requested topic/general knowledge
            log.info("quiz.all_content.hybrid_approach",
                    user_requested_topic=user_requested_topic,
                    content_ratio=content_ratio,
                    general_ratio=general_ratio)
        else:
            # Content is relevant or no specific topic requested - use primarily content
            effective_topic = detected_topics[0] if detected_topics else "Comprehensive Knowledge"
            content_ratio = 85  # 85% from uploaded content
            general_ratio = 15  # 15% general knowledge
            log.info("quiz.all_content.content_focused_approach",
                    effective_topic=effective_topic,
                    content_ratio=content_ratio)
        
        # Create a comprehensive context from all passages
        context = "\n\n".join(passages[:20])  # Use first 20 passages to avoid token limits
        
        # Create an intelligent prompt that handles the edge cases
        smart_prompt = f"""
You are an expert examiner creating {n} multiple‑choice questions from the uploaded content
for a {level} employee. Difficulty: {diff}. 

CONTENT FROM UPLOADED SOURCES:
\"\"\"{context}\"\"\"

USER CONTEXT:
- User requested topic: {user_requested_topic or "Not specified"}
- Detected content topics: {", ".join(detected_topics[:3]) if detected_topics else "Mixed topics"}
- Content relevance to user topic: {"High" if content_topic_relevance > 0.7 else "Medium" if content_topic_relevance > 0.3 else "Low"}

CRITICAL INSTRUCTIONS:
1. **SMART CONTENT UTILIZATION**:
   - Generate approximately {content_ratio}% questions from the provided uploaded content above ("source": "{content_source_type}")
   - Generate approximately {general_ratio}% questions from {"the user's requested topic: " + user_requested_topic if user_requested_topic and content_topic_relevance < 0.5 else "general knowledge"} ("source": "general")
   - Focus on the most relevant and important information in the uploaded content

2. **INTELLIGENT TOPIC HANDLING**:
   - If the uploaded content covers the user's requested topic, prioritize that overlap
   - If the content doesn't match the user's topic, create questions from both sources
   - Ensure questions test understanding of the actual uploaded material

3. **CONTENT ANALYSIS STRATEGY**:
   - Identify key concepts, facts, and information in the uploaded content
   - Create questions that span different aspects of the material
   - Use specific details and examples from the provided content
   - Make questions that would be valuable for someone learning from this material

4. **QUALITY REQUIREMENTS**:
   - Vary correct_index across all positions (0, 1, 2, 3)
   - Include brief explanations (1-2 sentences)
   - Make all 4 options plausible but only one clearly correct
   - Questions should be practical and test real understanding

5. **STRICT JSON FORMAT**:
   - Return ONLY a valid JSON array, nothing else
   - Each question must have exactly these fields: "stem", "options", "correct_index", "explanation", "source"
   - Each option must be exactly: {{"text": "option text"}}
   - Ensure all quotes are properly escaped and closed
   - No trailing commas anywhere
   - No extra text, markdown, or thinking tags

Return EXACTLY this format (complete and valid JSON):
[
  {{
    "stem": "Question text here?",
    "options": [
      {{"text": "Option A"}},
      {{"text": "Option B"}},
      {{"text": "Option C"}},
      {{"text": "Option D"}}
    ],
    "correct_index": 0,
    "explanation": "Brief explanation here.",
    "source": "{content_source_type}"
  }}
]
"""
        
        # Call the AI model
        max_retries = 3
        for attempt in range(max_retries):
            try:
                log.info("quiz.all_content.attempt", 
                        attempt=attempt + 1, 
                        session_id=session_id,
                        variant_id=variant_id)
                
                raw_response = call_deepseek(smart_prompt, n)
                questions = process_quiz_response(raw_response, n, attempt, max_retries)
                
                if questions and len(questions) >= n // 2:  # Accept if we got at least half
                    log.info("quiz.all_content.success", 
                            session_id=session_id,
                            variant_id=variant_id,
                            questions_generated=len(questions))
                    return questions
                else:
                    log.warning("quiz.all_content.insufficient_questions", 
                              session_id=session_id,
                              attempt=attempt + 1,
                              questions_generated=len(questions) if questions else 0,
                              questions_needed=n)
                    
            except Exception as e:
                log.error("quiz.all_content.attempt_failed", 
                         session_id=session_id,
                         attempt=attempt + 1, 
                         error=str(e))
                if attempt == max_retries - 1:
                    # Final fallback to general knowledge
                    log.warning("quiz.all_content.fallback_to_general", session_id=session_id)
                    return generate_quiz_with_variant_preference(
                        "General Knowledge", n, diff, level, None, variant_id, False
                    )
        
        # Should not reach here, but safety fallback
        return []
        
    except Exception as e:
        log.error("quiz.all_content.error", 
                 session_id=session_id, 
                 error=str(e))
        # Final fallback
        return generate_quiz_with_variant_preference(
            "General Knowledge", n, diff, level, None, variant_id, False
        )

def generate_quiz_with_variant_preference(topic: str, n: int, diff: str, level: str, session_id: str = None, variant_id: int = 1, has_pdf_content: bool = False):
    """Generate quiz with variant-specific source preferences to ensure diversity"""
    try:
        # Check network connectivity first
        if not is_network_available():
            log.warning("quiz.network_unavailable", message="Using offline fallback due to network issues")
            return generate_offline_quiz(topic, n, diff)
        
        # First, check if we should even search for content
        should_search_content = session_id is not None
        
        # If no session_id provided, skip content search entirely and use general knowledge
        if not session_id:
            log.info("quiz.no_session", topic=topic, message="No session ID provided, using general knowledge only")
            passages = []
            is_topic_relevant = False
            content_source_type = "general"
        else:
            # Search for relevant passages in the specified session
            passages = relevant_passages(topic, session_id)
            log.info("quiz.search.primary", topic=topic, session_id=session_id, variant_id=variant_id, passage_count=len(passages) if passages else 0, passage_length=sum(len(p) for p in passages) if passages else 0)
            
            # Detect content source type from session
            content_source_type = detect_content_source_type(session_id)
            log.info("quiz.content_source_detected", session_id=session_id, content_source_type=content_source_type)
            
            # Check if topic is relevant to uploaded content
            is_topic_relevant = check_topic_relevance(topic, passages)
            log.info("quiz.topic_relevance", topic=topic, variant_id=variant_id, is_relevant=is_topic_relevant, passages_found=len(passages) if passages else 0, content_source_type=content_source_type)
        
        # If topic is not relevant to uploaded content, skip all searches and use general knowledge
        if not is_topic_relevant:
            log.info("quiz.using_general", topic=topic, variant_id=variant_id, reason="Topic not relevant to uploaded content" if should_search_content else "No session provided")
            passages = []  # Clear passages to force general knowledge
            content_source_type = "general"
            # Skip all fallback searches when topic is not relevant or no session provided
        else:
            # If topic is relevant but passages are insufficient, try fallback searches
            if not passages or len("\n\n".join(passages)) < 100:
                fallback_topics = [
                    topic,
                    f"{topic} effects", f"{topic} impact", f"{topic} facts", f"{topic} summary",
                    f"{topic} introduction", f"{topic} basics", f"{topic} overview", f"{topic} definition"
                ]
                merged_passages = []
                for fallback_topic in fallback_topics:
                    fallback_passages = relevant_passages(fallback_topic, session_id)
                    log.info("quiz.search.fallback", fallback_topic=fallback_topic, session_id=session_id, variant_id=variant_id, passage_count=len(fallback_passages) if fallback_passages else 0, passage_length=sum(len(p) for p in fallback_passages) if fallback_passages else 0)
                    if fallback_passages:
                        # Check relevance for fallback topics too
                        if check_topic_relevance(topic, fallback_passages):
                            merged_passages.extend(fallback_passages)
                
                # Use merged passages if substantial and relevant
                if merged_passages and len("\n\n".join(merged_passages)) > 100:
                    passages = merged_passages
        
        # ...existing code...
        max_retries = 3
        result = []
        for attempt in range(max_retries):
            try:
                # More aggressive content prioritization
                has_substantial_content = passages and len("\n\n".join(passages)) > 50  # Lower threshold
                total_content_length = sum(len(p) for p in passages) if passages else 0
                
                # Adjust ratios based on content availability AND variant preferences for diversification
                if total_content_length > 500:  # Lots of content
                    if has_pdf_content and variant_id % 2 == 0:  # Even variants - more general knowledge
                        content_ratio, general_ratio = (60, 40)
                        source_preference = "balanced_toward_general"
                    else:  # Odd variants or no diversification needed - more uploaded content
                        content_ratio, general_ratio = (90, 10)
                        source_preference = f"{content_source_type}_heavy"
                elif total_content_length > 200:  # Moderate content
                    if has_pdf_content and variant_id % 2 == 0:  # Even variants - more general knowledge
                        content_ratio, general_ratio = (40, 60)
                        source_preference = "general_heavy"
                    else:  # Odd variants or no diversification needed - more uploaded content
                        content_ratio, general_ratio = (80, 20)
                        source_preference = f"{content_source_type}_heavy"
                elif total_content_length > 50:   # Some content
                    if has_pdf_content and variant_id % 2 == 0:  # Even variants - more general knowledge
                        content_ratio, general_ratio = (30, 70)
                        source_preference = "general_heavy"
                    else:  # Odd variants or no diversification needed - more uploaded content
                        content_ratio, general_ratio = (70, 30)
                        source_preference = f"{content_source_type}_moderate"
                else:  # Very little content
                    content_ratio, general_ratio = (20, 80)
                    source_preference = "general_only"
                
                context = "\n\n---\n\n".join(passages) if passages else "No relevant content found."
                
                log.info("quiz.content_analysis", 
                        variant_id=variant_id,
                        total_content_length=total_content_length, 
                        content_ratio=content_ratio, 
                        general_ratio=general_ratio,
                        source_preference=source_preference,
                        content_source_type=content_source_type,
                        passages_count=len(passages) if passages else 0)

                # Enhance prompt with variant-specific instructions for better source diversity
                variant_instruction = ""
                if has_pdf_content and total_content_length > 50:
                    if variant_id % 2 == 0:  # Even variants
                        variant_instruction = f"\n\nVARIANT DIVERSIFICATION: This is variant {variant_id}. To ensure variety across variants, focus more on general knowledge questions while still incorporating some {content_source_type} content when highly relevant. Generate {general_ratio}% general knowledge questions and {content_ratio}% {content_source_type}-based questions."
                    else:  # Odd variants
                        variant_instruction = f"\n\nVARIANT DIVERSIFICATION: This is variant {variant_id}. To ensure variety across variants, prioritize {content_source_type} content questions. Generate {content_ratio}% {content_source_type}-based questions and {general_ratio}% general knowledge questions."

                # Strengthen prompt: explicitly require n questions in instructions
                prompt = PROMPT_TMPL.format(
                    n=n, topic=topic, level=level, difficulty=diff,
                    context=context, content_ratio=content_ratio, general_ratio=general_ratio,
                    content_source_type=content_source_type
                ) + variant_instruction + f"\n\nIMPORTANT: You must generate exactly {n} questions in a single JSON array. Do not return fewer."

                raw_response = call_deepseek(prompt, n)
                log.info("quiz.raw_response", variant_id=variant_id, content=raw_response[:300])

                # Continue with existing response processing logic...
                return process_quiz_response(raw_response, n, attempt, max_retries)

            except Exception as e:
                log.error(f"quiz.generation.attempt_failed", attempt=attempt+1, variant_id=variant_id, error=str(e))
                if attempt == max_retries - 1:
                    raise
                continue
                
    except Exception as e:
        log.error("quiz.generation.failed", variant_id=variant_id, error=str(e))
        raise Exception(f"Quiz generation failed for variant {variant_id}: {str(e)}")

def process_quiz_response(raw_response: str, n: int, attempt: int, max_retries: int):
    """Process and clean the LLM response to extract valid quiz questions"""
    try:
        # ---- Clean LLM Output ----
        cleaned = raw_response.strip()

        # Remove any thinking tags or content - enhanced removal
        if "<think>" in cleaned:
            # Remove everything from <think> to </think> including tags
            cleaned = re.sub(r'<think>.*?</think>', '', cleaned, flags=re.DOTALL)
            cleaned = cleaned.strip()
        
        # Also handle incomplete thinking tags (common issue)
        if "<think>" in cleaned and "</think>" not in cleaned:
            # Remove everything from <think> onwards
            think_start = cleaned.find("<think>")
            if think_start != -1:
                cleaned = cleaned[:think_start].strip()
        
        # Remove any remaining partial thinking content
        if cleaned.startswith("</think>"):
            cleaned = cleaned[8:].strip()

        # Remove markdown if present
        if "```json" in cleaned:
            cleaned = cleaned.split("```json", 1)[-1].split("```", 1)[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```", 1)[-1].split("```", 1)[0].strip()

        # Look for JSON content more aggressively
        # Find the JSON array boundaries
        start_idx = cleaned.find("[")
        end_idx = cleaned.rfind("]")
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            cleaned = cleaned[start_idx:end_idx + 1]
        else:
            # If no complete array found, look for individual questions
            if '"stem"' in cleaned:
                # Try to extract from first "stem" to end
                stem_start = cleaned.find('"stem"')
                if stem_start != -1:
                    # Look backwards for opening brace
                    brace_start = cleaned.rfind('{', 0, stem_start)
                    if brace_start != -1:
                        # Extract from opening brace onwards
                        cleaned = cleaned[brace_start:]
                        # Wrap in array if not already
                        if not cleaned.startswith('['):
                            cleaned = f"[{cleaned}]"
                    else:
                        # No opening brace found, wrap the stem content
                        cleaned = f'[{{{cleaned[stem_start:]}}}]'
            elif cleaned.lstrip().startswith('{"stem"'):
                cleaned = f"[{cleaned}]"
            else:
                # Last resort: wrap whatever we have
                if cleaned and not cleaned.startswith('['):
                    cleaned = f"[{cleaned}]"

        log.info("quiz.cleaned_response", content=cleaned[:200])

        # ---- Parse JSON ----
        try:
            questions = json.loads(cleaned)
        except json.JSONDecodeError as je:
            log.error("quiz.json_parse_failed", error=str(je), content=cleaned[:500])
            
            # Try to fix common JSON issues
            if attempt < max_retries - 1:
                # Try to fix incomplete JSON
                if cleaned.count('{') > cleaned.count('}'):
                    missing_braces = cleaned.count('{') - cleaned.count('}')
                    cleaned += '}' * missing_braces
                if cleaned.count('[') > cleaned.count(']'):
                    missing_brackets = cleaned.count('[') - cleaned.count(']')
                    cleaned += ']' * missing_brackets
                
                try:
                    questions = json.loads(cleaned)
                    log.info("quiz.json_fixed", method="bracket_completion")
                except:
                    # Try manual parsing for partial responses
                    questions = manual_parse_questions(cleaned)
            else:
                raise Exception(f"Failed to parse JSON after {max_retries} attempts: {str(je)}")

        # ---- Validate Questions ----
        if not isinstance(questions, list):
            if isinstance(questions, dict) and "stem" in questions:
                questions = [questions]
            else:
                raise Exception(f"Expected list of questions, got {type(questions)}")

        if len(questions) == 0:
            raise Exception("No questions generated")

        # Validate and clean each question
        validated_questions = []
        for i, q in enumerate(questions):
            try:
                validated_q = {
                    "stem": q.get("stem", f"Question {i+1}"),
                    "options": q.get("options", []),
                    "correct_index": q.get("correct_index", 0),
                    "explanation": q.get("explanation", "No explanation provided."),
                    "source": q.get("source", "general")
                }
                
                # Validate options
                if len(validated_q["options"]) < 2:
                    log.warning(f"quiz.question_invalid", index=i, reason="insufficient_options")
                    continue
                
                # Ensure correct_index is valid
                if not (0 <= validated_q["correct_index"] < len(validated_q["options"])):
                    validated_q["correct_index"] = 0
                    log.warning(f"quiz.question_fixed", index=i, fix="correct_index_reset")
                
                validated_questions.append(validated_q)
                
            except Exception as e:
                log.warning(f"quiz.question_skipped", index=i, error=str(e))
                continue

        if len(validated_questions) == 0:
            raise Exception("No valid questions after validation")

        # If we got fewer questions than requested, but at least some valid ones
        if len(validated_questions) < n:
            log.warning("quiz.insufficient_questions", requested=n, generated=len(validated_questions))

        log.info("quiz.generation_success", questions_generated=len(validated_questions), questions_requested=n)
        return validated_questions

    except Exception as e:
        log.error("quiz.response_processing_failed", error=str(e))
        raise

def manual_parse_questions(text: str) -> list:
    """Manually parse questions from malformed JSON"""
    questions = []
    
    # Split on common question boundaries
    question_parts = re.split(r'(?="stem")', text)
    
    for part in question_parts:
        if '"stem"' not in part:
            continue
            
        try:
            # Try to extract a complete question object
            if not part.strip().startswith('{'):
                part = '{' + part
            if not part.strip().endswith('}'):
                part = part + '}'
                
            # Try to parse this individual question
            question = json.loads(part)
            questions.append(question)
        except:
            continue
    
    return questions

def add_variation_to_questions(questions: list, variant_id: int) -> list:
    """Add variation to questions for different variants"""
    import random
    
    # Set a seed based on variant_id for reproducible variations
    random.seed(variant_id * 42)
    
    varied_questions = []
    for question in questions:
        # Create a copy of the question
        varied_question = question.copy()
        
        # Shuffle options but maintain correct answer
        options = varied_question["options"]
        correct_index = varied_question["correct_index"]
        correct_option = options[correct_index]
        
        # Shuffle options
        random.shuffle(options)
        
        # Find new correct index
        new_correct_index = next(i for i, opt in enumerate(options) if opt["text"] == correct_option["text"])
        
        varied_question["options"] = options
        varied_question["correct_index"] = new_correct_index
        
        varied_questions.append(varied_question)
    
    return varied_questions

def detect_content_source_type(session_id: str) -> str:
    """
    Detect the type of content in a session by checking the source metadata.
    Returns the predominant content type: 'pdf', 'article', 'docx', 'pptx', 'txt', or 'mixed'
    """
    try:
        # Import here to avoid circular imports
        from app.services.search import get_session_content_types
        
        content_types = get_session_content_types(session_id)
        log.info("content_source_detection", session_id=session_id, content_types=content_types)
        
        if not content_types:
            return "general"
        
        # Count occurrences of each type
        type_counts = {}
        for content_type in content_types:
            type_counts[content_type] = type_counts.get(content_type, 0) + 1
        
        # If only one type, return it
        if len(type_counts) == 1:
            return list(type_counts.keys())[0]
        
        # If multiple types, check if one is dominant (>70%)
        total_count = sum(type_counts.values())
        for content_type, count in type_counts.items():
            if count / total_count > 0.7:
                return content_type
        
        # If mixed content with no clear dominant type
        return "mixed"
        
    except Exception as e:
        log.warning("content_source_detection.failed", session_id=session_id, error=str(e))
        # Fallback: assume it's PDF content (backward compatibility)
        return "pdf"

def check_topic_relevance(topic: str, passages: list[str], threshold: float = 0.3) -> bool:
    """
    Check if the topic is relevant to the PDF content.
    Returns True if relevant, False if topic should use general knowledge.
    """
    if not passages:
        return False
    
    # Combine all passages
    combined_text = " ".join(passages).lower()
    topic_lower = topic.lower()
    
    # Check for direct keyword matches
    topic_keywords = topic_lower.split()
    
    # Calculate relevance score
    keyword_matches = 0
    total_keywords = len(topic_keywords)
    
    for keyword in topic_keywords:
        if keyword in combined_text:
            keyword_matches += 1
    
    # Calculate relevance ratio
    relevance_ratio = keyword_matches / total_keywords if total_keywords > 0 else 0
    
    # Use only the relevance ratio for determination
    # No hardcoded content assumptions - let the keyword matching decide
    return relevance_ratio >= threshold

def generate_quiz(topic: str, n: int, diff: str, level: str, session_id: str = None):
    """Generate quiz - backward compatibility wrapper"""
    # Call the new variant-aware function with variant_id=1 (default behavior)
    return generate_quiz_with_variant_preference(topic, n, diff, level, session_id, variant_id=1, has_pdf_content=False)

# Additional helper functions would go here...
