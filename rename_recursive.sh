#!/usr/bin/env bash
# Usage: ./rename_recursive.sh <directory> <old_text> <new_text>
# Replaces <old_text> with <new_text> inside file contents and in filenames recursively.

set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <directory> <old_text> <new_text>"
  exit 1
fi

DIR="$1"
OLD="$2"
NEW="$3"

if [[ ! -d "$DIR" ]]; then
  echo "Error: '$DIR' is not a directory."
  exit 1
fi

content_count=0
rename_count=0

# Replace text inside file contents first (before any renames)
while IFS= read -r -d '' path; do
  if [[ -f "$path" ]] && grep -qF -- "$OLD" "$path" 2>/dev/null; then
    sed -i "s|${OLD}|${NEW}|g" "$path"
    echo "Updated contents: $path"
    content_count=$((content_count + 1))
  fi
done < <(find "$DIR" -type f -print0)

# Then rename files and directories (deepest first to avoid broken paths)
while IFS= read -r -d '' path; do
  base=$(basename "$path")
  if [[ "$base" == *"$OLD"* ]]; then
    new_base="${base//"$OLD"/"$NEW"}"
    new_path="$(dirname "$path")/$new_base"
    mv -- "$path" "$new_path"
    echo "Renamed: $path -> $new_path"
    rename_count=$((rename_count + 1))
  fi
done < <(find "$DIR" -depth -print0)

echo "Done. $content_count file(s) updated, $rename_count item(s) renamed."
