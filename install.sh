#!/usr/bin/env bash
#
# Installs the swe-agentic-loop skill into an agent skills directory.
#
#   ./install.sh                  # ~/.copilot/skills (user scope)
#   ./install.sh --project        # ./.github/skills (repository scope)
#   ./install.sh --dir <path>     # custom skills root
#   ./install.sh --force          # overwrite an existing installation
#
set -euo pipefail

SKILL_NAME="swe-agentic-loop"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
SRC_DIR="${SCRIPT_DIR}/skills/${SKILL_NAME}"

DEST_ROOT="${HOME}/.copilot/skills"
FORCE=0

usage() {
  sed -n '2,9p' "${BASH_SOURCE[0]}" | sed 's/^#\s\{0,1\}//'
}

while [ $# -gt 0 ]; do
  case "$1" in
    --project)
      DEST_ROOT="$(pwd -P)/.github/skills"
      shift
      ;;
    --dir)
      if [ $# -lt 2 ] || [ -z "${2:-}" ]; then
        echo "error: --dir requires a path argument" >&2
        exit 2
      fi
      DEST_ROOT="$2"
      shift 2
      ;;
    --force|-f)
      FORCE=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ ! -f "${SRC_DIR}/SKILL.md" ]; then
  echo "error: source skill not found at ${SRC_DIR}/SKILL.md" >&2
  exit 1
fi

DEST_DIR="${DEST_ROOT}/${SKILL_NAME}"

if [ -e "${DEST_DIR}" ] && [ "${FORCE}" -ne 1 ]; then
  echo "error: ${DEST_DIR} already exists. Re-run with --force to overwrite." >&2
  exit 1
fi

# Refuse to clobber a destination that resolves to the source itself.
if [ -d "${DEST_DIR}" ] && [ "$(cd -- "${DEST_DIR}" && pwd -P)" = "${SRC_DIR}" ]; then
  echo "error: destination is the source directory; nothing to do." >&2
  exit 1
fi

mkdir -p "${DEST_ROOT}"

TMP_DIR="$(mktemp -d "${DEST_ROOT}/.${SKILL_NAME}.XXXXXX")"
trap 'rm -rf "${TMP_DIR}"' EXIT

cp -R "${SRC_DIR}/." "${TMP_DIR}/"

rm -rf "${DEST_DIR}"
mv "${TMP_DIR}" "${DEST_DIR}"
trap - EXIT
chmod -R u+rw "${DEST_DIR}"

if [ -d "${DEST_DIR}/scripts" ]; then
  echo "Installed support scripts: $(cd -- "${DEST_DIR}/scripts" && printf '%s ' *)"
fi
echo "Installed ${SKILL_NAME} -> ${DEST_DIR}"
echo "Restart your agent session, then try: /${SKILL_NAME}"
