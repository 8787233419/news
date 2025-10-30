"""
LLM prompts for extracting and summarizing news article data
"""

import sys

# Fix Windows console encoding
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

import google.generativeai as genai
import json
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Initialize Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


def summarize_article_data(article_text: str, article_title: str = "", company_name: str = "") -> dict:
    """
    Extract significant data and source information from a news article using Gemini
    
    Args:
        article_text (str): Full news article text
        article_title (str): Article title (optional)
        company_name (str): Company name identified (optional)
    
    Returns:
        dict: {
            "summary": "4-5 line summary with key numeric data",
            "numeric_data": ["list of all numeric/quantitative data points"],
            "source": "Where the data is coming from"
        }
    
    Example:
        >>> article = "Reliance Industries reported Q4 revenue of ₹2.35 lakh crore, up 12% YoY..."
        >>> result = summarize_article_data(article, "Reliance Earnings", "Reliance Industries")
        >>> print(result['summary'])
    """
    
    if not GEMINI_API_KEY:
        print("⚠️  GEMINI_API_KEY not found in .env file")
        return {
            "summary": "API key not configured",
            "numeric_data": [],
            "source": "Unknown"
        }
    
    # Initialize model
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    
    # Create prompt
    company_context = f" about {company_name}" if company_name else ""
    
    prompt = f"""You are a financial data analyst. Analyze this news article{company_context} and extract key information.

Article Title: {article_title or "Not provided"}

Article Text: {article_text[:4000]}

Your task:
1. Write a concise summary (4-5 lines MAX) focusing on the most significant information
2. Identify ALL numeric/quantitative data (revenue, profits, percentages, growth rates, market share, dates, projections, etc.)
3. Identify the source of the data (company announcement, analyst report, regulatory filing, unnamed sources, etc.)

Return your response as a JSON object with this EXACT format:
{{
    "summary": "4-5 line concise summary with key highlights and numeric data",
    "numeric_data": [
        "Revenue: ₹X crore",
        "Growth: X%",
        "Other numeric fact"
    ],
    "source": "Where this data is coming from (company, analyst, filing, etc.)"
}}

Important:
- Keep summary to 4-5 lines maximum
- Extract ALL significant numbers mentioned
- Be specific about the source
- If no numeric data found, return empty array
- If source unclear, say "Article/Report" or "Unnamed sources"

JSON Response:"""
    
    try:
        # Get response from Gemini
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # Try to extract JSON
        if '```json' in response_text:
            json_str = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            json_str = response_text.split('```')[1].split('```')[0].strip()
        elif '{' in response_text:
            # Find JSON in response
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            json_str = response_text[start:end]
        else:
            json_str = response_text
        
        # Parse JSON
        result = json.loads(json_str)
        
        # Validate structure
        if not isinstance(result, dict):
            raise ValueError("Response is not a dictionary")
        
        # Ensure all keys exist
        return {
            "summary": result.get('summary', 'No summary available'),
            "numeric_data": result.get('numeric_data', []),
            "source": result.get('source', 'Unknown')
        }
        
    except Exception as e:
        print(f"Error summarizing article: {e}")
        return {
            "summary": "Error processing article",
            "numeric_data": [],
            "source": "Unknown"
        }


def summarize_multiple_articles(articles: list) -> list:
    """
    Summarize multiple articles with their data extraction
    
    Args:
        articles (list): List of article dictionaries with 'full_article', 'title', 'company_name'
    
    Returns:
        list: List of articles with added 'ai_summary' field containing extracted data
    """
    
    if not articles:
        return []
    
    print(f"\n📊 Summarizing {len(articles)} articles with AI...\n")
    
    summarized_articles = []
    
    for i, article in enumerate(articles, 1):
        article_text = article.get('full_article', '')
        article_title = article.get('title', '')
        company_name = article.get('company_name', '')
        
        # Skip if article is too short or has errors
        if article.get('article_length', 0) < 200:
            continue
        
        if article_text.startswith('ERROR') or article_text.startswith('NO_CONTENT'):
            continue
        
        print(f"   [{i}/{len(articles)}] Analyzing: {article.get('source', 'Unknown')}")
        if company_name:
            print(f"      Company: {company_name}")
        
        # Get AI summary
        ai_summary = summarize_article_data(article_text, article_title, company_name)
        
        # Add summary to article
        article_with_summary = article.copy()
        article_with_summary['ai_summary'] = ai_summary
        summarized_articles.append(article_with_summary)
        
        # Show preview
        print(f"      ✅ Summary: {ai_summary['summary'][:80]}...")
        if ai_summary['numeric_data']:
            print(f"      📊 Found {len(ai_summary['numeric_data'])} numeric data points")
        print()
    
    return summarized_articles


