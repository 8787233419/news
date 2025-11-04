"""
Fuzzy ISIN matcher
Uses fuzzy string matching to find top 3 company matches and their ISIN numbers
"""

import sys

# Fix Windows console encoding
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

import pandas as pd
from fuzzywuzzy import fuzz, process


def get_isin_for_company(company_name: str, excel_file: str = 'accord_bse_mapping_original.xlsx', top_n: int = 3, min_score: int = 70) -> list:
    """
    Find ISIN number for a company using fuzzy matching
    Returns top 3 matches with similarity scores above threshold
    
    Args:
        company_name (str): Company name to search for
        excel_file (str): Path to Excel file with company-ISIN mapping
        top_n (int): Number of top matches to return (default: 3)
        min_score (int): Minimum fuzzy match score to accept (default: 70)
    
    Returns:
        list: List of top N matches with format:
              [
                  {
                      'matched_name': 'Tata Motors Ltd',
                      'isin': 'INE155A01022',
                      'nse_symbol': 'TATAMOTORS',
                      'bse_code': '500570',
                      'rank': 1,
                      'score': 95
                  },
                  ...
              ]
              Returns empty list if no matches above min_score threshold
    """
    
    if not company_name:
        return []
    
    try:
        # Load the Excel file
        df = pd.read_excel(excel_file)
        
        # Get list of company names from the dataframe
        company_column = 'Company Name'
        if company_column not in df.columns:
            print(f"      ⚠️  '{company_column}' column not found in Excel file")
            return []
        
        # Create a list of company names (remove NaN values)
        company_names = df[company_column].dropna().tolist()
        
        # Use fuzzy matching to find top matches
        # process.extract returns list of tuples: (match, score)
        matches = process.extract(company_name, company_names, scorer=fuzz.token_sort_ratio, limit=top_n)
        
        results = []
        for rank, (matched_name, score) in enumerate(matches, 1):
            # Filter out matches below minimum score threshold
            if score < min_score:
                continue  # Skip this match
            
            # Get the row for this company
            row = df[df[company_column] == matched_name].iloc[0]
            
            # Extract ISIN and other info
            isin = row.get('CD_ISIN No', '')
            nse_symbol = row.get('CD_NSE Symbol', '')
            bse_code = row.get('CD_BSE Code', '')
            industry = row.get('CD_Industry1', '')
            
            # Convert to string and handle NaN
            isin = str(isin) if pd.notna(isin) else ''
            nse_symbol = str(nse_symbol) if pd.notna(nse_symbol) else ''
            bse_code = str(bse_code) if pd.notna(bse_code) else ''
            industry = str(industry) if pd.notna(industry) else ''
            
            results.append({
                'matched_name': matched_name,
                'isin': isin,
                'nse_symbol': nse_symbol,
                'bse_code': bse_code,
                'industry': industry,
                'rank': rank,
                'score': score
            })
        
        # If no results above threshold, return empty list (company_not_found)
        return results
        
    except Exception as e:
        print(f"      ⚠️  Error matching ISIN: {str(e)[:100]}")
        return []


# Test function
if __name__ == "__main__":
    print("=" * 70)
    print("🔍 Testing Fuzzy ISIN Matcher (70% Threshold)")
    print("=" * 70)
    
    # Test with a company name
    test_company = "Infosys"
    
    print(f"\n🔎 Searching for: {test_company}")
    print("⏳ Performing fuzzy match (min score: 70%)...\n")
    
    matches = get_isin_for_company(test_company, min_score=70)
    
    if matches:
        print(f"✅ Found {len(matches)} match(es) above 70% threshold:\n")
        for match in matches:
            score = match.get('score', 0)
            # Color code the score
            if score >= 90:
                confidence = "🟢 Excellent"
            elif score >= 80:
                confidence = "🟡 Good"
            else:
                confidence = "🟠 Fair"
            
            print(f"   Rank {match.get('rank', '?')} ({confidence} - Score: {score}%):")
            print(f"   └─ Company: {match.get('matched_name', 'N/A')}")
            print(f"      ISIN: {match.get('isin', 'N/A')}")
            print(f"      NSE: {match.get('nse_symbol', 'N/A')} | BSE: {match.get('bse_code', 'N/A')}")
            print()
    else:
        print("❌ company_not_found (all matches below 70% threshold)")
    
    print("=" * 70)

