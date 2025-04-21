# Medical Literature Research Tool

An advanced Model Content Protocol (MCP) server providing tools to search, analyze, and retrieve academic medical papers from the PubMed database.

## Features

- Search for medical literature using topics and researcher names
- Retrieve comprehensive publication details with structured metadata
- Generate formatted citations for publications
- Analyze researcher publication statistics and patterns
- Advanced error handling with retry mechanisms
- Detailed performance metrics

## Installation

1. Clone this repository:
   ```bash
   git clone <repository-url>
   cd medical-literature-tool
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the project root if needed for configuration

## Usage

1. Start the server:
   ```bash
   mcp run pubmed_server.py
   ```

   For development mode:
   ```bash
   mcp dev pubmed_server.py
   ```

2. Or add the server to your MCP client configuration.

## API Tools

### 1. find_articles

Search for medical literature matching specified topics and researchers.

Parameters:
- `topics` (List[str]): Medical topics or keywords to search in titles and abstracts
- `researchers` (List[str]): Researcher/author names to search for
- `result_limit` (int): Maximum number of results to return (default: 15)

Returns:
- Dictionary with search results, metadata, and performance metrics

### 2. get_publication_details

Retrieve comprehensive details for a specific publication, including a formatted citation.

Parameters:
- `article_id` (str): PubMed ID of the article to retrieve

Returns:
- Dictionary containing detailed article metadata and citation

### 3. get_article_statistics

Analyze publication patterns for a specific researcher.

Parameters:
- `researcher` (str): Name of the researcher/author to analyze

Returns:
- Dictionary with publication statistics, including total count, top journals, and publication years

## Technical Implementation

The server is built with a robust architecture:

- **Object-Oriented Design**: Using classes for better code organization
- **Advanced Error Handling**: Request retry mechanism for API reliability
- **Performance Monitoring**: Timing and metrics for search operations
- **Enhanced Data Structures**: Nested JSON responses with rich metadata
- **Logging System**: Rotating logs with detailed error tracking
- **Modular Components**: Separation of concerns between query building, API requests, and data parsing
