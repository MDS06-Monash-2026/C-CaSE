import numpy as np
import networkx as nx
from typing import Dict, Any

def build_schema_graph(db_metadata: Dict[str, Any]) -> nx.Graph:
    """
    Construct schema graph G dynamically from db_metadata.
    
    Args:
        db_metadata: Dictionary containing schema information. Expected to have:
            - 'foreign_keys': list of tuples like (table1, col1, table2, col2)
            - 'tables': list of table names
            
    Returns:
        nx.Graph where nodes are tables and edges exist for PK-FK relationships.
    """
    G = nx.Graph()
    
    if "foreign_keys" in db_metadata and db_metadata["foreign_keys"]:
        for fk in db_metadata["foreign_keys"]:
            # Format expected: (t1, c1, t2, c2)
            if len(fk) >= 4:
                t1, _, t2, _ = fk[:4]
                G.add_edge(t1.lower(), t2.lower())
    elif "table_info" in db_metadata:
        # Heuristic fallback: link tables if they share standardized column names
        table_info = db_metadata["table_info"]
        tables = list(table_info.keys())
        for i in range(len(tables)):
            for j in range(i+1, len(tables)):
                t1 = tables[i]
                t2 = tables[j]
                c1 = table_info[t1].get("columns", {}).keys()
                c2 = table_info[t2].get("columns", {}).keys()
                
                # Standardize strings: lowercase and strip underscores
                norm_c1 = {c.lower().replace("_", "") for c in c1}
                norm_c2 = {c.lower().replace("_", "") for c in c2}
                
                if norm_c1.intersection(norm_c2):
                    G.add_edge(t1.lower(), t2.lower())
                
    if "tables" in db_metadata:
        for table in db_metadata["tables"]:
            t_name = table.lower()
            if t_name not in G:
                G.add_node(t_name)
                
    return G

def propagate_relevance(initial_similarities: Dict[str, float], db_metadata: Dict[str, Any], alpha: float = 0.7) -> Dict[str, float]:
    """
    Propagate semantic relevance across the physical schema graph (RBP).
    
    Args:
        initial_similarities: Mapping of 'table.column' to raw cosine similarities.
        db_metadata: Schema graph details (PK/FK).
        alpha: Damping factor for propagation step.
        
    Returns:
        A dictionary with the updated similarities S_propagated.
    """
    G = build_schema_graph(db_metadata)
    tables = list(G.nodes())
    
    if not tables:
        return initial_similarities
        
    table_to_idx = {t: i for i, t in enumerate(tables)}
    n_tables = len(tables)
    
    # Extract table-level initial similarities (taking the max similarity among retrieved columns for a table)
    S_dense = np.zeros(n_tables)
    for col_path, sim in initial_similarities.items():
        if '.' in col_path:
            t_name = col_path.split('.')[0].lower()
            if t_name in table_to_idx:
                idx = table_to_idx[t_name]
                if sim > S_dense[idx]:
                    S_dense[idx] = sim
                    
    # Build transition matrix W = D^{-1} A
    A = nx.adjacency_matrix(G, nodelist=tables).toarray()
    D_diag = A.sum(axis=1)
    
    W = np.zeros_like(A, dtype=float)
    for i in range(n_tables):
        if D_diag[i] > 0:
            W[i] = A[i] / D_diag[i]
        else:
            # Isolated node, self-loop
            W[i, i] = 1.0
            
    # Propagate similarities
    # S_table_propagated = alpha * S_dense + (1 - alpha) * W * S_dense
    S_table_propagated = alpha * S_dense + (1 - alpha) * np.dot(W, S_dense)
    
    # Map back the propagated table relevance to columns
    # Re-calculate the column-level propagated relevance
    S_propagated = {}
    for col_path, sim in initial_similarities.items():
        if '.' in col_path:
            t_name = col_path.split('.')[0].lower()
            if t_name in table_to_idx:
                idx = table_to_idx[t_name]
                # Modifying the prompt's S_propagated definition to blend base col similarity and propagated table context
                S_propagated[col_path] = alpha * sim + (1 - alpha) * S_table_propagated[idx]
            else:
                S_propagated[col_path] = sim
        else:
            S_propagated[col_path] = sim
            
    return S_propagated
