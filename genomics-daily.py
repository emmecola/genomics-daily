#!/usr/bin/env python3
import anthropic
import html
import os
import pandas as pd
import re
import requests
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from urllib.parse import urlencode

def load_keywords_from_file(filepath):
    """
    Load keywords from a text file
    
    Parameters:
    -----------
    filepath : str
        Path to the keywords file
    
    Returns:
    --------
    list
        List of keywords
    """
    try:
        with open(filepath, 'r') as f:
            keywords = [line.strip() for line in f if line.strip()]
        return keywords
    except FileNotFoundError:
        print(f"Keywords file not found: {filepath}")
        return []
    except Exception as e:
        print(f"Error reading keywords file: {e}")
        return []

def load_journals_from_file(filepath):
    """
    Load journals from a text file
    
    Parameters:
    -----------
    filepath : str
        Path to the journals file
    
    Returns:
    --------
    list
        List of journals with [Journal] qualifier
    """
    try:
        with open(filepath, 'r') as f:
            journals = [f"{line.strip()}[Journal]" for line in f if line.strip()]
        return journals
    except FileNotFoundError:
        print(f"Journals file not found: {filepath}")
        return []
    except Exception as e:
        print(f"Error reading journals file: {e}")
        return []

def get_full_text(element):
    """
    Concatenate element text and its children's text
    """
    text_parts = []
    if element.text:
        text_parts.append(element.text)
    for child in element:
        child_text = get_full_text(child)
        if child_text:
            text_parts.append(child_text)
        if child.tail:
            text_parts.append(child.tail)
    return ' '.join(text_parts)

def clean_text(text):
    """
    Clean text
    """
    cleaned_text = re.sub('<[^<]+?>', '', text)
    cleaned_text = html.unescape(cleaned_text)
    cleaned_text = ' '.join(cleaned_text.split())
    return cleaned_text

def clean_title_text(title_element):
    """
    Extract and clean title text from XML, preserving full content
    """
    if title_element is None:
        return "N/A"
    full_text = get_full_text(title_element)
    cleaned_text = clean_text(full_text)
    return cleaned_text if cleaned_text else "N/A"

def clean_abstract_text(abstract):
    """
    Extract and clean abstract text from XML, preserving full content
    """
    if abstract is None:
        return "N/A"
    abstract_texts = abstract.findall('.//AbstractText')
    full_abstract_parts = []
    for text_elem in abstract_texts:
        full_text = get_full_text(text_elem)
        cleaned_text = clean_text(full_text)
        full_abstract_parts.append(cleaned_text)
    full_abstract = ' '.join(full_abstract_parts)
    return full_abstract if full_abstract else "N/A"

def retrieve_genomics_papers_with_abstracts(days_back=1, 
                                            keywords_file='keywords.txt', 
                                            journals_file='journals.txt'):
    """
    Retrieve and filter genomics papers
    
    Parameters:
    -----------
    days_back : int, optional (default=1)
        Number of days to look back for papers
    keywords_file : str, optional
        Path to file containing keywords
    journals_file : str, optional
        Path to file containing journals
    
    Returns:
    --------
    pandas.DataFrame
        DataFrame of most relevant papers
    """
    # Load keywords and journals from files
    keywords = load_keywords_from_file(keywords_file)
    major_journals = load_journals_from_file(journals_file)

    # Calculate the date range
    end_date = datetime.now() - timedelta(days=days_back)
    start_date = datetime.now() - timedelta(days=days_back)
    
    # Format dates for PubMed search
    start_date_str = start_date.strftime("%Y/%m/%d")
    end_date_str = end_date.strftime("%Y/%m/%d")
    
    # PubMed E-utilities base URL
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"

    # Construct comprehensive search query
    keyword_query = " OR ".join([f"{kw}[Title/Abstract]" for kw in keywords])

    # Join the journals with OR to create a journal filter
    journal_filter = " OR ".join(major_journals)

    # Add publication type filter for Journal Article
    publication_type_filter = "Journal Article[Publication Type]"
    
    # Create the search query
    search_query = (
        f"(({keyword_query})) "
        f"AND ({journal_filter}) "
        f"AND {publication_type_filter} "
        f"AND {start_date_str}:{end_date_str}[Date - Publication]"
    )
    
    # Search parameters
    search_params = {
        'db': 'pubmed',
        'term': search_query,
        'retmax': 500,
        'usehistory': 'y'
    }

    # Perform search
    search_response = requests.get(f"{base_url}esearch.fcgi", params=search_params)
    
    # Parse search response
    search_root = ET.fromstring(search_response.content)
    web_env = search_root.find('WebEnv').text
    query_key = search_root.find('QueryKey').text
    
    # Fetch paper details
    fetch_params = {
        'db': 'pubmed',
        'query_key': query_key,
        'WebEnv': web_env,
        'retmode': 'xml',
        'retmax': 500
    }

    # Perform fetch
    fetch_response = requests.get(f"{base_url}efetch.fcgi", params=fetch_params)
    
    # Parse fetch response
    fetch_root = ET.fromstring(fetch_response.content)
    
    # Extract paper details
    papers = []
    for article in fetch_root.findall('.//PubmedArticle'):
        try:
            # Extract title
            article_title = article.find('.//ArticleTitle')
            title = clean_title_text(article_title)
            
            # Extract authors
            authors = article.findall('.//Author')
            author_names = [
                f"{author.find('LastName').text} {author.find('ForeName').text}" 
                for author in authors 
                if author.find('LastName') is not None and author.find('ForeName') is not None
            ]
            
            # Extract abstract
            abstract = article.find('.//Abstract')
            abstract_text = clean_abstract_text(abstract)
            
            # Extract journal
            journal = article.find('.//Title')
            journal_name = journal.text if journal is not None else "N/A"
            
            # Extract publication date
            pub_date = article.find('.//PubDate')
            publication_date = (
                f"{pub_date.find('Year').text}" 
                if pub_date is not None and pub_date.find('Year') is not None 
                else "N/A"
            )
            
            # Extract PMID
            pmid = article.find('.//PMID')
            pmid_value = pmid.text if pmid is not None else "N/A"

            # Extract link
            link = 'https://pubmed.ncbi.nlm.nih.gov/' + pmid_value if pmid is not None else "N/A"
            
            papers.append({
                'Title': title,
                'Authors': ', '.join(author_names[:3]) + (', et al.' if len(author_names) > 3 else ''),
                'Journal': journal_name,
                'Publication Year': publication_date,
                'PMID': pmid_value,
                'Link': link,
                'Abstract': abstract_text
            })
        except Exception as e:
            print(f"Error processing article: {e}")
    
    # Convert to DataFrame and remove duplicates
    df = pd.DataFrame(papers)
    df.drop_duplicates(subset=['PMID'], inplace=True)
    
    return df

