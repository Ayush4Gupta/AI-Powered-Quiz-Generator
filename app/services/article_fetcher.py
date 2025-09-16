# article_fetcher.py
"""
Service for fetching and extracting content from article URLs
"""
import httpx
import structlog
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import re
import time
import random
from dataclasses import dataclass

log = structlog.get_logger()

@dataclass
class ArticleContent:
    """Represents extracted article content"""
    url: str
    title: str
    content: str
    author: Optional[str] = None
    publish_date: Optional[str] = None
    word_count: int = 0
    extraction_method: str = "basic"
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        self.word_count = len(self.content.split()) if self.content else 0

class ArticleFetcher:
    """Fetches and extracts content from article URLs"""
    
    def __init__(self):
        self.session = httpx.Client(
            timeout=30.0,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
        )
    
    def fetch_article(self, url: str) -> Optional[ArticleContent]:
        """Fetch and extract content from a single article URL"""
        try:
            log.info("article.fetch.start", url=url)
            
            # Validate URL
            if not self._is_valid_url(url):
                log.error("article.fetch.invalid_url", url=url)
                return None
            
            # Add random delay to be respectful
            time.sleep(random.uniform(0.5, 1.5))
            
            # Fetch the page
            response = self.session.get(url)
            response.raise_for_status()
            
            # Check content type
            content_type = response.headers.get('content-type', '').lower()
            if 'text/html' not in content_type:
                log.warning("article.fetch.not_html", url=url, content_type=content_type)
                return None
            
            # Extract content
            article = self._extract_content(url, response.text)
            
            if article and article.content and len(article.content.strip()) > 100:
                log.info("article.fetch.success", 
                        url=url, 
                        title=article.title[:50] if article.title else "No title",
                        word_count=article.word_count,
                        method=article.extraction_method)
                return article
            else:
                log.warning("article.fetch.insufficient_content", url=url)
                return None
                
        except httpx.TimeoutException:
            log.error("article.fetch.timeout", url=url)
            return None
        except httpx.HTTPStatusError as e:
            log.error("article.fetch.http_error", url=url, status_code=e.response.status_code)
            return None
        except Exception as e:
            log.error("article.fetch.error", url=url, error=str(e))
            return None
    
    def fetch_multiple_articles(self, urls: List[str], max_articles: int = 10) -> List[ArticleContent]:
        """Fetch content from multiple article URLs"""
        articles = []
        
        log.info("article.fetch.multiple.start", url_count=len(urls), max_articles=max_articles)
        
        # Limit the number of URLs to process
        urls_to_process = urls[:max_articles]
        
        for i, url in enumerate(urls_to_process, 1):
            log.info("article.fetch.progress", current=i, total=len(urls_to_process), url=url)
            
            article = self.fetch_article(url)
            if article:
                articles.append(article)
            
            # Add delay between requests to be respectful
            if i < len(urls_to_process):
                time.sleep(random.uniform(1.0, 2.0))
        
        log.info("article.fetch.multiple.complete", 
                total_urls=len(urls_to_process), 
                successful=len(articles),
                failed=len(urls_to_process) - len(articles))
        
        return articles
    
    def _is_valid_url(self, url: str) -> bool:
        """Validate if URL is properly formatted and accessible"""
        try:
            parsed = urlparse(url)
            return all([parsed.scheme, parsed.netloc]) and parsed.scheme in ['http', 'https']
        except Exception:
            return False
    
    def _extract_content(self, url: str, html: str) -> Optional[ArticleContent]:
        """Extract article content from HTML using multiple methods"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Try multiple extraction methods in order of preference
            methods = [
                self._extract_with_article_tags,
                self._extract_with_schema_org,
                self._extract_with_common_selectors,
                self._extract_with_heuristics
            ]
            
            for method in methods:
                try:
                    article = method(url, soup)
                    if article and article.content and len(article.content.strip()) > 100:
                        return article
                except Exception as e:
                    log.debug("article.extraction_method.failed", method=method.__name__, error=str(e))
                    continue
            
            log.warning("article.extraction.all_methods_failed", url=url)
            return None
            
        except Exception as e:
            log.error("article.extraction.error", url=url, error=str(e))
            return None
    
    def _extract_with_article_tags(self, url: str, soup: BeautifulSoup) -> Optional[ArticleContent]:
        """Extract using HTML5 article tags"""
        article_tag = soup.find('article')
        if not article_tag:
            return None
        
        # Extract title
        title = self._extract_title(soup)
        
        # Extract content from article tag
        content_parts = []
        for p in article_tag.find_all(['p', 'div', 'section'], recursive=True):
            text = p.get_text(strip=True)
            if text and len(text) > 20:
                content_parts.append(text)
        
        content = '\n\n'.join(content_parts)
        
        if len(content.strip()) > 100:
            return ArticleContent(
                url=url,
                title=title,
                content=content,
                extraction_method="article_tags"
            )
        
        return None
    
    def _extract_with_schema_org(self, url: str, soup: BeautifulSoup) -> Optional[ArticleContent]:
        """Extract using Schema.org microdata"""
        # Look for JSON-LD structured data
        scripts = soup.find_all('script', {'type': 'application/ld+json'})
        
        for script in scripts:
            try:
                import json
                data = json.loads(script.string)
                
                if isinstance(data, list):
                    data = data[0]
                
                if data.get('@type') in ['Article', 'NewsArticle', 'BlogPosting']:
                    title = data.get('headline', '')
                    content = data.get('articleBody', '')
                    author = data.get('author', {}).get('name', '') if isinstance(data.get('author'), dict) else ''
                    
                    if content and len(content.strip()) > 100:
                        return ArticleContent(
                            url=url,
                            title=title,
                            content=content,
                            author=author,
                            extraction_method="schema_org"
                        )
            except:
                continue
        
        return None
    
    def _extract_with_common_selectors(self, url: str, soup: BeautifulSoup) -> Optional[ArticleContent]:
        """Extract using common CSS selectors"""
        title = self._extract_title(soup)
        
        # Common content selectors
        selectors = [
            '.post-content, .entry-content, .article-content, .content',
            '.post-body, .entry-body, .article-body',
            '[class*="content"], [class*="article"], [class*="post"]',
            'main, #main, .main',
            '[role="main"]'
        ]
        
        for selector in selectors:
            try:
                elements = soup.select(selector)
                for element in elements:
                    content_parts = []
                    for p in element.find_all(['p', 'div', 'section']):
                        text = p.get_text(strip=True)
                        if text and len(text) > 20:
                            content_parts.append(text)
                    
                    content = '\n\n'.join(content_parts)
                    if len(content.strip()) > 100:
                        return ArticleContent(
                            url=url,
                            title=title,
                            content=content,
                            extraction_method="common_selectors"
                        )
            except:
                continue
        
        return None
    
    def _extract_with_heuristics(self, url: str, soup: BeautifulSoup) -> Optional[ArticleContent]:
        """Extract using text density heuristics"""
        title = self._extract_title(soup)
        
        # Remove unwanted elements
        for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'menu']):
            element.decompose()
        
        # Find all paragraph-like elements
        candidates = []
        for tag in soup.find_all(['p', 'div', 'section', 'article']):
            text = tag.get_text(strip=True)
            if len(text) > 50:  # Minimum text length
                candidates.append(text)
        
        # Combine meaningful paragraphs
        content = '\n\n'.join(candidates)
        
        if len(content.strip()) > 100:
            return ArticleContent(
                url=url,
                title=title,
                content=content,
                extraction_method="heuristics"
            )
        
        return None
    
    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract article title using multiple methods"""
        # Try different title extraction methods
        title_methods = [
            lambda: soup.find('h1').get_text(strip=True) if soup.find('h1') else '',
            lambda: soup.find('title').get_text(strip=True) if soup.find('title') else '',
            lambda: soup.find('meta', {'property': 'og:title'})['content'] if soup.find('meta', {'property': 'og:title'}) else '',
            lambda: soup.find('meta', {'name': 'twitter:title'})['content'] if soup.find('meta', {'name': 'twitter:title'}) else '',
        ]
        
        for method in title_methods:
            try:
                title = method()
                if title and len(title.strip()) > 5:
                    return title.strip()
            except:
                continue
        
        return "Untitled Article"
    
    def __del__(self):
        """Clean up the HTTP session"""
        try:
            self.session.close()
        except:
            pass

# Global instance
article_fetcher = ArticleFetcher()
