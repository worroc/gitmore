#!/bin/bash

set -e

GITMORE_DIR="$(cd "$(dirname "$0")" && pwd)"

(cd "${GITMORE_DIR}" && uv pip uninstall gitmore 2>/dev/null || true)
rm -f ${HOME}/bin/gitmore

echo "Uninstalled gitmore"
