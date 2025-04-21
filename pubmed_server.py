import logging
import requests
import json
import xml.etree.ElementTree as ET
from mcp.server.fastmcp import FastMCP
from typing import Dict, Any, List, Optional, Tuple, Union
from dotenv import load_dotenv
import time
import os
from datetime import datetime

# Environment configuration
load_dotenv()

# Setup logging with rotation
log_directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(log_directory, exist_ok=True)
log_file = os.path.join(log_directory, f"medlibrary_{datetime.now().strftime('%Y%m%d')}.log")

logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# API Configuration
class Config:
    NCBI_API_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    ARTICLE_VIEW_BASE = "https://pubmed.ncbi.nlm.nih.gov"
    REQUEST_TIMEOUT = 30
    RETRY_ATTEMPTS = 3
    RETRY_DELAY = 1

# Initialize service
mcp = FastMCP("MedicalLibrary")
logger = logging.getLogger("MedicalLibrary")

class QueryBuilder:
    @staticmethod
    def create_author_clause(names: List[str]) -> str:
        """Generate search clause for author names"""
        if not names:
            return ""
        return "(" + " OR ".join(f"{name}[Author]" for name in names) + ")"
    
    @staticmethod
    def create_keyword_clause(terms: List[str]) -> str:
        """Generate search clause for keywords in title/abstract"""
        if not terms:
            return ""
        return "(" + " OR ".join(f"{term}[Title/Abstract]" for term in terms) + ")"
    
    @staticmethod
    def combine_clauses(clauses: List[str]) -> str:
        """Combine multiple search clauses with AND operator"""
        return " AND ".join(clause for clause in clauses if clause)

def make_api_request(endpoint: str, params: Dict[str, Any], retries: int = Config.RETRY_ATTEMPTS) -> requests.Response:
    """
    Make a request to NCBI API with retry logic
    
    Args:
        endpoint: API endpoint path
        params: Request parameters
        retries: Number of retry attempts
        
    Returns:
        Response object from the API
    
    Raises:
        requests.RequestException: If request fails after all retries
    """
    url = f"{Config.NCBI_API_BASE}/{endpoint}"
    attempt = 0
    
    while attempt < retries:
        try:
            response = requests.get(url, params=params, timeout=Config.REQUEST_TIMEOUT)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            attempt += 1
            if attempt == retries:
                logger.error(f"Failed API request to {url}: {str(e)}")
                raise
            time.sleep(Config.RETRY_DELAY)
            logger.warning(f"Retrying API request to {url} (attempt {attempt}/{retries})")

def retrieve_article_ids(search_query: str, max_count: int) -> Tuple[List[str], int]:
    """
    Search for articles and retrieve their IDs
    
    Args:
        search_query: Complete search query string
        max_count: Maximum number of results to retrieve
        
    Returns:
        Tuple containing list of article IDs and total result count
    """
    if not search_query:
        return [], 0
        
    logger.info(f"Searching with query: {search_query}")
    
    try:
        params = {
            "db": "pubmed",
            "term": search_query,
            "retmax": max_count,
            "retmode": "json",
            "usehistory": "y"
        }
        
        response = make_api_request("esearch.fcgi", params)
        data = response.json()
        
        id_list = data.get("esearchresult", {}).get("idlist", [])
        total_count = int(data.get("esearchresult", {}).get("count", 0))
        
        logger.info(f"Search returned {total_count} total results, fetching {len(id_list)}")
        return id_list, total_count
    except Exception as e:
        logger.error(f"Error retrieving article IDs: {str(e)}")
        return [], 0

def fetch_article_metadata(article_ids: List[str]) -> Optional[ET.Element]:
    """
    Fetch detailed metadata for articles by their IDs
    
    Args:
        article_ids: List of article IDs to fetch
        
    Returns:
        XML root element containing article data, or None if request fails
    """
    if not article_ids:
        return None
        
    try:
        params = {
            "db": "pubmed",
            "id": ",".join(article_ids),
            "retmode": "xml"
        }
        
        response = make_api_request("efetch.fcgi", params)
        root = ET.fromstring(response.content)
        return root
    except Exception as e:
        logger.error(f"Error fetching article metadata: {str(e)}")
        return None