def print_summary_results(articles_with_summaries: list):
    """
    Print formatted summary results for all articles
    
    Args:
        articles_with_summaries (list): Articles with AI summaries
    """
    
    if not articles_with_summaries:
        print("\n⚠️  No summarized articles to display")
        return
    
    print("\n" + "=" * 70)
    print("📰 AI-GENERATED ARTICLE SUMMARIES")
    print("=" * 70)
    
    for i, article in enumerate(articles_with_summaries, 1):
        ai_summary = article.get('ai_summary', {})
        
        print(f"\n{'─' * 70}")
        print(f"📄 Article #{i}: {article.get('source', 'Unknown')}")
        print(f"{'─' * 70}")
        
        # Company
        if article.get('company_name'):
            print(f"🏢 Company: {article['company_name']}")
        
        # Title
        print(f"📌 Title: {article.get('title', 'No title')}")
        
        # Summary
        print(f"\n📝 Summary:")
        summary_lines = ai_summary.get('summary', 'No summary').split('\n')
        for line in summary_lines:
            if line.strip():
                print(f"   {line.strip()}")
        
        # Numeric Data
        numeric_data = ai_summary.get('numeric_data', [])
        if numeric_data:
            print(f"\n📊 Key Numeric Data:")
            for data_point in numeric_data:
                print(f"   • {data_point}")
        
        # Source
        source = ai_summary.get('source', 'Unknown')
        print(f"\n🔗 Data Source: {source}")
        
        # URL
        print(f"🌐 URL: {article.get('url', 'N/A')[:70]}...")
    
    print("\n" + "=" * 70)
    
    # Statistics
    total_numeric_points = sum(len(a.get('ai_summary', {}).get('numeric_data', [])) for a in articles_with_summaries)
    articles_with_numbers = sum(1 for a in articles_with_summaries if a.get('ai_summary', {}).get('numeric_data', []))
    
    print("📊 SUMMARY STATISTICS:")
    print(f"   Total articles summarized: {len(articles_with_summaries)}")
    print(f"   Articles with numeric data: {articles_with_numbers}")
    print(f"   Total numeric data points: {total_numeric_points}")
    print("=" * 70)


# Example usage
def main():
    """Test the summarization functions"""
    
    test_article = """
    Infosys Ltd. reported record-breaking quarterly results on Tuesday, with revenue reaching ₹40,986 crore 
    for Q1 FY24, representing a 13.7% increase compared to the same quarter last year. The IT services giant's 
    net profit came in at ₹6,368 crore, beating analyst expectations of ₹6,100 crore.
    
    Digital services drove much of the growth, generating ₹24,500 crore in revenue, up 15% year-over-year. 
    The company's operating margin improved to 21.2%, up 60 basis points from the previous quarter. Infosys also 
    announced a 6% increase in its quarterly dividend to ₹18.5 per share.
    
    CEO Salil Parekh stated in the earnings call that Infosys now has over 345,000 employees globally,
    with particularly strong growth in BFSI sector where revenue increased by 18%. The company's market 
    capitalization now stands at ₹6.5 lakh crore, maintaining its position as India's second-most valuable IT company.
    """
    
    test_title = "Infosys Reports Record Q1 Revenue of ₹40,986 Crore, Beats Expectations"
    test_company = "Infosys"
    
    print("=" * 70)
    print("🧪 Testing Article Summarization with Gemini")
    print("=" * 70)
    
    if not GEMINI_API_KEY:
        print("\n❌ ERROR: GEMINI_API_KEY not found!")
        print("Please create a .env file with your Gemini API key:")
        print("GEMINI_API_KEY=your-key-here")
        print("\nGet your key from: https://makersuite.google.com/app/apikey")
    else:
        print(f"\n✅ API Key loaded: {GEMINI_API_KEY[:20]}...")
        
        print("\n🔍 Analyzing test article...\n")
        result = summarize_article_data(test_article, test_title, test_company)
        
        print("📝 SUMMARY:")
        print(f"   {result['summary']}")
        
        print("\n📊 NUMERIC DATA:")
        for data_point in result['numeric_data']:
            print(f"   • {data_point}")
        
        print(f"\n🔗 SOURCE: {result['source']}")
        
        print("\n" + "=" * 70)
        print("📄 Full JSON Response:")
        print("=" * 70)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()

