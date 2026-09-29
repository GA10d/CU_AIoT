#!/bin/zsh
set -e
cd "$(dirname "$0")"

PYTHON_BIN=""
for candidate in \
  "/opt/anaconda3/envs/aiot/bin/python" \
  "$HOME/anaconda3/envs/aiot/bin/python" \
  "$HOME/miniconda3/envs/aiot/bin/python"
do
  if [[ -x "$candidate" ]]; then
    PYTHON_BIN="$candidate"
    break
  fi
done

if [[ -z "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

echo "Using Python: $PYTHON_BIN"
exec "$PYTHON_BIN" app.py
