"""
read_webpage.py — Lightweight webpage scraper for the Nexus Engine.
Uses trafilatura to extract clean, boilerplate-free markdown content from URLs.
"""
import sys
import argparse
import trafilatura
from typing import Optional

def scrape_url(url: str, output_format: str = "markdown") -> Optional[str]:
    """
    Scrapes a URL and returns clean content.
    Supported formats: 'markdown', 'txt', 'xml', 'csv', 'json'
    """
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded is None:
            print(f"Error: Could not fetch content from {url}", file=sys.stderr)
            return None
        
        # Extract content
        # include_comments=False, include_tables=True, include_images=False are defaults for 'clean' capture
        result = trafilatura.extract(
            downloaded, 
            output_format=output_format,
            include_comments=False,
            include_tables=True,
            include_links=True
        )
        
        return result
    except Exception as e:
        print(f"Exception while scraping {url}: {e}", file=sys.stderr)
        return None

def main():
    parser = argparse.ArgumentParser(description="Lightweight webpage reader for Nexus Engine.")
    parser.add_argument("url", help="The URL to scrape")
    parser.add_argument("-o", "--output", help="Path to save the output (optional)")
    parser.add_argument("-f", "--format", choices=["markdown", "txt", "json", "xml"], default="markdown", help="Output format (default: markdown)")
    
    args = parser.parse_args()
    
    content = scrape_url(args.url, output_format=args.format)
    
    if content:
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Successfully saved content to {args.output}")
        else:
            # Handle Windows console encoding
            if sys.stdout.encoding != 'utf-8':
                sys.stdout.reconfigure(encoding='utf-8')
            print(content)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
