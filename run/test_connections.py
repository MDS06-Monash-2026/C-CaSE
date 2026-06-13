import os
import json
import sqlite3
import pandas as pd
from pathlib import Path
from google.cloud import bigquery

try:
    import snowflake.connector
except ImportError:
    snowflake = None

# Configuration
BQ_CRED_DIR = "bigquery_credentials"
SF_CRED_DIR = "snowflake_credential"
SQLITE_DIR = "resource/databases/spider2-localdb"

def print_box(msg):
    print(f"\n{'='*10} {msg} {'='*10}")

def test_sqlite_deep():
    print_box("TESTING SQLITE: [DB_IMDB]")
    # Looking specifically for the DB_IMDB file
    db_path = Path(SQLITE_DIR) / "Db-IMDB.db" # or .sqlite
    if not db_path.exists():
        db_path = Path(SQLITE_DIR) / "Db-IMDB.sqlite"

    if not db_path.exists():
        print(f"❌ Database file {db_path} not found in {SQLITE_DIR}")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        # Get the first available table name in this specific DB
        tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table';", conn)
        if tables.empty:
            print("⚠️ DB found, but it contains no tables.")
        else:
            target_table = tables.iloc[0]['name']
            print(f"✅ Found Table: [{target_table}] in DB_IMDB")
            df = pd.read_sql(f"SELECT * FROM {target_table} LIMIT 3", conn)
            print(f"📊 Sample Data:\n{df}")
        conn.close()
    except Exception as e:
        print(f"❌ SQLite Error: {e}")

def test_bigquery_deep():
    print_box("TESTING BIGQUERY: [austin_311]")
    json_keys = list(Path(BQ_CRED_DIR).glob("*.json"))
    if not json_keys:
        print("❌ No BQ keys found.")
        return

    # Specific table provided
    target_table = "bigquery-public-data.austin_311.311_service_requests"

    try:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(json_keys[0])
        client = bigquery.Client()
        
        print(f"✅ Querying: {target_table}")
        query = f"SELECT * FROM `{target_table}` LIMIT 3"
        df = client.query(query).to_dataframe()
        print(f"📊 Sample Data:\n{df}")

    except Exception as e:
        print(f"❌ BigQuery Error: {e}")

def test_snowflake_deep():
    print_box("TESTING SNOWFLAKE: [ADS_SPONSORED_BRANDS]")
    cred_files = list(Path(SF_CRED_DIR).glob("*.json"))
    if not cred_files or snowflake is None:
        print("❌ Snowflake credentials or library missing.")
        return

    # Specific table provided
    target_table = "CRYPTO.CRYPTO_ETHEREUM.TRACES"

    try:
        with open(cred_files[0], 'r') as f:
            config = json.load(f)
        
        conn = snowflake.connector.connect(**config)
        cursor = conn.cursor()
        
        print(f"✅ Accessing: {target_table}")
        # Note: Using double quotes for Snowflake identifiers to handle case sensitivity
        cursor.execute(f'SELECT * FROM {target_table} LIMIT 3')
        
        columns = [col[0] for col in cursor.description]
        data = cursor.fetchall()
        df = pd.DataFrame(data, columns=columns)
        print(f"📊 Sample Data:\n{df}")
            
        conn.close()
    except Exception as e:
        print(f"❌ Snowflake Error: {e}")

if __name__ == "__main__":
    test_sqlite_deep()
    test_bigquery_deep()
    test_snowflake_deep()