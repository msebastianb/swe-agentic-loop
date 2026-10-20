#!/usr/bin/env bash
#
# bus-init.sh - create the run-scoped artifact mailbox for one loop run.
#
# The mailbox holds pointers, not payloads: the task spec and its acceptance
# checklist are written once here and every later spawn points at these files.
# Idempotent: re-running against the same bus reuses it and never overwrites an
# existing artifact. Contains no host paths and no project names.
#
# Usage:
#   bus-init.sh [--bus DIR] [--task FILE] [--checklist FILE] [--name NAME]
#
#   --bus DIR        bus root to use/create (default: a fresh mktemp -d)
#   --task FILE      task-spec file to copy in as task-spec.md
#   --checklist FILE checklist file to copy in as checklist.md
#   --name NAME      label recorded in the bus README
#   -h, --help       show this help
#
# Prints shell-style KEY=VALUE lines (BUS_DIR, TASK_SPEC, CHECKLIST, OUTPUT_DIR)
# for the caller to pass on to the spawned agents.
set -euo pipefail

BASE_DIR=""
TASK_SRC=""
CHECK_SRC=""
RUN_NAME=""

usage() {
  sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^#\{1,\} \{0,1\}//'
}

while [ $# -gt 0 ]; do
  case "$1" in
    --bus)       [ $# -ge 2 ] || { echo "error: --bus needs a path" >&2; exit 2; };      BASE_DIR="$2"; shift 2 ;;
    --task)      [ $# -ge 2 ] || { echo "error: --task needs a path" >&2; exit 2; };     TASK_SRC="$2"; shift 2 ;;
    --checklist) [ $# -ge 2 ] || { echo "error: --checklist needs a path" >&2; exit 2; }; CHECK_SRC="$2"; shift 2 ;;
    --name)      [ $# -ge 2 ] || { echo "error: --name needs a value" >&2; exit 2; };     RUN_NAME="$2"; shift 2 ;;
    -h|--help)   usage; exit 0 ;;
    *) echo "error: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [ -n "${BASE_DIR}" ]; then
  mkdir -p -- "${BASE_DIR}"
else
  BASE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/swe-bus.XXXXXX")"
fi
BUS_DIR="$(cd -- "${BASE_DIR}" && pwd -P)"

if [ -f "${BUS_DIR}/.bus-init" ]; then
  echo "bus already initialised - reusing (no state lost)" >&2
else
  : > "${BUS_DIR}/.bus-init"
  {
    printf 'run: %s\n' "${RUN_NAME:-unnamed}"
    printf 'created: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } > "${BUS_DIR}/README.bus"
fi

# Copy each artifact in only when it is not already present and non-empty,
# so a second run cannot clobber what the first one wrote.
if [ -n "${TASK_SRC}" ] && [ ! -s "${BUS_DIR}/task-spec.md" ]; then
  cp -- "${TASK_SRC}" "${BUS_DIR}/task-spec.md"
fi
if [ -n "${CHECK_SRC}" ] && [ ! -s "${BUS_DIR}/checklist.md" ]; then
  cp -- "${CHECK_SRC}" "${BUS_DIR}/checklist.md"
fi

[ -f "${BUS_DIR}/task-spec.md" ] || : > "${BUS_DIR}/task-spec.md"
[ -f "${BUS_DIR}/checklist.md" ] || : > "${BUS_DIR}/checklist.md"
mkdir -p -- "${BUS_DIR}/artifacts"

printf 'BUS_DIR=%s\n'    "${BUS_DIR}"
printf 'TASK_SPEC=%s\n'  "${BUS_DIR}/task-spec.md"
printf 'CHECKLIST=%s\n'  "${BUS_DIR}/checklist.md"
printf 'OUTPUT_DIR=%s\n' "${BUS_DIR}/artifacts"
