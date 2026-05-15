#!/bin/sh
set -e

ELF_DIR="${1:-.}"

echo "Running riscv-arch-test ELFs from: $ELF_DIR"

if [ ! -d "$ELF_DIR" ]; then
  echo "Error: ELF directory not found: $ELF_DIR" >&2
  exit 1
fi

passed=0
failed=0
test_log="riscv-arch-test-results.log"

# Clear log if it exists
> "$test_log"

# Find all ELF files and run them
for elf in $(find "$ELF_DIR" -type f -name '*.elf' 2>/dev/null | sort); do
  test_name=$(basename "$elf" .elf)
  echo "" | tee -a "$test_log"
  echo "=== Running test: $test_name ===" | tee -a "$test_log"
  
  # Run the ELF via cocotb backend (self-checking binary)
  # The test passes/fails based on exit code: 0=pass, non-zero=fail
  if ./scripts/run_signature.py -b cocotb -o /tmp/dummy.sig "$elf" 2>&1 | tee -a "$test_log"; then
    echo "PASS: $test_name" | tee -a "$test_log"
    passed=$((passed+1))
  else
    exit_code=$?
    echo "FAIL: $test_name (exit code: $exit_code)" | tee -a "$test_log"
    failed=$((failed+1))
  fi
done

echo "" | tee -a "$test_log"
echo "=== Test Summary ===" | tee -a "$test_log"
echo "Passed: $passed" | tee -a "$test_log"
echo "Failed: $failed" | tee -a "$test_log"

if [ "$failed" -gt 0 ]; then
  echo "Some tests failed!" >&2
  exit 1
fi

echo "All tests passed!" | tee -a "$test_log"
exit 0
