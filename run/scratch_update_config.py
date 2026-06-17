import re

def update_config():
    with open(r"d:\C-CaSE\run\config.py", "r", encoding="utf-8") as f:
        content = f.read()

    # Remove SCHEMA_LINKING
    content = re.sub(r'SCHEMA_LINKING\s*=\s*"""[\s\S]*?"""\s*', '', content)
    # Remove USER_INPUT
    content = re.sub(r'USER_INPUT\s*=\s*"""[\s\S]*?"""\s*', '', content)
    # Remove SQL_GENERATION
    content = re.sub(r'SQL_GENERATION\s*=\s*"""[\s\S]*?"""\s*', '', content)
    # Remove REVISE_ERROR
    content = re.sub(r'REVISE_ERROR\s*=\s*"""[\s\S]*?"""\s*', '', content)

    # New Prompts
    new_prompts = """
SEMANTIC_ANCHORING = \"\"\"
[SYSTEM INSTRUCTION]
You are a highly efficient semantic routing model. Your sole objective is to identify the "Terminal Tables" (the source and destination tables) required to answer the user's query.
You will be provided with a user question and a compressed list of available database tables and their core concepts.

[DATABASE TABLES]
{list_of_all_tables_with_one_line_summaries}

[USER QUESTION]
{user_question}

[TASK]
Identify ONLY the tables directly mentioned or conceptually required by the user's question. Do not attempt to find bridge tables, mapping tables, or foreign keys—the downstream deterministic graph algorithm will handle join paths.

[OUTPUT FORMAT - STRICT JSON]
{
  "source_tables": ["table_name_1"],
  "destination_tables": ["table_name_2"]
}
\"\"\"

SINGLE_PASS_SQL_GENERATION = \"\"\"
[SYSTEM INSTRUCTION]
You are an expert SQL Data Engineer. You are provided with a perfectly resolved, topologically accurate, and highly compressed database sub-schema. 
All necessary bridge tables and join paths are guaranteed to be present in this schema.

[TSCG COMPRESSED SCHEMA]
{tscg_distilled_steiner_tree_schema}

[USER QUESTION]
{user_question}

[TASK]
Generate the exact, highly optimized {SQL_DIALECT} query to answer the user's question. 
- Use the exact table and column names provided in the schema.
- Pay strict attention to aggregations (SUM, AVG, MAX), GROUP BY clauses, and date filtering logic.
- ONLY return the exact columns requested by the user. Do not return extra columns.

[OUTPUT]
```sql
-- Your SQL query here
```
\"\"\"

SEMANTIC_DISAMBIGUATION = \"\"\"
[SYSTEM INSTRUCTION]
You are a diagnostic SQL logic verifier. A previous generation attempt resulted in high epistemic uncertainty due to a semantic collision between two or more highly similar columns in the schema.

[USER QUESTION]
{user_question}

[AMBIGUOUS SUSPECT ELEMENTS]
We have identified the following columns that could mathematically satisfy the query, but have different semantic meanings:
1. {suspect_column_A} (Description: {desc_A})
2. {suspect_column_B} (Description: {desc_B})

[TASK]
Perform a counterfactual simulation in your reasoning. 
1. State the Average Treatment Effect (ATE) or business outcome if we filter/aggregate using Column A versus Column B.
2. Based strictly on the semantics of the User Question, declare which column is the correct target and which is the distractor.

[OUTPUT FORMAT]
<reasoning>
If I use {suspect_column_A}, the query will measure [X]. If I use {suspect_column_B}, the query will measure [Y]. The user is asking for [Z], therefore...
</reasoning>
<prune_target>{distractor_column_name}</prune_target>
<keep_target>{correct_column_name}</keep_target>
\"\"\"
"""
    
    with open(r"d:\C-CaSE\run\config.py", "w", encoding="utf-8") as f:
        f.write(new_prompts + "\n" + content)
        
if __name__ == "__main__":
    update_config()
