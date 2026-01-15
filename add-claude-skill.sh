#!/bin/bash

set -e

GITMORE_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="${HOME}/.claude/skills/gitmore"

mkdir -p "${SKILL_DIR}"
cp "${GITMORE_DIR}/SKILL.md" "${SKILL_DIR}/SKILL.md"

echo "Added gitmore skill to ${SKILL_DIR}"
