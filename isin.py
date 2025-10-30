"""
Extract main company name from news articles using Gemini AI
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


def extract_company_simple(article_text: str, article_title: str = "") -> str:
    """
    Robust version that returns only the MAIN company name with validation
    
    Args:
        article_text (str): Full news article text
        article_title (str): Article title (optional)
    
    Returns:
        str: Main company name (or empty string if none found)
    
    Example:
        >>> article = "Infosys announced new AI platform today..."
        >>> company = extract_company_simple(article)
        >>> print(company)
        'Infosys'
    """
    
    if not GEMINI_API_KEY:
        print("⚠️  GEMINI_API_KEY not found in .env file")
        return ""
    
    # Initialize model with structured output configuration
    model = genai.GenerativeModel(
        'models/gemini-2.5-flash',
        generation_config={
            "temperature": 0.1,  # Lower temperature for more consistent output
            "top_p": 0.8,
            "top_k": 40,
        }
    )
    
    # Robust prompt with anti-hallucination measures
    prompt = f"""You are a financial analyst expert at extracting company names from news articles.

CRITICAL RULES - DO NOT VIOLATE:
1. Extract ONLY the PRIMARY company that this article is mainly about
2. The company name MUST actually appear in the article text or title
3. DO NOT make up, guess, or infer company names that are not explicitly mentioned
4. Return the simple/common company name (e.g., "Infosys" not "Infosys Limited")
5. If the article is about general topics, sectors, or multiple companies without a clear primary focus, return "NONE"
6. DO NOT return generic terms like "the company", "firm", "corporation"

Article Title: {article_title or "Not provided"}

Article Text (first 4000 chars): {article_text[:4000]}

Return ONLY a valid JSON object with this EXACT format:
{{"company_name": "CompanyName", "confidence": "high/medium/low", "mentioned_in": "title/body/both"}}

If NO company found or article is too general, return:
{{"company_name": "NONE", "confidence": "none", "mentioned_in": "none"}}

JSON Response:"""
    
    try:
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # Extract JSON from response
        if '```json' in response_text:
            json_str = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            json_str = response_text.split('```')[1].split('```')[0].strip()
        elif '{' in response_text:
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            json_str = response_text[start:end]
        else:
            json_str = response_text
        
        # Parse JSON
        result = json.loads(json_str)
        company_name = result.get('company_name', '').strip()
        confidence = result.get('confidence', 'low')
        
        # Validation: Check if company name is valid
        if not company_name or company_name.upper() == "NONE":
            return ""
        
        # Filter out generic/invalid responses
        invalid_terms = ['company', 'corporation', 'firm', 'business', 'the', 'inc', 'ltd', 'limited']
        if company_name.lower() in invalid_terms:
            return ""
        
        # Validation: Verify the company name actually appears in the text (case-insensitive)
        article_text_lower = article_text.lower()
        article_title_lower = (article_title or "").lower()
        company_name_lower = company_name.lower()
        
        # Check if company name or common variations exist in the article
        appears_in_text = (
            company_name_lower in article_text_lower or 
            company_name_lower in article_title_lower
        )
        
        if not appears_in_text:
            # Try to find partial matches (company name might be abbreviated)
            words = company_name.split()
            if len(words) > 1:
                # Try first word (e.g., "Tata" from "Tata Motors")
                if words[0].lower() in article_text_lower or words[0].lower() in article_title_lower:
                    appears_in_text = True
        
        if not appears_in_text:
            print(f"         ⚠️  Validation failed: '{company_name}' not found in article text")
            return ""
        
        # Filter out low confidence results
        if confidence == "low":
            print(f"         ⚠️  Low confidence ({confidence}) for '{company_name}'")
            return ""
        
        return company_name
        
    except json.JSONDecodeError as e:
        print(f"         ⚠️  JSON parsing error: {e}")
        return ""
    except Exception as e:
        print(f"         ⚠️  Error: {e}")
        return ""


# Example usage

def main():
    # Test article
    test_article = """
    Tata Motors reported record quarterly revenue on Wednesday, beating analyst expectations.
    The Indian automobile maker delivered 2.5 lakh vehicles in Q4 FY24, up 28% from last year.
    CEO N Chandrasekaran said Tata Motors is on track for strong growth in FY25.
    The company also announced plans to expand EV production capacity in Pune and Gujarat.
    Competitors like Mahindra and Maruti Suzuki are also ramping up electric vehicle production.
    """
    
    test_title = "Tata Motors reports record quarterly revenue, beats expectations"
    
    print("=" * 70)
    print("🔍 Testing Company Extraction with Gemini")
    print("=" * 70)
    
    if not GEMINI_API_KEY:
        print("\n❌ ERROR: GEMINI_API_KEY not found!")
        print("Please create a .env file with your Gemini API key:")
        print("GEMINI_API_KEY=your-key-here")
        print("\nGet your key from: https://makersuite.google.com/app/apikey")
    else:
        print(f"\n✅ API Key loaded: {GEMINI_API_KEY[:20]}...")
        
        # Test: Extract main company only
        print("\n🔍 Extract MAIN company:")
        main_company = extract_company_simple(test_article, test_title)
        print(f"   Main company: {main_company}")
    
    print("\n" + "=" * 70)

if __name__ == "__main__":    
    main()