class ArticleParser:
    @staticmethod
    def extract_text(element: ET.Element, xpath: str, default: str = "N/A") -> str:
        """Extract text from an XML element at the given xpath"""
        result = element.findtext(xpath)
        return result if result else default
    
    @staticmethod
    def process_articles(root_element: ET.Element) -> List[Dict[str, Any]]:
        """Process XML data and extract structured article information"""
        if root_element is None:
            return []
            
        articles = root_element.findall(".//PubmedArticle")
        results = []
        
        for article in articles:
            # Core article data
            pmid = ArticleParser.extract_text(article, ".//PMID")
            
            # Construct article record
            article_data = {
                "id": pmid,
                "url": f"{Config.ARTICLE_VIEW_BASE}/{pmid}",
                "title": ArticleParser.extract_text(article, ".//ArticleTitle"),
                "journal": {
                    "name": ArticleParser.extract_text(article, ".//Journal/Title"),
                    "volume": ArticleParser.extract_text(article, ".//Journal/JournalIssue/Volume"),
                    "issue": ArticleParser.extract_text(article, ".//Journal/JournalIssue/Issue"),
                    "pages": ArticleParser.extract_text(article, ".//Pagination/MedlinePgn"),
                },
                "publication_date": ArticleParser.extract_text(article, ".//PubDate/Year"),
                "doi": ArticleParser.extract_text(article, ".//ELocationID[@EIdType='doi']"),
                "abstract": ArticleParser.extract_text(article, ".//Abstract/AbstractText"),
                "authors": ArticleParser.extract_authors(article),
                "keywords": ArticleParser.extract_keywords(article)
            }
            
            results.append(article_data)
            
        return results
    
    @staticmethod
    def extract_authors(article: ET.Element) -> List[Dict[str, str]]:
        """Extract and format author information"""
        authors = []
        
        for author_elem in article.findall(".//Author"):
            lastname = ArticleParser.extract_text(author_elem, "LastName", "")
            forename = ArticleParser.extract_text(author_elem, "ForeName", "")
            initials = ArticleParser.extract_text(author_elem, "Initials", "")
            
            if lastname or forename or initials:
                authors.append({
                    "lastname": lastname,
                    "forename": forename,
                    "initials": initials,
                    "full_name": f"{lastname} {forename}" if forename else f"{lastname} {initials}",
                })
                
        return authors
    
    @staticmethod
    def extract_keywords(article: ET.Element) -> List[str]:
        """Extract keywords if available"""
        keywords = []
        
        for keyword in article.findall(".//Keyword"):
            if keyword.text:
                keywords.append(keyword.text)
                
        return keywords

@mcp.tool()
async def find_articles(
    topics: List[str] = [], 
    researchers: List[str] = [], 
    result_limit: int = 15
) -> Dict[str, Any]:
    """
    Search for medical literature in PubMed database
    
    Args:
        topics: List of medical topics or keywords to search in titles and abstracts
        researchers: List of researcher/author names to search for
        result_limit: Maximum number of results to return (default: 15)
        
    Returns:
        Dictionary with search results and metadata
    """
    try:
        # Start operation timestamp
        start_time = time.time()
        
        # Build search query
        author_clause = QueryBuilder.create_author_clause(researchers)
        topic_clause = QueryBuilder.create_keyword_clause(topics)
        query = QueryBuilder.combine_clauses([author_clause, topic_clause])
        
        if not query:
            return {
                "status": "error",
                "message": "Search requires at least one topic or researcher name",
                "articles": []
            }
        
        # Get article IDs matching search criteria
        article_ids, total_count = retrieve_article_ids(query, result_limit)
        
        if not article_ids:
            return {
                "status": "success",
                "message": "No articles found matching the search criteria",
                "total_available": 0,
                "articles": []
            }
        
        # Fetch and parse article details
        root = fetch_article_metadata(article_ids)
        articles = ArticleParser.process_articles(root)
        
        # Calculate operation time
        elapsed_time = time.time() - start_time
        
        return {
            "status": "success",
            "message": f"Found {total_count} articles, returning {len(articles)}",
            "total_available": total_count,
            "retrieved": len(articles),
            "performance": {
                "elapsed_seconds": round(elapsed_time, 2)
            },
            "articles": articles
        }
    except Exception as e:
        logger.error(f"Error in find_medical_literature: {str(e)}")
        return {
            "status": "error",
            "message": str(e),
            "articles": []
        }

