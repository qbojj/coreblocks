#!/bin/sh
set -eu

ELF_DIR="$1"
OUT_DIR="test-results-signatures"
mkdir -p "$OUT_DIR"

echo "Running ELFs from: $ELF_DIR"

count=0
for elf in $(find "$ELF_DIR" -type f -name '*.elf' 2>/dev/null); do
  base=$(basename "$elf" .elf)
  out="$OUT_DIR/$base.signature"
  echo "Running $elf -> $out"
  # Use pysim backend by default (no external simulator required)
  if ! ./scripts/run_signature.py -b pysim -o "$out" "$elf"; then
    echo "Test run failed for $elf" >&2
  fi
  count=$((count+1))
done

echo "Ran $count ELF(s). Signatures in $OUT_DIR"

exit 0
