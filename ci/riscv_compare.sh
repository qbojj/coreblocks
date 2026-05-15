#!/bin/sh
set -eu

ELF_DIR="$1"
SIGN_DIR="test-results-signatures"

echo "Comparing signatures in $SIGN_DIR"

if [ ! -d "$SIGN_DIR" ]; then
  echo "No signatures directory found ($SIGN_DIR)" >&2
  exit 1
fi

failed=0
for sig in $(find "$SIGN_DIR" -type f -name '*.signature' 2>/dev/null); do
  name=$(basename "$sig")
  # Look for a reference signature in the riscv-arch-test repo (common paths)
  ref1="test/external/riscv-arch-test/riscof_work/$name"
  ref2="test/external/riscof/riscof_work/$name"
  if [ -f "$ref1" ]; then
    if ! diff -u "$ref1" "$sig"; then
      echo "Signature differs: $name" >&2
      failed=1
    fi
  elif [ -f "$ref2" ]; then
    if ! diff -u "$ref2" "$sig"; then
      echo "Signature differs: $name" >&2
      failed=1
    fi
  else
    echo "No reference signature found for $name; produced $sig" >&2
  fi
done

if [ "$failed" -ne 0 ]; then
  echo "Signature comparison failed" >&2
  exit 2
fi

echo "Signature comparison complete"
exit 0
