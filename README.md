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