def generate_editorial_with_claude(papers_df, mode='simple'):
    """
    Generate an editorial using Anthropic's Claude API based on retrieved papers
    
    Parameters:
    -----------
    papers_df : pandas.DataFrame
        DataFrame containing genomics papers
    
    Returns:
    --------
    str
        Generated editorial text
    """
    # Ensure Anthropic API key is set
    client = anthropic.Anthropic(
        api_key=os.getenv('ANTHROPIC_API_KEY')
    )
    
    # Validate API key
    if not client.api_key:
        raise ValueError("Anthropic API key not found. Set ANTHROPIC_API_KEY environment variable.")
    
    # Prepare paper summaries for the prompt
    paper_summaries = "\n\n".join([
        f"Title: {row['Title']}\n"
        f"Authors: {row['Authors']}\n"
        f"Journal: {row['Journal']}\n"
        f"Link: {row['Link']}\n"
        f"Publication Year: {row['Publication Year']}\n"
        f"Abstract: {row['Abstract']}"
        for _, row in papers_df.iterrows()
    ])
    
    # Construct the prompt for the editorial
    if mode=='advanced':
        tokens = 4000
        temp = 0.3
        mymodel = 'claude-3-opus-latest'
        prompt = f"""
You are a senior scientific editor specializing in genomics research.
    Write an insightful and cohesive essay analyzing the latest trends in genomics research based on the following recent publications.

{paper_summaries}

You have to group papers according to common themes, and select the most important themes or the ones covered by more papers. 

For each identified theme, please provide:
1. An introduction of the theme
2. Historical context and background
3. Accessible metaphors to explain complex concepts
4. Integration of findings from the provided abstracts
5. Future research directions and implications

Also follow these instructions:
- Ignore publications that are not related to genomics, genetics or DNA analysis.
- Make connections between papers, allowing smooth transitions between different cited papers.
- Ensure technical concepts are explained clearly.
- Cite the papers that you took into account, and include a complete reference list at the end. No other lists should be present.
- Use subheadings only to distinguish themes.
- Write a catchy title.
- Don't use emojis.
- Be professional and serious, avoid sensationalism.
- Do not sign this text.
- Use the **Markdown** syntax.
    """
    else:
        tokens = 1200
        temp = 0.7
        mymodel = 'claude-3-5-haiku-latest'
        prompt = f"""
    You are a senior scientific editor specializing in genomics research.
    Write a short, insightful editorial analyzing the latest trends in genomics research based on the following recent publications:
    
    {paper_summaries}
    
    You must follow these instructions:
    - Ignore publications that are not related to genomics, genetics or DNA analysis.
    - Select the three most relevant papers, giving priority to the topics that you deem more important.
    - If possible, the papers you choose should cover different research areas (including, for example, medicine, evolution, plant science or microbiology).
    - Write a catchy title that synthetises the three papers that you selected, and a brief introductory paragraph.
    - For each selected paper, write one paragraph describing the major findings and why it is relevant. This paragraph should not contain lists.
    - Each subheading must start with a relevant emoji.
    - Be engaging but serious, avoid sensationalism.
    - Do not sign this text.
    - At the end of the text, add the references with links to the papers that you chose.
    - Use the **Markdown** syntax.
    """
    
    # Call Anthropic's Claude API
    try:
        response = client.messages.create(
            model=mymodel,
            max_tokens=tokens,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=temp
        )
        
        # Extract and return the editorial text
        return response.content[0].text
    
    except Exception as e:
        print(f"Error generating editorial with Claude: {e}")
        return None

def main():
    keywords_file = sys.argv[1]
    journals_file = sys.argv[2]
    days_back = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    mode = sys.argv[4] if len(sys.argv) > 4 else 'simple'
    df = retrieve_genomics_papers_with_abstracts(keywords_file=keywords_file, journals_file=journals_file, days_back=days_back)
    editorial = generate_editorial_with_claude(df,mode=mode)
    print(editorial)

if __name__ == "__main__":
    main()
