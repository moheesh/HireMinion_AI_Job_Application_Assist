"""
HTML Cleaning Module
Extracts visible text and metadata from HTML
"""
import os
import re
import json
from bs4 import BeautifulSoup
from urllib.parse import urlparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOADED_DIR = os.path.join(PROJECT_ROOT, "downloaded")

# Known job board URL patterns: domain -> company position in path
JOB_BOARDS = {
    'greenhouse.io': 0,
    'lever.co': 0,
    'jobs.lever.co': 0,
    'boards.greenhouse.io': 0,
    'myworkdayjobs.com': 0,
    'smartrecruiters.com': 0,
}


def extract_company_from_url(url: str) -> str:
    """Extract company name from job board URLs"""
    parsed = urlparse(url)
    domain = parsed.netloc.lower().replace('www.', '')
    path_parts = [p for p in parsed.path.split('/') if p]
    
    for job_domain, idx in JOB_BOARDS.items():
        if job_domain in domain and len(path_parts) > idx:
            return path_parts[idx].replace('-', ' ').title()
    
    return ""


def extract_company_from_title(title: str) -> str:
    """Extract company name from page title"""
    if not title:
        return ""
    
    # Common patterns: "Job Title at Company" or "Job Title - Company" or "Company | Job Title"
    patterns = [
        r'\bat\s+([A-Z][A-Za-z0-9\s&.]+?)(?:\s*[-|]|$)',
        r'[-|]\s*([A-Z][A-Za-z0-9\s&.]+?)(?:\s*[-|]|$)',
        r'^([A-Z][A-Za-z0-9\s&.]+?)\s*[-|]',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, title)
        if match:
            company = match.group(1).strip()
            # Filter out common non-company words
            if company.lower() not in ['job', 'career', 'careers', 'jobs', 'hiring', 'apply']:
                return company
    
    return ""


def extract_company_from_meta(soup: BeautifulSoup) -> str:
    """Extract company name from meta tags"""
    # Try og:site_name first
    og_site = soup.find('meta', property='og:site_name')
    if og_site and og_site.get('content'):
        return og_site['content']
    
    # Try application-name
    app_name = soup.find('meta', attrs={'name': 'application-name'})
    if app_name and app_name.get('content'):
        return app_name['content']
    
    return ""


def extract_company_from_jsonld(soup: BeautifulSoup) -> str:
    """Extract company name from JSON-LD structured data"""
    scripts = soup.find_all('script', type='application/ld+json')
    
    for script in scripts:
        try:
            data = json.loads(script.string)
            
            # Handle list of objects
            if isinstance(data, list):
                data = data[0] if data else {}
            
            # Look for JobPosting schema
            if data.get('@type') == 'JobPosting':
                org = data.get('hiringOrganization', {})
                if isinstance(org, dict):
                    return org.get('name', '')
                return str(org) if org else ''
            
            # Look for Organization directly
            if data.get('@type') == 'Organization':
                return data.get('name', '')
                
        except (json.JSONDecodeError, TypeError, AttributeError):
            continue
    
    return ""


def extract_metadata(html: str, url: str = "") -> dict:
    """Extract company and job metadata from HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Get page title
    title_tag = soup.find('title')
    title = title_tag.get_text(strip=True) if title_tag else ""
    
    # Try each extraction method in order of reliability
    company = (
        extract_company_from_jsonld(soup) or
        extract_company_from_meta(soup) or
        extract_company_from_url(url) or
        extract_company_from_title(title)
    )
    
    return {
        "company": company,
        "title": title,
    }


def extract_text(html: str) -> str:
    """Extract main content text from HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Remove non-content tags
    for tag in soup(['script', 'style', 'noscript', 'meta', 'link', 'head', 
                     'nav', 'header', 'footer', 'aside', 'form', 'button',
                     'iframe', 'svg', 'img', 'video', 'audio', 'canvas']):
        tag.decompose()
    
    # Remove elements with common non-content roles
    for tag in soup.find_all(attrs={'role': ['navigation', 'banner', 'contentinfo', 'menu', 'menubar', 'toolbar']}):
        tag.decompose()
    
    # Try to find main content container
    main = soup.find('main') or soup.find(attrs={'role': 'main'}) or soup.find(id='content') or soup.find(class_='content') or soup.find('article') or soup.body or soup
    
    return main.get_text(separator='\n', strip=True)


def clean_file(input_filename: str = "html_snapshot.html", output_filename: str = "cleaned.txt") -> dict:
    """Read HTML file, extract text and metadata, and save"""
    input_path = os.path.join(DOWNLOADED_DIR, input_filename)
    output_path = os.path.join(DOWNLOADED_DIR, output_filename)
    meta_path = os.path.join(DOWNLOADED_DIR, "metadata.json")
    
    with open(input_path, 'r', encoding='utf-8') as f:
        html = f.read()
    
    # Load existing metadata (has URL)
    url = ""
    existing_meta = {}
    if os.path.exists(meta_path):
        with open(meta_path, 'r', encoding='utf-8') as f:
            existing_meta = json.load(f)
            url = existing_meta.get('url', '')
    
    # Extract text
    text = extract_text(html)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(text)
    
    # Extract and merge metadata
    extracted = extract_metadata(html, url)
    existing_meta.update(extracted)
    
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(existing_meta, f, indent=2)
    
    return {
        "text_path": output_path,
        "metadata": existing_meta
    }


if __name__ == "__main__":
    result = clean_file()
    print(f"✅ Saved to {result['text_path']}")
    print(f"📋 Metadata: {json.dumps(result['metadata'], indent=2)}")