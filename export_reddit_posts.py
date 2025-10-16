#!/usr/bin/env python3
"""
Reddit Post Exporter for StreetWatch Chicago
Exports Reddit posts from CSV as individual markdown files and consolidates them.

This script reads the CSV file, extracts Reddit URLs, downloads each post as markdown,
and creates a consolidated file with row numbers for Gemini analysis.
"""

import csv
import json
import os
import sys
import time
from typing import Optional, Dict, List, Tuple
from urllib.parse import urlparse
import requests


class RedditPostExporter:
    """Exports Reddit posts to markdown format with row tracking."""
    
    # CORS proxy configurations
    PROXY_CONFIG = {
        'codetabs': {
            'name': 'CodeTabs',
            'url_template': 'https://api.codetabs.com/v1/proxy?quest={url}'
        },
        'corslol': {
            'name': 'CORS.lol',
            'url_template': 'https://api.cors.lol/?url={url}'
        },
        'direct': {
            'name': 'Direct',
            'url_template': '{url}'
        }
    }
    
    AUTO_PROXY_ORDER = ['codetabs', 'corslol', 'direct']
    
    def __init__(self, csv_file: str, output_dir: str = 'reddit_exports', 
                 consolidated_file: str = 'consolidated_reddit_posts.md',
                 use_proxy: str = 'auto'):
        """
        Initialize the exporter.
        
        Args:
            csv_file: Path to the CSV file with Reddit URLs
            output_dir: Directory to save individual markdown files
            consolidated_file: Name of the consolidated markdown file
            use_proxy: Proxy mode ('auto', 'codetabs', 'corslol', 'direct')
        """
        self.csv_file = csv_file
        self.output_dir = output_dir
        self.consolidated_file = consolidated_file
        self.use_proxy = use_proxy
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
    def format_reddit_json_url(self, url: str) -> str:
        """Convert Reddit URL to JSON API format."""
        if '.json' in url:
            return url
            
        # Find query parameters and fragments
        query_index = url.find('?')
        fragment_index = url.find('#')
        
        insert_index = len(url)
        if query_index != -1:
            insert_index = min(insert_index, query_index)
        if fragment_index != -1:
            insert_index = min(insert_index, fragment_index)
            
        base_url = url[:insert_index]
        remainder = url[insert_index:]
        
        # Remove trailing slash
        if base_url.endswith('/'):
            base_url = base_url[:-1]
            
        return f"{base_url}.json{remainder}"
    
    def fetch_with_proxy(self, reddit_url: str, proxy_key: str) -> Optional[List]:
        """Fetch Reddit data using specified proxy."""
        config = self.PROXY_CONFIG[proxy_key]
        request_url = config['url_template'].format(url=reddit_url)
        
        print(f"  Trying {config['name']}...", end=' ')
        
        try:
            headers = {
                'User-Agent': 'StreetWatchChicago/1.0 (Educational Research Project)'
            }
            response = requests.get(request_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # Validate Reddit data structure
                if (isinstance(data, list) and len(data) >= 2 and
                    data[0].get('data', {}).get('children') and
                    data[1].get('data', {}).get('children')):
                    print(f"✅ Success")
                    return data
                else:
                    print(f"❌ Invalid structure")
                    return None
            else:
                print(f"❌ HTTP {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Error: {str(e)[:50]}")
            return None
    
    def fetch_reddit_data(self, url: str) -> Optional[List]:
        """Fetch Reddit post data with automatic proxy fallback."""
        reddit_url = self.format_reddit_json_url(url)
        
        if self.use_proxy == 'auto':
            # Try each proxy in sequence
            for proxy_key in self.AUTO_PROXY_ORDER:
                data = self.fetch_with_proxy(reddit_url, proxy_key)
                if data:
                    return data
                time.sleep(1)  # Brief delay between attempts
            return None
        else:
            # Use specific proxy
            return self.fetch_with_proxy(reddit_url, self.use_proxy)
    
    def format_comment(self, comment: Dict, depth: int = 0, style: str = 'tree') -> str:
        """Format a comment and its replies as markdown."""
        output = []
        
        if not comment.get('data', {}).get('body'):
            return ''
        
        data = comment['data']
        
        # Format based on style
        if style == 'tree':
            depth_tag = '─' * depth
            if depth_tag:
                output.append(f"├{depth_tag} ")
            else:
                output.append("##### ")
        else:
            depth_tag = '\t' * depth
            if depth_tag:
                output.append(f"{depth_tag}- ")
            else:
                output.append("- ")
        
        # Add comment content
        body = data.get('body', 'deleted')
        author = data.get('author', '[deleted]')
        ups = data.get('ups', 0)
        downs = data.get('downs', 0)
        
        output.append(f"{body} ⏤ by *{author}* (↑ {ups}/ ↓ {downs})\n")
        
        # Process replies
        if data.get('replies') and isinstance(data['replies'], dict):
            sub_comments = data['replies'].get('data', {}).get('children', [])
            for sub_comment in sub_comments:
                output.append(self.format_comment(sub_comment, depth + 1, style))
        
        # Add separator for top-level comments
        if depth == 0 and data.get('replies'):
            if style == 'tree':
                output.append('└────\n\n')
            else:
                output.append('\n')
        
        return ''.join(output)
    
    def reddit_to_markdown(self, data: List, style: str = 'tree') -> str:
        """Convert Reddit JSON data to markdown format."""
        output = []
        
        # Extract post data
        post = data[0]['data']['children'][0]['data']
        
        # Title and content
        output.append(f"# {post.get('title', 'Untitled')}\n\n")
        
        if post.get('selftext'):
            output.append(f"{post['selftext']}\n\n")
        
        # Metadata
        output.append(f"[permalink](https://reddit.com{post.get('permalink', '')})\n")
        output.append(f"by *{post.get('author', '[deleted]')}* ")
        output.append(f"(↑ {post.get('ups', 0)}/ ↓ {post.get('downs', 0)})\n\n")
        
        # Comments
        output.append("## Comments\n\n")
        comments = data[1]['data']['children']
        
        for comment in comments:
            if comment.get('kind') == 't1':  # It's a comment
                output.append(self.format_comment(comment, style=style))
        
        return ''.join(output)
    
    def is_reddit_url(self, url: str) -> bool:
        """Check if URL is a Reddit post."""
        if not url:
            return False
        parsed = urlparse(url)
        return 'reddit.com' in parsed.netloc and '/comments/' in parsed.path
    
    def export_posts(self, max_posts: Optional[int] = None) -> Tuple[int, int, List[str]]:
        """
        Export all Reddit posts from CSV.
        
        Args:
            max_posts: Maximum number of posts to export (None = all)
            
        Returns:
            Tuple of (successful_count, failed_count, failed_urls)
        """
        successful = 0
        failed = 0
        failed_urls = []
        
        print(f"Reading CSV file: {self.csv_file}")
        print(f"Output directory: {self.output_dir}")
        print(f"Proxy mode: {self.use_proxy}\n")
        
        with open(self.csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        print(f"Found {len(rows)} rows in CSV\n")
        
        # Filter Reddit URLs
        reddit_rows = [(i+2, row) for i, row in enumerate(rows) 
                      if self.is_reddit_url(row.get('SourceURL', ''))]
        
        print(f"Found {len(reddit_rows)} Reddit URLs\n")
        
        if max_posts:
            reddit_rows = reddit_rows[:max_posts]
            print(f"Limiting to first {max_posts} posts\n")
        
        # Export each post
        for row_num, row in reddit_rows:
            url = row['SourceURL']
            print(f"\n[Row {row_num}] {url}")
            
            # Fetch data
            data = self.fetch_reddit_data(url)
            
            if data:
                # Convert to markdown
                markdown = self.reddit_to_markdown(data)
                
                # Save individual file
                filename = f"row_{row_num:03d}.md"
                filepath = os.path.join(self.output_dir, filename)
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(f"<!-- CSV Row: {row_num} -->\n")
                    f.write(f"<!-- Source: {url} -->\n")
                    f.write(f"<!-- Extracted Location: {row.get('Title', 'N/A')} -->\n")
                    f.write(f"<!-- Coordinates: {row.get('Latitude', 'N/A')}, {row.get('Longitude', 'N/A')} -->\n\n")
                    f.write(markdown)
                
                print(f"  ✅ Saved to {filename}")
                successful += 1
                
                # Rate limiting
                time.sleep(2)
            else:
                print(f"  ❌ Failed to fetch")
                failed += 1
                failed_urls.append((row_num, url))
        
        return successful, failed, failed_urls
    
    def consolidate_files(self) -> str:
        """Consolidate all markdown files into one large file."""
        print(f"\nConsolidating files into {self.consolidated_file}...")
        
        files = sorted([f for f in os.listdir(self.output_dir) if f.endswith('.md')])
        
        with open(self.consolidated_file, 'w', encoding='utf-8') as outfile:
            outfile.write("# Consolidated Reddit Posts for StreetWatch Chicago\n\n")
            outfile.write("This file contains all Reddit posts from the CSV for analysis.\n")
            outfile.write("Each post shows the CSV row number and extracted location data.\n\n")
            outfile.write(f"Total posts: {len(files)}\n\n")
            outfile.write("---\n\n")
            
            for filename in files:
                filepath = os.path.join(self.output_dir, filename)
                
                with open(filepath, 'r', encoding='utf-8') as infile:
                    content = infile.read()
                    outfile.write(content)
                    outfile.write("\n\n---\n\n")
        
        print(f"✅ Consolidated {len(files)} files")
        return self.consolidated_file


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Export Reddit posts from CSV to markdown files'
    )
    parser.add_argument(
        'csv_file',
        help='Path to CSV file (default: data/map_data.csv)',
        nargs='?',
        default='data/map_data.csv'
    )
    parser.add_argument(
        '--output-dir',
        default='reddit_exports',
        help='Output directory for individual files'
    )
    parser.add_argument(
        '--consolidated',
        default='consolidated_reddit_posts.md',
        help='Consolidated output file'
    )
    parser.add_argument(
        '--proxy',
        choices=['auto', 'codetabs', 'corslol', 'direct'],
        default='auto',
        help='Proxy mode to use'
    )
    parser.add_argument(
        '--max-posts',
        type=int,
        help='Maximum number of posts to export'
    )
    
    args = parser.parse_args()
    
    # Create exporter
    exporter = RedditPostExporter(
        csv_file=args.csv_file,
        output_dir=args.output_dir,
        consolidated_file=args.consolidated,
        use_proxy=args.proxy
    )
    
    # Export posts
    successful, failed, failed_urls = exporter.export_posts(max_posts=args.max_posts)
    
    # Consolidate files
    consolidated_path = None
    if successful > 0:
        consolidated_path = exporter.consolidate_files()
    
    # Summary
    print("\n" + "="*60)
    print("EXPORT SUMMARY")
    print("="*60)
    print(f"✅ Successful: {successful}")
    print(f"❌ Failed: {failed}")
    
    if failed_urls:
        print("\nFailed URLs:")
        for row_num, url in failed_urls:
            print(f"  Row {row_num}: {url}")
    
    if successful > 0 and consolidated_path:
        print(f"\n📄 Individual files: {args.output_dir}/")
        print(f"📄 Consolidated file: {consolidated_path}")
        print("\nNext steps:")
        print("1. Review the consolidated file")
        print("2. Upload to Google Gemini 2.5 Pro for analysis")
        print("3. Use with pipeline_description.md for full context")
    
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
