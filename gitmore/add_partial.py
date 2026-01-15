"""Stage specific hunks or lines from a file non-interactively."""

import re
import subprocess
import sys

import click


def run_git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def get_diff(file_path: str) -> str:
    result = run_git("diff", "--", file_path)
    return result.stdout


def parse_hunk_header(header: str) -> tuple[int, int, int, int, str]:
    """Parse @@ -old_start,old_count +new_start,new_count @@ context."""
    match = re.match(r"@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@(.*)", header)
    if not match:
        raise ValueError(f"Invalid hunk header: {header}")
    old_start = int(match.group(1))
    old_count = int(match.group(2)) if match.group(2) else 1
    new_start = int(match.group(3))
    new_count = int(match.group(4)) if match.group(4) else 1
    context = match.group(5)
    return old_start, old_count, new_start, new_count, context


def split_hunk(hunk: dict, context_lines: int = 3) -> list[dict]:
    """Split a hunk into smaller hunks at context boundaries."""
    lines = hunk["lines"]
    if not lines:
        return [hunk]

    # Find change blocks (groups of consecutive +/- lines)
    blocks = []
    current_block_start = None
    current_block_end = None

    for i, line in enumerate(lines):
        if line and line[0] in ("+", "-"):
            if current_block_start is None:
                current_block_start = i
            current_block_end = i
        elif current_block_start is not None:
            blocks.append((current_block_start, current_block_end))
            current_block_start = None
            current_block_end = None

    if current_block_start is not None:
        blocks.append((current_block_start, current_block_end))

    if len(blocks) <= 1:
        return [hunk]

    # Check if blocks can be split (need enough context between them)
    split_points = []
    for i in range(len(blocks) - 1):
        end_of_current = blocks[i][1]
        start_of_next = blocks[i + 1][0]
        gap = start_of_next - end_of_current - 1
        if gap >= context_lines * 2:
            split_points.append(i)

    if not split_points:
        return [hunk]

    # Split into multiple hunks
    result = []
    old_line = hunk["old_start"]
    new_line = hunk["new_start"]

    block_ranges = []
    prev_split = -1
    for sp in split_points:
        block_ranges.append((prev_split + 1, sp))
        prev_split = sp
    block_ranges.append((prev_split + 1, len(blocks) - 1))

    for first_block_idx, last_block_idx in block_ranges:
        first_block = blocks[first_block_idx]
        last_block = blocks[last_block_idx]

        start_idx = max(0, first_block[0] - context_lines)
        end_idx = min(len(lines) - 1, last_block[1] + context_lines)

        # Handle trailing empty line
        while end_idx < len(lines) - 1 and lines[end_idx + 1] == "":
            end_idx += 1

        # Calculate line offsets
        old_offset = 0
        new_offset = 0
        for i in range(start_idx):
            if lines[i] and lines[i][0] in (" ", "-"):
                old_offset += 1
            if lines[i] and lines[i][0] in (" ", "+"):
                new_offset += 1

        mini_lines = lines[start_idx:end_idx + 1]
        old_count = sum(1 for l in mini_lines if l and l[0] in (" ", "-"))
        new_count = sum(1 for l in mini_lines if l and l[0] in (" ", "+"))

        mini_hunk = {
            "old_start": hunk["old_start"] + old_offset,
            "old_count": old_count,
            "new_start": hunk["new_start"] + new_offset,
            "new_count": new_count,
            "context": hunk["context"],
            "lines": mini_lines,
            "header": build_hunk_header(
                hunk["old_start"] + old_offset,
                old_count,
                hunk["new_start"] + new_offset,
                new_count,
                hunk["context"],
            ),
        }
        result.append(mini_hunk)

    return result


def split_diff(diff: str) -> tuple[str, list[dict]]:
    """Split diff into header and list of hunks with metadata."""
    lines = diff.split("\n")
    header_lines = []
    raw_hunks = []
    current_hunk = None
    in_header = True

    for line in lines:
        if line.startswith("@@"):
            in_header = False
            if current_hunk:
                raw_hunks.append(current_hunk)
            old_start, old_count, new_start, new_count, context = parse_hunk_header(line)
            current_hunk = {
                "header": line,
                "old_start": old_start,
                "old_count": old_count,
                "new_start": new_start,
                "new_count": new_count,
                "context": context,
                "lines": [],
            }
        elif in_header:
            header_lines.append(line)
        elif current_hunk is not None:
            current_hunk["lines"].append(line)

    if current_hunk:
        raw_hunks.append(current_hunk)

    # Split hunks into smallest possible chunks
    hunks = []
    for hunk in raw_hunks:
        hunks.extend(split_hunk(hunk))

    return "\n".join(header_lines), hunks


def parse_spec(spec: str, total: int) -> set[int]:
    """Parse specification like '1,3,5' or '1-3' or '1,3-5'."""
    result = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            result.update(range(int(start), int(end) + 1))
        else:
            result.add(int(part))
    return {n for n in result if 1 <= n <= total}


def build_hunk_header(old_start: int, old_count: int, new_start: int, new_count: int, context: str) -> str:
    """Build @@ header line."""
    old_part = f"-{old_start},{old_count}" if old_count != 1 else f"-{old_start}"
    new_part = f"+{new_start},{new_count}" if new_count != 1 else f"+{new_start}"
    return f"@@ {old_part} {new_part} @@{context}"


