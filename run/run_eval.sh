#!/bin/bash
set -e

# Load environment variables from the .env file
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

echo "Starting evaluation pipeline (Custom Subset Configuration)..."
python evaluate_subset.py --data_file spider2_data.json "$@"
