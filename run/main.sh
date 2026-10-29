#!/bin/bash
set -e

if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
fi

LOG_PATH=log_v3_topn100
TOP_N=100

python generate_docs.py  # Can commnet out if run/documents is not empty
python embedding_docs.py # Can commnet out if run/embeddings is not empty

python retrieve_topk_schema.py --log_path $LOG_PATH --top_n $TOP_N
python add_id.py --log_path $LOG_PATH
python generate_schema.py --log_path $LOG_PATH --is_initial
python complete_schema.py --log_path $LOG_PATH
python postprocess.py --log_path $LOG_PATH
python generate_schema.py --log_path $LOG_PATH