def filter_hunk_lines(hunk: dict, selected_lines: set[int]) -> dict | None:
    """
    Filter a hunk to include only selected changed lines.

    selected_lines are 1-indexed positions within the changed lines of the hunk.
    Context lines are always preserved.
    Unselected - lines become context lines.
    Unselected + lines are removed.
    """
    lines = hunk["lines"]
    new_lines = []

    # Number changed lines (+ and -)
    change_num = 0
    for line in lines:
        if not line:  # empty line at end
            new_lines.append(line)
            continue

        prefix = line[0] if line else " "
        content = line[1:] if line else ""

        if prefix in ("+", "-"):
            change_num += 1
            if change_num in selected_lines:
                new_lines.append(line)
            elif prefix == "-":
                # Convert unselected deletion to context
                new_lines.append(" " + content)
            # Unselected + lines are simply omitted
        else:
            # Context line - always keep
            new_lines.append(line)

    # Recalculate counts
    old_count = sum(1 for l in new_lines if l and l[0] in (" ", "-"))
    new_count = sum(1 for l in new_lines if l and l[0] in (" ", "+"))

    if old_count == new_count and not any(l and l[0] in ("+", "-") for l in new_lines):
        # No actual changes remain
        return None

    return {
        "header": build_hunk_header(hunk["old_start"], old_count, hunk["new_start"], new_count, hunk["context"]),
        "lines": new_lines,
    }


def build_patch(header: str, hunks: list[dict]) -> str:
    """Build a patch string from header and hunks."""
    parts = [header]
    for hunk in hunks:
        parts.append(hunk["header"])
        parts.extend(hunk["lines"])
    return "\n".join(parts)


def apply_patch(patch: str) -> bool:
    """Apply patch to git index."""
    result = subprocess.run(
        ["git", "apply", "--cached", "-"],
        input=patch,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        click.echo(f"Error applying patch: {result.stderr}", err=True)
        return False
    return True


@click.command("add-partial")
@click.argument("file")
@click.option("--list", "-l", "list_hunks", is_flag=True, help="List available hunks")
@click.option("--hunks", "-H", help="Hunk numbers to stage (e.g., '1,3,5' or '1-3')")
@click.option("--hunk", "-k", type=int, help="Single hunk number for line-level staging")
@click.option("--lines", "-L", help="Line numbers within hunk to stage (e.g., '1-3,5')")
def add_partial(file: str, list_hunks: bool, hunks: str, hunk: int, lines: str):
    """
    Stage specific hunks or lines from a file non-interactively.

    \b
    Examples:
        gitmore add-partial myfile.py --list
        gitmore add-partial myfile.py --hunks 1,3
        gitmore add-partial myfile.py --hunk 2 --lines 1-3
    """
    diff = get_diff(file)
    if not diff:
        click.echo(f"No unstaged changes in {file}")
        return

    header, hunk_list = split_diff(diff)

    if not hunk_list:
        click.echo("No hunks found")
        return

    if list_hunks:
        click.echo(f"Found {len(hunk_list)} hunk(s) in {file}:\n")
        for i, h in enumerate(hunk_list, 1):
            click.echo(f"=== Hunk {i} ===")
            click.echo(h["header"])

            # Number and display changed lines
            change_num = 0
            for line in h["lines"]:
                if line and line[0] in ("+", "-"):
                    change_num += 1
                    click.echo(f"  [{change_num}] {line}")
                else:
                    click.echo(f"      {line}")
            click.echo()
        return

    if hunk and lines:
        # Line-level staging within a single hunk
        if hunk < 1 or hunk > len(hunk_list):
            click.echo(f"Invalid hunk number {hunk} (available: 1-{len(hunk_list)})", err=True)
            sys.exit(1)

        target_hunk = hunk_list[hunk - 1]
        # Count changed lines in this hunk
        total_changes = sum(1 for l in target_hunk["lines"] if l and l[0] in ("+", "-"))
        selected = parse_spec(lines, total_changes)

        if not selected:
            click.echo(f"No valid lines selected (available: 1-{total_changes})", err=True)
            sys.exit(1)

        filtered = filter_hunk_lines(target_hunk, selected)
        if not filtered:
            click.echo("No changes remain after filtering")
            return

        patch = build_patch(header, [filtered])
        if apply_patch(patch):
            click.echo(f"Staged lines {lines} from hunk {hunk} of {file}")
        return

    if hunks:
        # Hunk-level staging
        selected = parse_spec(hunks, len(hunk_list))
        if not selected:
            click.echo(f"No valid hunks selected (available: 1-{len(hunk_list)})", err=True)
            sys.exit(1)

        selected_hunks = []
        for i in sorted(selected):
            h = hunk_list[i - 1]
            selected_hunks.append({
                "header": h["header"],
                "lines": h["lines"],
            })

        patch = build_patch(header, selected_hunks)
        if apply_patch(patch):
            click.echo(f"Staged hunk(s) {hunks} from {file}")
        return

    click.echo("Specify --list, --hunks, or --hunk with --lines")
    sys.exit(1)
# Another test
