---
name: gitmore
description: Non-interactive partial git staging. Use when you need to stage specific hunks or lines from a file without interactive prompts.
allowed-tools: Bash(gitmore:*)
---

# gitmore - Non-interactive Partial Git Staging

Use `gitmore add-partial` when you need to selectively stage parts of a file.

## List available hunks

```bash
gitmore add-partial <file> -l
```

Shows all hunks with numbered changed lines.

## Stage specific hunks

```bash
gitmore add-partial <file> -H 1
gitmore add-partial <file> -H 1,3
gitmore add-partial <file> -H 1-3
```

## Stage specific lines within a hunk

```bash
gitmore add-partial <file> -K 2 -L 1-3,5
```

Where `-K` selects the hunk number and `-L` selects line numbers within that hunk.

## When to use

- When committing only part of the changes in a file
- When splitting changes into logical commits
- When you need precise control over what gets staged
