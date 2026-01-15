# gitmore

Git utilities for non-interactive partial staging.

## Installation

```bash
./install.sh
```

This installs `gitmore` to `~/bin/gitmore`. Ensure `~/bin` is in your PATH.

## Uninstallation

```bash
./uninstall.sh
```

## Commands

### add-partial

Stage specific hunks or lines from a file without interactive prompts.

**List available hunks:**
```bash
gitmore add-partial myfile.py --list
```

**Stage specific hunks:**
```bash
gitmore add-partial myfile.py --hunks 1,3
gitmore add-partial myfile.py --hunks 1-3
```

**Stage specific lines within a hunk:**
```bash
gitmore add-partial myfile.py --hunk 2 --lines 1-3,5
```

## Claude Code Integration

Teach Claude Code when and how to use gitmore:

```bash
./add-claude-skill.sh
```

This installs a skill to `~/.claude/skills/gitmore` that helps Claude
use gitmore for selective staging tasks.
