import os
import glob
import warnings
from google.cloud import bigquery

# Suppress the BigQuery Storage REST API warning to keep logs clean
warnings.filterwarnings("ignore", category=UserWarning, module="google.cloud.bigquery")

def test_credentials():
    cred_paths = glob.glob(os.path.join("bigquery_credentials", "**", "*.json"), recursive=True)
    
    if not cred_paths:
        print("No JSON credentials found in bigquery_credentials/ folder.")
        return

    print(f"Found {len(cred_paths)} credential(s) to test...\n")
    print("-" * 60)

    for path in cred_paths:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path
        filename = os.path.basename(path)
        
        try:
            client = bigquery.Client()
            # Run an extremely lightweight query just to test authentication and quotas
            query_job = client.query("SELECT 1 AS test_connection")
            results = query_job.result().to_dataframe(create_bqstorage_client=False)
            
            if not results.empty and results.iloc[0]['test_connection'] == 1:
                print(f"[✅ SUCCESS] {filename} is authenticated and working.")
            else:
                print(f"[⚠️ WARNING] {filename} connected but returned unexpected result.")
                
        except Exception as e:
            error_msg = str(e)
            if "Quota" in error_msg or "403 Quota" in error_msg:
                print(f"[🛑 QUOTA EXCEEDED] {filename} has exhausted its BigQuery API quota limit.")
            elif "Permission" in error_msg or "403" in error_msg:
                print(f"[❌ PERMISSION DENIED] {filename} lacks permissions or the service account is disabled.")
            else:
                print(f"[❌ ERROR] {filename} failed to connect:\n   -> {error_msg.splitlines()[0]}")
                
    print("-" * 60)

if __name__ == "__main__":
    test_credentials()
