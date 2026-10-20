#!/usr/bin/env bash
#
# bus-verify.sh - enforce mailbox integrity for one artifact (pointer target).
#
# Because the bus carries pointers, a missing or empty output file is the most
# likely silent break. This check is the executable form of the mailbox-integrity
# rule: it exits non-zero when the artifact is missing or empty, so the rule is
# never discretionary. Contains no host paths and no project names.
#
# Usage:
#   bus-verify.sh <artifact-path> [...]
#
#   -h, --help   show this help
#
# Exit codes:
#   0  every artifact exists and is non-empty
#   1  at least one artifact is missing
#   2  at least one artifact is empty
#   3  bad usage
#
# For each artifact prints:  OK|MISSING|EMPTY  <bytes>  <sha256|->  <path>
set -euo pipefail

usage() {
  sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^#\{1,\} \{0,1\}//'
}

if [ $# -eq 0 ]; then
  echo "error: no artifact path given" >&2
  usage >&2
  exit 3
fi

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
esac

missing=0
empty=0

for path in "$@"; do
  if [ ! -e "${path}" ]; then
    printf 'MISSING  %s  %s\n' "-" "${path}" >&2
    missing=1
    continue
  fi
  bytes="$(wc -c < "${path}" | tr -d '[:space:]')"
  if [ "${bytes}" -eq 0 ]; then
    printf 'EMPTY    0  -  %s\n' "${path}" >&2
    empty=1
    continue
  fi
  if command -v sha256sum >/dev/null 2>&1; then
    digest="$(sha256sum -- "${path}" | awk '{print $1}')"
  else
    digest="$(shasum -a 256 -- "${path}" | awk '{print $1}')"
  fi
  printf 'OK       %s  %s  %s\n' "${bytes}" "${digest}" "${path}"
done

if [ "${missing}" -ne 0 ]; then echo "integrity FAILED: missing artifact(s)" >&2; exit 1; fi
if [ "${empty}" -ne 0 ]; then echo "integrity FAILED: empty artifact(s)" >&2; exit 2; fi
echo "integrity OK"
