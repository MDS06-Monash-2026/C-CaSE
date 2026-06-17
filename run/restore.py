import subprocess
import os

files_to_restore = [
    "run/config.py",
    "run/run_diverse_batch.py",
    "run/sql_generation.py",
    "run/sql_revise.py"
]

commit_hash = "af6bad0a95432d7aa069d1eca24a7255821172ee"

for file in files_to_restore:
    try:
        content = subprocess.check_output(['git', 'show', f'{commit_hash}:{file}'], cwd="d:/C-CaSE")
        with open(f"d:/C-CaSE/{file}", "wb") as f:
            f.write(content)
        print(f"Restored {file}")
    except Exception as e:
        print(f"Failed to restore {file}: {e}")

# Remove slayql2_schema_engine.py
slayql2_path = "d:/C-CaSE/run/slayql2_schema_engine.py"
if os.path.exists(slayql2_path):
    os.remove(slayql2_path)
    print("Removed slayql2_schema_engine.py")

print("Restore complete.")
