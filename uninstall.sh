#!/bin/bash

set -e

(cd ${HOME}/dev/gitmore && uv pip uninstall gitmore 2>/dev/null || true)
rm -f ${HOME}/bin/gitmore

echo "Uninstalled gitmore"
