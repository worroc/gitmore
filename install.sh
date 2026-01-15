#!/bin/bash

set -e

GITMORE_DIR="$(cd "$(dirname "$0")" && pwd)"

# install uv if not installed
command -v uv >/dev/null || pipx install uv

# initialize uv project and sync dependencies
(cd "${GITMORE_DIR}" && uv sync)

# create wrapper script
mkdir -p ${HOME}/bin

cat > ${HOME}/bin/gitmore << EOF
#!/bin/bash
${GITMORE_DIR}/.venv/bin/python -m gitmore "\$@"
EOF

chmod +x ${HOME}/bin/gitmore

echo "Installed gitmore to ~/bin/gitmore"
echo "Make sure ~/bin is in your PATH"
