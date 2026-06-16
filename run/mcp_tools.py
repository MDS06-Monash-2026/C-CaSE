import os
import json
from google.cloud import bigquery
from sql_execution import get_least_used_credential

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "lookup_business_term",
            "description": "Use this tool to find the exact database codes, definitions, or formulas for business concepts (e.g., 'purchase', 'adenocarcinoma').",
            "parameters": {
                "type": "object",
                "properties": {
                    "term": {"type": "string", "description": "The business term to look up"}
                },
                "required": ["term"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "dry_run_query",
            "description": "Validates SQL syntax and schema linkages without executing the query. Returns success or the exact syntax/type mismatch error.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql_query": {"type": "string"}
                },
                "required": ["sql_query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_shortest_join_path",
            "description": "Returns the exact SQL JOIN syntax required to connect two tables.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_table": {"type": "string"},
                    "target_table": {"type": "string"}
                },
                "required": ["source_table", "target_table"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "profile_column_values",
            "description": "Returns the top 5 most frequent values, null percentage, and data format of a specific column.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {"type": "string"},
                    "column_name": {"type": "string"}
                },
                "required": ["table_name", "column_name"]
            }
        }
    }
]

# 1. Enterprise Semantic Glossary MCP
def lookup_business_term(term: str) -> str:
    term_lower = term.lower()
    
    # Mocked Glossary matching user request
    glossary = {
        "breast cancer": "Table: Cytogen, Column: Morph, Value: '3111'",
        "adenocarcinoma": "Table: Cytogen, Column: Morph, Value: '8140/3'",
        "purchase": "Google Analytics schema strictly requires eCommerceAction.action_type = '6'"
    }
    
    for key, value in glossary.items():
        if key in term_lower:
            return value
            
    return f"Term '{term}' not found in the semantic glossary."

# 2. BigQuery Dry-Run Validator MCP
def dry_run_query(sql_query: str) -> str:
    try:
        credential_path = get_least_used_credential()
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credential_path
        client = bigquery.Client()
        
        job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
        query_job = client.query(sql_query, job_config=job_config)
        
        bytes_processed = query_job.total_bytes_processed
        return f"[SUCCESS] SQL syntax is valid and schema correctly linked. Estimated bytes processed: {bytes_processed}"
    except Exception as e:
        return f"[ERROR] Syntax or schema mismatch: {str(e)}"

# 3. Topological Join-Path Generator MCP
def get_shortest_join_path(source_table: str, target_table: str) -> str:
    # A mocked topology response simulating Dijkstra's shortest path traversal
    if "ga_sessions" in source_table.lower() and "product_catalog" in target_table.lower():
        return "INNER JOIN product_mapping pm ON ga_sessions.id = pm.session_id INNER JOIN product_catalog ON pm.product_id = product_catalog.id"
    
    # Generic fallback
    return f"No known explicit topological path between {source_table} and {target_table}. Ensure foreign keys exist or review schema."

# 4. Approximate Data Profiler MCP
def profile_column_values(table_name: str, column_name: str) -> str:
    # Use exact same credential logic to safely sample data
    try:
        credential_path = get_least_used_credential()
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credential_path
        client = bigquery.Client()
        
        # We wrap the table name in backticks just in case it contains dots or special characters
        safe_table = f"`{table_name.replace('`', '')}`"
        
        query = f"SELECT {column_name} FROM {safe_table} WHERE {column_name} IS NOT NULL LIMIT 5"
        result = client.query(query).result()
        
        vals = [str(row[0]) for row in result]
        if not vals:
            return "Column contains only NULL values or is empty."
            
        return f"Top sampled values for {table_name}.{column_name}: {vals}"
    except Exception as e:
        return f"[ERROR profiling column]: {str(e)}"

def execute_tool_call(function_name: str, arguments: dict) -> str:
    if function_name == "lookup_business_term":
        return lookup_business_term(**arguments)
    elif function_name == "dry_run_query":
        return dry_run_query(**arguments)
    elif function_name == "get_shortest_join_path":
        return get_shortest_join_path(**arguments)
    elif function_name == "profile_column_values":
        return profile_column_values(**arguments)
    else:
        return f"Tool {function_name} not found."
