#!/usr/bin/env bash

cd ~/tdb-alpaca/alpaca-scalper || exit 1

source ~/tdb-alpaca/.venv/bin/activate

set -a
source .env
set +a

echo "Bot environment loaded."
echo "Python: $(which python)"
echo "Key length: ${#APCA_API_KEY_ID}"
echo "Secret length: ${#APCA_API_SECRET_KEY}"
