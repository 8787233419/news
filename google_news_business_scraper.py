import requests
import pandas as pd
from bs4 import BeautifulSoup
import asyncio
from playwright.async_api import async_playwright
import json
from datetime import datetime, timedelta, timezone
from dateutil import parser as date_parser
import sys
import time
import re
from isin import extract_company_simple
from isin_matcher import get_isin_for_company
from prompts import summarize_multiple_articles, print_summary_results
import os
from dotenv import load_dotenv

load_dotenv()

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass


MIN_ARTICLE_LENGTH = 200

def fetch_business_news_rss(processed_articles):
    """Fetch top business news from Google News RSS feed, filtering out already processed articles"""
    print("=" * 70)
    print("📰 Google News Business Section Scraper (RSS Method)")
    print("=" * 70)
    
    print("\n📡 Fetching Google News Business RSS feed...")
    
    
    rss_url = "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtVnVHZ0pWVXlnQVAB?hl=en-IN&gl=IN&ceid=IN:en"
    
    try:
        resp = requests.get(rss_url, timeout=10)
        resp.raise_for_status()
        
        # Parse RSS XML
        soup = BeautifulSoup(resp.content, 'xml')
        items = soup.find_all('item')
        
        print(f"✅ Found {len(items)} news items in RSS feed")
        
        articles_data = []
        skipped_count = 0
        
      
        current_time = datetime.now()
        time_window_minutes = 1440  # 24 hours - matches RSS feed, dedup handles rest
        cutoff_time = current_time - timedelta(minutes=time_window_minutes)
        
        print(f"⏰ Filtering articles from last {time_window_minutes} minutes")
        print(f"   Cutoff time: {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        time_filtered_count = 0
        
        parse_errors = 0
        
        for idx, item in enumerate(items):  # Process ALL items, no [:10] limit
            try:
                title = item.find('title').get_text() if item.find('title') else "No Title"
                link = item.find('link').get_text() if item.find('link') else None
                pub_date = item.find('pubDate').get_text() if item.find('pubDate') else "Unknown"
                source_elem = item.find('source')
                source = source_elem.get_text() if source_elem else "Unknown"
                
                if link:
                
                    date_parse_failed = False
                    try:
                        article_time = date_parser.parse(pub_date)
                 
                        if article_time.tzinfo is not None:
                            article_time = article_time.replace(tzinfo=None)
                        
                     
                        if idx < 3:
                            print(f"   [DEBUG] Article {idx+1}: {title[:50]}...")
                            print(f"           Published: {article_time.strftime('%Y-%m-%d %H:%M:%S')}")
                            print(f"           Age: {(current_time - article_time).total_seconds()/3600:.1f} hours old")
                        
                        # Skip articles older than cutoff time
                        if article_time < cutoff_time:
                            time_filtered_count += 1
                            continue
                    except Exception as e:
                   
                        date_parse_failed = True
                        parse_errors += 1
                        if idx < 3:
                            print(f"   [DEBUG] Article {idx+1}: Could not parse date '{pub_date}'")
                    
                    # Create unique identifier for article
                    article_id = (title, source)
                    
    
                    if article_id in processed_articles:
                        skipped_count += 1
                        continue
                    
                    articles_data.append({
                        'title': title,
                        'link': link,
                        'source': source,
                        'pub_date': pub_date,
                        'article_id': article_id
                    })
                    
              
            except Exception as e:
                continue
        
        if parse_errors > 0:
            print(f"⚠️  Warning: Could not parse date for {parse_errors} article(s) (included anyway)")
        
        if time_filtered_count > 0:
            print(f"⏰ Filtered out {time_filtered_count} article(s) older than {time_window_minutes} minutes")
        
        if skipped_count > 0:
            print(f"⏭️  Skipped {skipped_count} already-processed article(s)")
        
        print(f"\n📊 FILTERING SUMMARY:")
        print(f"   Total RSS items: {len(items)}")
        print(f"   Filtered by time: {time_filtered_count}")
        print(f"   Already processed: {skipped_count}")
        print(f"   Parse errors: {parse_errors}")
        print(f"   ✅ NEW articles to scrape: {len(articles_data)}")
        
        return articles_data
        
    except Exception as e:
        print(f"❌ Error fetching RSS feed: {e}")
        return []

async def get_story_url(page, google_news_url):
    """Follow Google News RSS link - it will redirect to the actual article source"""
    try:
  
        await page.goto(google_news_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        
       
        return [page.url] if page.url else None
        
    except Exception as e:
        print(f"         ❌ Error: {str(e)[:60]}...")
        return None

async def scrape_article_content(url, page):
    """Scrape full article text from a URL using Playwright"""
    try:
        await page.goto(url, timeout=120000, wait_until="domcontentloaded")
        await asyncio.sleep(2)
        
        content = await page.content()
        soup = BeautifulSoup(content, "html.parser")
        
        # Remove unwanted elements (from rs.py approach)
        for element in soup.find_all(['script', 'style', 'nav', 'header', 'footer', 'aside', 'iframe']):
            element.decompose()
        
        # Extract paragraphs (from test2.py approach)
        paragraphs = soup.find_all("p")
        text = " ".join([p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 30])
        
        return text.strip() if text else "NO_CONTENT"
        
    except Exception as e:
        return f"ERROR: {str(e)[:100]}"

async def resolve_google_news_url(page, google_url):
    """Resolve a Google News article URL to the actual source URL"""
    try:
        await page.goto(google_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        
        final_url = page.url
        
        # If redirected away from Google News, we got the real URL
        if 'news.google.com' not in final_url:
            return final_url
        
        # Otherwise try to find external links
        try:
            external_links = await page.locator('a[href^="http"]:not([href*="google.com"])').all()
            for link in external_links[:3]:
                href = await link.get_attribute('href')
                if href and 'google.com' not in href:
                    return href
        except:
            pass
        
        return None
    except:
        return None

async def scrape_all_articles(articles):
    """Scrape full content from all article URLs using Playwright"""
    if not articles:
        print("⚠️  No articles to scrape")
        return []
    
    print(f"\n📰 Starting to scrape {len(articles)} stories...\n")
    
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        scraped_articles = []
        
        for i, article in enumerate(articles, 1):
            google_news_url = article['link']
            title = article['title']
            
            print(f"   [{i}/{len(articles)}] Processing Story: {article['source']}")
            print(f"      Title: {title[:60]}...")
            
            # Get article URL from RSS (will redirect to source)
            story_urls = []
            if 'news.google.com' in google_news_url:
                print(f"      🔗 Following RSS redirect to source...")
                story_urls = await get_story_url(page, google_news_url)
                
                if story_urls:
                    print(f"      ✅ Found article: {story_urls[0][:60]}...")
                else:
                    print(f"      ⚠️  Could not get article URL, skipping story...\n")
                    continue
            else:
                # Direct URL, not a Google News link
                story_urls = [google_news_url]
                print(f"      Direct article URL: {google_news_url[:70]}...")
            
            # Scrape all articles for this story
            for url_idx, url in enumerate(story_urls, 1):
                print(f"      📄 Article {url_idx}/{len(story_urls)}: Scraping content...")
                
                # Scrape the article content
                full_article = await scrape_article_content(url, page)
                article_length = len(full_article) if not full_article.startswith("ERROR") and not full_article.startswith("NO_CONTENT") else 0
                
                # Extract domain from URL
                from urllib.parse import urlparse
                domain = urlparse(url).netloc.replace('www.', '')
                
                # Extract company name using Gemini AI
                company_name = ""
                if article_length > MIN_ARTICLE_LENGTH:
                    print(f"         🤖 Extracting company name with AI...")
                    company_name = extract_company_simple(full_article, title)
                    if company_name:
                        print(f"         ✅ Company: {company_name}")
                    else:
                        print(f"         ⚠️  No company identified")
                
                scraped_articles.append({
                    "title": title,
                    "source": article['source'],
                    "domain": domain,
                    "url": url,
                    "pub_date": article['pub_date'],
                    "full_article": full_article,
                    "article_length": article_length,
                    "company_name": company_name,
                    "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "story_index": i,
                    "article_index": url_idx
                })
                
                if article_length > 0:
                    print(f"         ✅ Scraped {article_length} characters")
                else:
                    print(f"         ⚠️  Failed to scrape content")
                
                # Small delay between requests
                await asyncio.sleep(1)
            
            print()  # Blank line between stories
        
        await browser.close()
        print(f"📊 Total articles scraped: {len(scraped_articles)}")
        return scraped_articles

def print_json_results(articles):
    """Print articles in JSON format: source -> full article"""
    if not articles:
        print("\n⚠️  No articles to display!")
        return
    
    # Filter out failed scrapes and short articles
    valid_articles = [
        article for article in articles
        if not article["full_article"].startswith("ERROR") 
        and not article["full_article"].startswith("NO_CONTENT")
        and article["article_length"] > MIN_ARTICLE_LENGTH
    ]
    
    filtered_count = len(articles) - len(valid_articles)
    if filtered_count > 0:
        print(f"🗑️  Filtered out {filtered_count} articles (errors or too short)\n")
    
    if not valid_articles:
        print("⚠️  No valid articles after filtering!")
        return
    
    # Group articles by story
    stories = {}
    for article in valid_articles:
        story_idx = article.get("story_index", 1)
        if story_idx not in stories:
            stories[story_idx] = []
        stories[story_idx].append(article)
    
    # Collect unique companies
    companies_found = {}
    
    for article in valid_articles:
        company = article.get("company_name", "")
        if company:
            if company not in companies_found:
                companies_found[company] = []
            companies_found[company].append({
                "source": article.get("domain", article["source"]),
                "title": article["title"]
            })
    
    print("=" * 70)
    print(f"📰 BUSINESS NEWS STORIES")
    print("=" * 70)
    print(f"\n✅ Found {len(stories)} stories with {len(valid_articles)} total articles\n")
    
    # Show companies identified
    if companies_found:
        print("🏢 COMPANIES IDENTIFIED:")
        for company, articles_list in companies_found.items():
            print(f"   • {company} ({len(articles_list)} article(s))")
        print()
    
    # Print stories with their articles
    print("📄 STORIES & ARTICLES:")
    for story_idx in sorted(stories.keys()):
        story_articles = stories[story_idx]
        print(f"\n📖 Story #{story_idx}: {story_articles[0]['title'][:70]}...")
        print(f"   Sources: {len(story_articles)}")
        for idx, article in enumerate(story_articles, 1):
            company = article.get("company_name", "Unknown")
            domain = article.get("domain", article["source"])
            print(f"   [{idx}] {domain} - Company: {company}")
    
    # Create JSON structure
    result = {}
    for story_idx in sorted(stories.keys()):
        story_articles = stories[story_idx]
        story_key = f"story_{story_idx}"
        result[story_key] = {
            "title": story_articles[0]["title"],
            "articles": []
        }
        for article in story_articles:
            result[story_key]["articles"].append({
                "source": article.get("domain", article["source"]),
                "url": article["url"],
                "company": article.get("company_name", "Unknown"),
                "article_preview": article["full_article"][:100] + "..."
            })
    
    print("\n" + "=" * 70)
    print("📄 FULL RESULTS (JSON):")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # Print statistics
    print("\n" + "=" * 70)
    print("📊 STATISTICS:")
    total_chars = sum(article["article_length"] for article in valid_articles)
    avg_chars = total_chars / len(valid_articles) if valid_articles else 0
    print(f"   Total stories: {len(stories)}")
    print(f"   Total articles: {len(valid_articles)}")
    print(f"   Avg articles per story: {len(valid_articles)/len(stories):.1f}")
    print(f"   Companies identified: {len(companies_found)}")
    print(f"   Average article length: {avg_chars:.0f} characters")
    print(f"   Total content: {total_chars:,} characters")
    print("=" * 70)

def send_slack_message(message):
    slack_url=os.getenv("SLACK_URL")

    if(slack_url):
        # If a list is provided, send one Slack message per item
        if isinstance(message, list):
            for idx, item in enumerate([m for m in message if m and isinstance(m, str)], 1):
                payload = {"text": item}
                response = requests.post(slack_url, json=payload)
                if response.status_code==200:
                    print(f"Slack message {idx} sent successfully")
                else:
                    print(f"Failed to send Slack message {idx}: {response.status_code}")
                    print(f"Error: {response.text}")
        else:
            text = str(message)
            payload = {"text": text}
            response = requests.post(slack_url, json=payload)
            if response.status_code==200:
                print("Slack message sent successfully")
            else:
                print(f"Failed to send Slack message: {response.status_code}")
                print(f"Error: {response.text}")

    else:
        print("SLACK_URL not found in .env file")

def format_slack_message_from_article(article: dict) -> str:
    """Builds a Slack-ready text message with required lines.
    Lines:
    1) Company name
    2) Summary
    3) Industry
    4) Link
    5) Release Time (if available)
    """
    company = (
        article.get("matched_company_name")
        or article.get("company_name")
        or "Unknown Company"
    )
    summary = (
        (article.get("ai_summary", {}) or {}).get("summary")
        or "No summary available"
    )
    industry = article.get("industry", "Unknown")
    url = article.get("url", "")
    pub_date_raw = article.get("pub_date")

    release_time_line = ""
    try:
        if pub_date_raw:
            dt = date_parser.parse(pub_date_raw)
            # Convert to IST (UTC+5:30)
            ist = timezone(timedelta(hours=5, minutes=30))
            if dt.tzinfo is None:
                # If no timezone info, assume UTC
                dt = dt.replace(tzinfo=timezone.utc)
            dt_ist = dt.astimezone(ist)
            release_time_line = f"\nRelease Time: {dt_ist.strftime('%d-%m-%Y %H:%M:%S')} IST"
    except Exception:
        # If parsing fails, omit the release time line
        release_time_line = ""

    # Optional fields
    sentiment = (
        article.get("sentiment")
        or (article.get("ai_summary", {}) or {}).get("sentiment")
        or ""
    )

    lines = [
        f"*{company}*",  # whole first line bold
        f"*Summary:* {summary}",
    ]

    if sentiment:
        lines.append(f"*Sentiment:* {sentiment}")

    lines.append(f"*Industry:* {industry}")

    if url:
        lines.append(f"*Link:* {url}")

    message = "\n".join(lines) + (f"\n*Release Time:* {release_time_line.split(': ',1)[1]}" if release_time_line else "")
    message += "\n------------------------------"
    return message

async def main(processed_articles_set):
    # Fetch business news from RSS (filtering out already processed articles)
    articles = fetch_business_news_rss(processed_articles_set)
    
    if not articles:
        print("\n⚠️  No new articles found in RSS feed.")
        return []
    
    # Scrape full content from each article
    scraped_articles = await scrape_all_articles(articles)
    
    if scraped_articles:
        # Print results in JSON format
        # print(scraped_articles)
        print_json_results(scraped_articles)
        
        # STEP 1: Get ISIN matches for all companies found (BEFORE summarization)
        print("\n" + "=" * 70)
        print("🔍 STEP 1: FINDING ISIN MATCHES FOR COMPANIES")
        print("=" * 70)
        
        # Collect unique companies and map them to articles
        company_to_articles = {}
        for article in scraped_articles:
            company = article.get("company_name", "")
            if company:
                if company not in company_to_articles:
                    company_to_articles[company] = []
                company_to_articles[company].append(article)
        
        if company_to_articles:
            print(f"\n✅ Found {len(company_to_articles)} unique company/companies\n")
            
            # Get ISIN matches for each company and filter articles
            articles_with_isin = []
            all_matches = {}
            
            for company, company_articles in company_to_articles.items():
                print(f"🔎 Searching ISIN for: {company}")
                matches = get_isin_for_company(company, top_n=3, min_score=70)
                
                if matches:
                    all_matches[company] = matches
                    print(f"   ✅ Found {len(matches)} match(es) above 70% confidence:")
                    for i, match in enumerate(matches, 1):
                        print(f"      {i}. {match['matched_name']} - ISIN: {match['isin']} (Score: {match['score']}%)")
                    
                    # Add ISIN info to articles for this company
                    for article in company_articles:
                        article['isin_matches'] = matches
                        article['primary_isin'] = matches[0]['isin']
                        article['matched_company_name'] = matches[0]['matched_name']
                        article['industry'] = matches[0].get('industry', '')
                        articles_with_isin.append(article)
                    
                    print(f"   ✅ {len(company_articles)} article(s) will be processed for summarization")
                else:
                    print(f"   ❌ company_not_found (all matches below 70% threshold)")
                    print(f"   ⏭️  Skipping {len(company_articles)} article(s) - no ISIN match")
                print()
            
            # Print ISIN matches summary
            if all_matches:
                print("=" * 70)
                print("📋 ISIN MATCHES SUMMARY (JSON):")
                print("=" * 70)
                print(json.dumps(all_matches, indent=2, ensure_ascii=False))
                print("=" * 70)
            
            # STEP 2: Summarize ONLY articles with valid ISIN matches
            if articles_with_isin:
                print("\n" + "=" * 70)
                print(f"🤖 STEP 2: AI ANALYSIS FOR {len(articles_with_isin)} ARTICLES WITH ISIN")
                print("=" * 70)
                
                articles_with_summaries = summarize_multiple_articles(articles_with_isin)
                if articles_with_summaries:
                    print_summary_results(articles_with_summaries)

                    # Prepare formatted Slack messages
                    slack_messages = []
                    for article in articles_with_summaries:
                        msg = format_slack_message_from_article(article)
                        if msg.strip():
                            slack_messages.append(msg)

                    if slack_messages:
                        send_slack_message(slack_messages)
                    
                else:
                    print("\n⚠️  No articles to summarize")
            else:
                print("\n" + "=" * 70)
                print("⚠️  No articles with valid ISIN matches to summarize")
                print("=" * 70)
        else:
            print("\n⚠️  No companies identified in articles")
        
        # Return articles to be marked as processed by caller
        return articles
    else:
        print("\n⚠️  No articles were scraped.")
        return []

if __name__ == "__main__":
    iteration = 0
    INTERVAL_MINUTES = 30  # Run every 30 minutes (from start of iteration)
    
   
    processed_articles = set()  # Set of (title, source) tuples
    
    print("\n" + "🔄" * 35)
    print("🤖 CONTINUOUS NEWS SCRAPER STARTED")
    print(f"⏰ Will run every {INTERVAL_MINUTES} minutes (from iteration start)")
    print("📝 Processed articles are tracked permanently (never re-scraped)")
    print("❌ Press Ctrl+C to stop")
    print("🔄" * 35 + "\n")
    
    while True:
        iteration += 1
        iteration_start_time = datetime.now()
        
        print("\n" + "🚀" * 35)
        print(f"🔄 ITERATION #{iteration}")
        print(f"🕐 Started at: {iteration_start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📚 Total processed articles: {len(processed_articles)}")
        print("🚀" * 35 + "\n")
        
        try:
            # Run the main scraping function with processed articles tracker
            processed_articles_list = asyncio.run(main(processed_articles))
            
            # Mark articles as processed permanently
            if processed_articles_list:
                for article in processed_articles_list:
                    if 'article_id' in article:
                        processed_articles.add(article['article_id'])
                print(f"\n✅ Marked {len(processed_articles_list)} article(s) as processed permanently")
            
            end_time = datetime.now()
            duration = (end_time - iteration_start_time).total_seconds()
            
            print("\n" + "✅" * 35)
            print(f"✅ ITERATION #{iteration} COMPLETED")
            print(f"⏱️  Duration: {duration:.1f} seconds ({duration/60:.1f} minutes)")
            print(f"🕐 Finished at: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print("✅" * 35)
            
        except KeyboardInterrupt:
            print("\n\n" + "🛑" * 35)
            print("⛔ SCRAPER STOPPED BY USER")
            print(f"📊 Total iterations completed: {iteration}")
            print(f"📚 Total unique articles processed: {len(processed_articles)}")
            print("🛑" * 35)
            break
            
        except Exception as e:
            end_time = datetime.now()
            duration = (end_time - iteration_start_time).total_seconds()
            print("\n" + "⚠️" * 35)
            print(f"❌ ERROR IN ITERATION #{iteration}")
            print(f"🔥 Error: {str(e)[:100]}")
            print(f"⏱️  Failed after: {duration:.1f} seconds")
            print(f"🕐 Failed at: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print("⚠️" * 35)
        
        # Calculate sleep time to maintain exact 30-minute intervals
        elapsed_time = (datetime.now() - iteration_start_time).total_seconds()
        sleep_seconds = (INTERVAL_MINUTES * 60) - elapsed_time
        
        if sleep_seconds > 0:
            sleep_minutes = sleep_seconds / 60
            next_run_time = datetime.now() + pd.Timedelta(seconds=sleep_seconds)
            
            print(f"\n💤 Sleeping for {sleep_minutes:.1f} minutes...")
            print(f"⏰ Next iteration at: {next_run_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   (Exactly {INTERVAL_MINUTES} minutes from iteration start)")
            print("-" * 70 + "\n")
            
            try:
                time.sleep(sleep_seconds)
            except KeyboardInterrupt:
                print("\n\n" + "🛑" * 35)
                print("⛔ SCRAPER STOPPED BY USER")
                print(f"📊 Total iterations completed: {iteration}")
                print(f"📚 Total unique articles processed: {len(processed_articles)}")
                print("🛑" * 35)
                break
        else:
            print(f"\n⚠️  WARNING: Processing took {elapsed_time/60:.1f} minutes")
            print(f"   (Longer than {INTERVAL_MINUTES}-minute interval!)")
            print(f"   Starting next iteration immediately...\n")
            print("-" * 70 + "\n")