@mcp.tool()
async def get_publication_details(article_id: str) -> Dict[str, Any]:
    """
    Retrieve comprehensive details for a specific medical publication
    
    Args:
        article_id: PubMed ID of the article to retrieve
        
    Returns:
        Dictionary containing complete article metadata
    """
    try:
        # Validate input
        if not article_id or not article_id.strip():
            return {
                "status": "error",
                "message": "Article ID is required"
            }
        
        # Fetch article metadata
        root = fetch_article_metadata([article_id])
        
        if root is None:
            return {
                "status": "error",
                "message": f"Failed to retrieve data for article ID: {article_id}"
            }
        
        articles = ArticleParser.process_articles(root)
        
        if not articles:
            return {
                "status": "error",
                "message": f"No article found with ID: {article_id}"
            }
        
        # Add citation information
        article_data = articles[0]
        article_data["citation"] = generate_citation(article_data)
        
        return {
            "status": "success",
            "publication": article_data
        }
    except Exception as e:
        logger.error(f"Error in get_publication_details: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }

def generate_citation(article: Dict[str, Any]) -> str:
    """
    Generate a formatted citation for an article
    
    Args:
        article: Article data dictionary
        
    Returns:
        Formatted citation string
    """
    try:
        # Extract author names for citation
        author_list = []
        for author in article.get("authors", [])[:6]:  # Limit to first 6 authors
            author_list.append(f"{author.get('lastname', '')} {author.get('initials', '')}")
        
        if len(article.get("authors", [])) > 6:
            author_list.append("et al")
        
        authors_text = ", ".join(author_list)
        
        # Format citation
        journal = article.get("journal", {})
        citation = (
            f"{authors_text}. {article.get('title', '')}. "
            f"{journal.get('name', '')}. {article.get('publication_date', '')};"
            f"{journal.get('volume', '')}"
        )
        
        if journal.get("issue"):
            citation += f"({journal.get('issue')})"
        
        if journal.get("pages"):
            citation += f":{journal.get('pages')}"
        
        citation += "."
        
        if article.get("doi"):
            citation += f" doi: {article.get('doi')}"
        
        return citation
    except Exception as e:
        logger.error(f"Error generating citation: {str(e)}")
        return "Citation generation failed"

@mcp.tool()
async def get_article_statistics(researcher: str) -> Dict[str, Any]:
    """
    Get publication statistics for a specific researcher
    
    Args:
        researcher: Name of the researcher/author
        
    Returns:
        Dictionary with publication statistics
    """
    try:
        # Validate input
        if not researcher or not researcher.strip():
            return {
                "status": "error",
                "message": "Researcher name is required"
            }
        
        # Build search query for this specific researcher
        query = f"{researcher}[Author]"
        
        # Get total publications count (limit=0 just to get count)
        article_ids, total_count = retrieve_article_ids(query, 100)
        
        # Get recent publications to analyze
        if article_ids:
            root = fetch_article_metadata(article_ids[:10])  # Get details for 10 most recent
            articles = ArticleParser.process_articles(root)
            
            # Extract journals and years for analysis
            journals = {}
            years = {}
            
            for article in articles:
                # Count publications by journal
                journal = article.get("journal", {}).get("name")
                if journal and journal != "N/A":
                    journals[journal] = journals.get(journal, 0) + 1
                
                # Count publications by year
                year = article.get("publication_date")
                if year and year != "N/A":
                    years[year] = years.get(year, 0) + 1
            
            # Sort journals and years by count
            top_journals = sorted(journals.items(), key=lambda x: x[1], reverse=True)[:5]
            publication_years = sorted(years.items(), key=lambda x: x[0], reverse=True)
            
            return {
                "status": "success",
                "researcher": researcher,
                "total_publications": total_count,
                "recent_sample_size": len(articles),
                "top_journals": [{"name": j[0], "count": j[1]} for j in top_journals],
                "publication_years": [{"year": y[0], "count": y[1]} for y in publication_years],
                "sample_titles": [a.get("title") for a in articles[:5]]
            }
        else:
            return {
                "status": "success",
                "researcher": researcher,
                "total_publications": 0,
                "message": "No publications found for this researcher"
            }
            
    except Exception as e:
        logger.error(f"Error in get_article_statistics: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }

if __name__ == "__main__":
    mcp.run() 