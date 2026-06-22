import os
import pickle
import re
from rank_bm25 import BM25Okapi

def extract_literals(query: str) -> list:
    """
    Extract potential query values/entities from the user question Q
    (e.g., words inside quotes, capitalized names, numbers).
    """
    literals = []
    
    # Words in quotes
    quotes = re.findall(r'["\']([^"\']+)["\']', query)
    literals.extend(quotes)
    
    # Capitalized sequences (heuristics for names)
    caps = re.findall(r'\b[A-Z][a-z]+\b', query)
    literals.extend(caps)
    
    # Numbers
    numbers = re.findall(r'\b\d+(?:\.\d+)?\b', query)
    literals.extend(numbers)
    
    return list(set(literals))


def build_db_value_index(db_connection, db_id: str, output_dir: str = "bm25_indices") -> None:
    """
    Offline Value Extraction.
    db_connection: SQLite connection to the database.
    db_id: Identifier for saving the index.
    """
    os.makedirs(output_dir, exist_ok=True)
    cursor = db_connection.cursor()
    
    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    corpus = []
    mapping = []
    
    for (table_name,) in tables:
        # Get columns
        cursor.execute(f"PRAGMA table_info('{table_name}')")
        columns = cursor.fetchall()
        for col in columns:
            col_name = col[1]
            col_type = col[2].upper()
            if 'TEXT' in col_type or 'VARCHAR' in col_type or 'CHAR' in col_type:
                try:
                    # Extract unique values (limit to 1000 for performance as per specification)
                    cursor.execute(f"SELECT DISTINCT \"{col_name}\" FROM \"{table_name}\" WHERE \"{col_name}\" IS NOT NULL LIMIT 1000")
                    values = cursor.fetchall()
                    for (val,) in values:
                        if isinstance(val, str) and val.strip():
                            corpus.append(val.split()) # Tokenized for BM25
                            mapping.append(f"{table_name}.{col_name}")
                except Exception as e:
                    print(f"Error reading {table_name}.{col_name}: {e}")
                    
    if corpus:
        bm25 = BM25Okapi(corpus)
        index_data = {
            'bm25': bm25,
            'mapping': mapping,
            'corpus_strings': [' '.join(c) for c in corpus]
        }
        with open(os.path.join(output_dir, f"{db_id}_bm25.pkl"), "wb") as f:
            pickle.dump(index_data, f)


def get_value_hints(query: str, db_id: str, indices_dir: str = "bm25_indices", threshold: float = 2.0) -> str:
    """
    Online Value Matching. Extracts query hints based on BM25 match.
    
    Args:
        query: The user question.
        db_id: Database identifier.
        indices_dir: Directory where indexes are stored.
        threshold: Score threshold for BM25 matching.
        
    Returns:
        Formatted prompt injection block.
    """
    index_path = os.path.join(indices_dir, f"{db_id}_bm25.pkl")
    if not os.path.exists(index_path):
        return ""
        
    with open(index_path, "rb") as f:
        index_data = pickle.load(f)
        
    bm25 = index_data['bm25']
    mapping = index_data['mapping']
    corpus_strings = index_data['corpus_strings']
    
    literals = extract_literals(query)
    hints = []
    
    for literal in literals:
        tokenized_query = literal.split()
        if not tokenized_query:
            continue
            
        scores = bm25.get_scores(tokenized_query)
        if len(scores) == 0:
            continue
            
        best_idx = max(range(len(scores)), key=lambda i: scores[i])
        best_score = scores[best_idx]
        
        if best_score > threshold:
            col_path = mapping[best_idx]
            match_val = corpus_strings[best_idx]
            hints.append(f"[Value Hint: Your query term '{literal}' matches value '{match_val}' in column '{col_path}']")
            
    if hints:
        return "\n[VALUE HINTS]\n" + "\n".join(hints) + "\n"
    return ""
