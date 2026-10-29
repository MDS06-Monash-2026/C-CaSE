import os
import json
import sqlite3
import glob
import pickle
from rank_bm25 import BM25Okapi


def index_dir():
    return os.environ.get("SLAYQL_BM25_DIR", "bm25_indices")

def extract_and_build(corpus, mapping, db_id):
    if corpus:
        bm25 = BM25Okapi(corpus)
        index_data = {
            'bm25': bm25,
            'mapping': mapping,
            'corpus_strings': [' '.join(c) for c in corpus]
        }
        with open(os.path.join(index_dir(), f"{db_id}_bm25.pkl"), "wb") as f:
            pickle.dump(index_data, f)
        print(f"Successfully built index for {db_id}")
    else:
        with open(os.path.join(index_dir(), f"{db_id}_empty.txt"), "w") as f:
            f.write("empty")
        print(f"No textual values extracted for {db_id}")

def build_sqlite(db_path, db_name):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    corpus = []
    mapping = []
    for (table_name,) in tables:
        cursor.execute(f"PRAGMA table_info('{table_name}')")
        columns = cursor.fetchall()
        for col in columns:
            col_name = col[1]
            col_type = col[2].upper()
            if any(t in col_type for t in ['TEXT', 'VARCHAR', 'CHAR', 'STRING']):
                try:
                    cursor.execute(f'SELECT DISTINCT "{col_name}" FROM "{table_name}" WHERE "{col_name}" IS NOT NULL LIMIT 1000')
                    values = cursor.fetchall()
                    for (val,) in values:
                        if isinstance(val, str) and val.strip():
                            corpus.append(val.split())
                            mapping.append(f"{table_name}.{col_name}")
                except Exception as e:
                    pass
    conn.close()
    extract_and_build(corpus, mapping, db_name)

def build_bigquery(db_name, bq_client):
    corpus = []
    mapping = []
    try:
        with open("documents/bigquery.json", "r", encoding="utf-8") as f:
            docs = json.load(f)
        tables = docs.get(db_name, {})
        for table_id, table_info in tables.items():
            columns = table_info.get("columns", {})
            for col_name, col_metadata in columns.items():
                if "column type: STRING" in col_metadata or "column type: TEXT" in col_metadata:
                    query = f"SELECT DISTINCT `{col_name}` FROM `{table_id}` WHERE `{col_name}` IS NOT NULL LIMIT 1000"
                    try:
                        query_job = bq_client.query(query)
                        results = query_job.result()
                        for row in results:
                            val = row[0]
                            if isinstance(val, str) and val.strip():
                                corpus.append(val.split())
                                mapping.append(f"{table_id}.{col_name}")
                    except Exception as e:
                        pass
    except Exception as e:
        print(f"Failed to process BQ db {db_name}: {e}")
    extract_and_build(corpus, mapping, db_name)

def build_snowflake(db_name, sf_conn):
    corpus = []
    mapping = []
    try:
        with open("documents/snowflake.json", "r", encoding="utf-8") as f:
            docs = json.load(f)
        tables = docs.get(db_name, {})
        cursor = sf_conn.cursor()
        
        # Snowflake fully qualified names are typically DB.SCHEMA.TABLE. 
        # We can query them directly.
        for table_id, table_info in tables.items():
            columns = table_info.get("columns", {})
            for col_name, col_metadata in columns.items():
                col_type = ""
                for line in col_metadata.split('\n'):
                    if line.startswith("column type:"):
                        col_type = line.replace("column type:", "").strip().upper()
                        break
                
                if any(t in col_type for t in ['TEXT', 'VARCHAR', 'STRING']):
                    query = f'SELECT DISTINCT "{col_name}" FROM {table_id} WHERE "{col_name}" IS NOT NULL LIMIT 1000'
                    try:
                        cursor.execute(query)
                        values = cursor.fetchall()
                        for (val,) in values:
                            if isinstance(val, str) and val.strip():
                                corpus.append(val.split())
                                mapping.append(f"{table_id}.{col_name}")
                    except Exception as e:
                        pass
    except Exception as e:
        print(f"Failed to process Snowflake db {db_name}: {e}")
    finally:
        if 'cursor' in locals():
            cursor.close()
    extract_and_build(corpus, mapping, db_name)


def build_all_indices(data_file="subset_diverse_20_evaluation.json"):
    os.makedirs(index_dir(), exist_ok=True)
    with open(data_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    sqlite_dbs = set()
    bq_dbs = set()
    sf_dbs = set()
    
    for instance_id, info in data.items():
        db_name = info["db_name"]
        if instance_id.startswith("local"):
            sqlite_dbs.add(db_name)
        elif instance_id.startswith("bq") or instance_id.startswith("ga"):
            bq_dbs.add(db_name)
        elif instance_id.startswith("sf"):
            sf_dbs.add(db_name)
            
    print(f"Found {len(sqlite_dbs)} SQLite, {len(bq_dbs)} BigQuery, {len(sf_dbs)} Snowflake DBs.")
    
    # Process SQLite
    for db_name in sorted(list(sqlite_dbs)):
        if os.path.exists(os.path.join(index_dir(), f"{db_name}_bm25.pkl")) or os.path.exists(os.path.join(index_dir(), f"{db_name}_empty.txt")):
            print(f"Skipping {db_name}, already built.")
            continue
        db_path = os.path.join("resource", "databases", "spider2-localdb", f"{db_name}.sqlite")
        if os.path.exists(db_path):
            build_sqlite(db_path, db_name)
            
    # Process BQ
    if bq_dbs:
        from google.cloud import bigquery
        bq_creds = glob.glob(os.path.join("bigquery_credentials", "**", "*.json"), recursive=True)
        if bq_creds:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = bq_creds[0]
            try:
                bq_client = bigquery.Client()
                for db_name in sorted(list(bq_dbs)):
                    if os.path.exists(os.path.join(index_dir(), f"{db_name}_bm25.pkl")) or os.path.exists(os.path.join(index_dir(), f"{db_name}_empty.txt")):
                        print(f"Skipping {db_name}, already built.")
                        continue
                    build_bigquery(db_name, bq_client)
            except Exception as e:
                print(f"Failed to initialize BQ client: {e}")
        else:
            print("Failed to initialize BQ client: No credentials found in bigquery_credentials folder.")
            
    # Process Snowflake
    if sf_dbs:
        import snowflake.connector
        try:
            with open(os.path.join("snowflake_credential", "snowflake_credential.json")) as f:
                sf_creds = json.load(f)
            sf_conn = snowflake.connector.connect(**sf_creds)
            for db_name in sorted(list(sf_dbs)):
                if os.path.exists(os.path.join(index_dir(), f"{db_name}_bm25.pkl")) or os.path.exists(os.path.join(index_dir(), f"{db_name}_empty.txt")):
                    print(f"Skipping {db_name}, already built.")
                    continue
                build_snowflake(db_name, sf_conn)
            sf_conn.close()
        except Exception as e:
            print(f"Failed to initialize Snowflake client: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--data_file', type=str, default="subset_diverse_20_evaluation.json")
    args = parser.parse_args()
    build_all_indices(args.data_file)
