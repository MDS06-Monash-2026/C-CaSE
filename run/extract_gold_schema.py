import json
import os
# pyrefly: ignore [missing-import]
import sqlglot
# pyrefly: ignore [missing-import]
import sqlglot.expressions as exp

def extract_schema(sql_file, dialect=None):
    if not os.path.exists(sql_file):
        return [], []
        
    with open(sql_file, "r", encoding="utf-8") as f:
        sql = f.read()
    
    try:
        tables = set()
        columns = set()
        for statement in sqlglot.parse(sql, read=dialect):
            if statement is None:
                continue
            for table in statement.find_all(exp.Table):
                if table.name:
                    tables.add(table.name.lower())
            for col in statement.find_all(exp.Column):
                if col.name:
                    columns.add(col.name.lower())
        return list(tables), list(columns)
    except Exception as e:
        print(f"Failed to parse {sql_file}: {e}")
        return [], []

import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subset_file", required=True)
    args = parser.parse_args()
    
    gold_dir = "../evaluation_suite/gold/sql"
    
    with open(args.subset_file, "r", encoding="utf-8") as f:
        subset = json.load(f)
    
    gold_schema = {}
    for inst_id in subset.keys():
        dialect = None
        if inst_id.startswith("bq") or inst_id.startswith("ga"):
            dialect = "bigquery"
        elif inst_id.startswith("sf"):
            dialect = "snowflake"
        elif inst_id.startswith("local"):
            dialect = "sqlite"
            
        sql_path = os.path.join(gold_dir, f"{inst_id}.sql")
        tables, columns = extract_schema(sql_path, dialect)
        gold_schema[inst_id] = {
            "tables": tables,
            "columns": columns
        }
        
    with open("gold_schema_columns.json", "w", encoding="utf-8") as f:
        json.dump(gold_schema, f, indent=4)
        
    print("Gold schema extraction complete.")

if __name__ == "__main__":
    main()
