#!/usr/bin/env bash

set -euo pipefail

mode="${1:?mode must be startup or cleanup}"
case "$mode" in
  startup | cleanup) ;;
  *)
    echo "mode must be startup or cleanup" >&2
    exit 64
    ;;
esac

managed_paths=(
  .venv
  .ci-site
  dist
  build
  .eggs
  netbox_proxbox.egg-info
  .ruff_cache
  .pytest_cache
  .coverage
  htmlcov
)
source_roots=(netbox_proxbox proxbox_cli tests)
stale_symlink=0

for target in "${managed_paths[@]}"; do
  if test -L "$target"; then
    find "$target" -maxdepth 0 -type l -delete
    stale_symlink=1
  elif test -e "$target"; then
    find "$target" -depth -delete
  fi
done

for source_root in "${source_roots[@]}"; do
  if test -L "$source_root"; then
    find "$source_root" -maxdepth 0 -type l -delete
    stale_symlink=1
    continue
  fi
  if ! test -d "$source_root"; then
    if test "$mode" = startup; then
      echo "required checkout path is missing: $source_root" >&2
      exit 66
    fi
    continue
  fi
  while IFS= read -r -d '' target; do
    find "$target" -maxdepth 0 -type l -delete
    stale_symlink=1
  done < <(
    find "$source_root" -type l \
      \( -name '*.pyc' -o -name '*.pyo' -o -name __pycache__ \) -print0
  )
  find "$source_root" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
  find "$source_root" -depth -type d -name __pycache__ -empty -delete
done

if test "$mode" = startup && test "$stale_symlink" -ne 0; then
  echo "removed unsafe generated-state symlink; refusing this run" >&2
  exit 65
fi
