"""Tests for gitmore add-partial command."""

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from gitmore.add_partial import (
    add_partial,
    build_hunk_header,
    build_patch,
    filter_hunk_lines,
    parse_hunk_header,
    parse_spec,
    split_diff,
    split_hunk,
)

SAMPLE_DIFF = """\
diff --git a/foo.py b/foo.py
index 1234567..abcdefg 100644
--- a/foo.py
+++ b/foo.py
@@ -1,6 +1,7 @@
 import os
 import sys
+import re

 def hello():
     print("hello")
@@ -10,4 +11,4 @@ def hello():
 def goodbye():
-    print("goodbye")
+    print("bye")
     return True
"""

TWO_HUNK_DIFF = """\
diff --git a/bar.py b/bar.py
index 1111111..2222222 100644
--- a/bar.py
+++ b/bar.py
@@ -1,3 +1,4 @@
 line1
+added1
 line2
 line3
@@ -10,3 +11,3 @@ def func():
 old_context
-removed
+replaced
 end_context
"""


# --- parse_hunk_header ---

class TestParseHunkHeader:
    def test_standard_header(self):
        result = parse_hunk_header("@@ -1,6 +1,7 @@ context")
        assert result == (1, 6, 1, 7, " context")

    def test_missing_counts(self):
        result = parse_hunk_header("@@ -1 +1 @@")
        assert result == (1, 1, 1, 1, "")

    def test_only_old_count(self):
        result = parse_hunk_header("@@ -1,3 +1 @@")
        assert result == (1, 3, 1, 1, "")

    def test_invalid_header(self):
        with pytest.raises(ValueError, match="Invalid hunk header"):
            parse_hunk_header("not a header")


# --- parse_spec ---

class TestParseSpec:
    def test_single(self):
        assert parse_spec("2", 5) == {2}

    def test_comma_separated(self):
        assert parse_spec("1,3,5", 5) == {1, 3, 5}

    def test_range(self):
        assert parse_spec("2-4", 5) == {2, 3, 4}

    def test_mixed(self):
        assert parse_spec("1,3-5", 6) == {1, 3, 4, 5}

    def test_out_of_range_filtered(self):
        assert parse_spec("0,3,10", 5) == {3}

    def test_all_out_of_range(self):
        assert parse_spec("10,20", 5) == set()

    def test_spaces(self):
        assert parse_spec("1, 3, 5", 5) == {1, 3, 5}

    def test_duplicates(self):
        assert parse_spec("2,2,2", 5) == {2}

    def test_single_element_range(self):
        assert parse_spec("3-3", 5) == {3}


# --- build_hunk_header ---

class TestBuildHunkHeader:
    def test_with_counts(self):
        assert build_hunk_header(1, 6, 1, 7, " ctx") == "@@ -1,6 +1,7 @@ ctx"

    def test_count_of_one(self):
        assert build_hunk_header(5, 1, 5, 1, "") == "@@ -5 +5 @@"

    def test_roundtrip_with_parse(self):
        header = "@@ -10,4 +11,5 @@ def foo():"
        old_start, old_count, new_start, new_count, context = parse_hunk_header(header)
        rebuilt = build_hunk_header(old_start, old_count, new_start, new_count, context)
        assert rebuilt == header


# --- split_diff ---

class TestSplitDiff:
    def test_two_hunks(self):
        header, hunks = split_diff(SAMPLE_DIFF)
        assert "diff --git" in header
        assert len(hunks) == 2

    def test_header_preserved(self):
        header, _ = split_diff(SAMPLE_DIFF)
        assert "--- a/foo.py" in header
        assert "+++ b/foo.py" in header

    def test_hunk_metadata(self):
        _, hunks = split_diff(SAMPLE_DIFF)
        assert hunks[0]["old_start"] == 1
        assert hunks[0]["new_start"] == 1

    def test_hunk_lines_captured(self):
        _, hunks = split_diff(SAMPLE_DIFF)
        # First hunk has the +import re change
        changed = [l for l in hunks[0]["lines"] if l and l[0] in ("+", "-")]
        assert any("import re" in l for l in changed)

    def test_empty_diff(self):
        header, hunks = split_diff("")
        assert hunks == []

    def test_single_hunk_diff(self):
        single = """\
diff --git a/f.py b/f.py
index aaa..bbb 100644
--- a/f.py
+++ b/f.py
@@ -1,2 +1,3 @@
 line1
+new
 line2
"""
        header, hunks = split_diff(single)
        assert len(hunks) == 1
        assert hunks[0]["old_start"] == 1

    def test_two_hunks_content_separated(self):
        _, hunks = split_diff(TWO_HUNK_DIFF)
        # Hunk 1: addition only
        h1_changes = [l for l in hunks[0]["lines"] if l and l[0] in ("+", "-")]
        assert any("+added1" in l for l in h1_changes)
        assert not any("removed" in l for l in h1_changes)
        # Hunk 2: replacement
        h2_changes = [l for l in hunks[1]["lines"] if l and l[0] in ("+", "-")]
        assert any("-removed" in l for l in h2_changes)
        assert any("+replaced" in l for l in h2_changes)
        assert not any("added1" in l for l in h2_changes)

    def test_two_hunks_counts_match_lines(self):
        _, hunks = split_diff(TWO_HUNK_DIFF)
        for h in hunks:
            actual_old = sum(1 for l in h["lines"] if l and l[0] in (" ", "-"))
            actual_new = sum(1 for l in h["lines"] if l and l[0] in (" ", "+"))
            assert h["old_count"] == actual_old
            assert h["new_count"] == actual_new

    def test_sample_diff_second_hunk_offsets(self):
        _, hunks = split_diff(SAMPLE_DIFF)
        # Second hunk starts at line 10/11
        assert hunks[1]["old_start"] == 10
        assert hunks[1]["new_start"] == 11


# --- split_hunk ---

class TestSplitHunk:
    def test_single_block_not_split(self):
        hunk = {
            "old_start": 1, "old_count": 3, "new_start": 1, "new_count": 4,
            "context": "", "header": "@@ -1,3 +1,4 @@",
            "lines": [" ctx", "+added", " ctx2"],
        }
        result = split_hunk(hunk)
        assert len(result) == 1

    def test_two_blocks_with_large_gap_split(self):
        # Two change blocks separated by 7 context lines (> 3*2=6)
        lines = ["+add1"] + [" ctx"] * 7 + ["+add2"]
        hunk = {
            "old_start": 1, "old_count": 7, "new_start": 1, "new_count": 9,
            "context": "", "header": "@@ -1,7 +1,9 @@",
            "lines": lines,
        }
        result = split_hunk(hunk)
        assert len(result) == 2

    def test_split_hunk_first_part_content(self):
        # Two change blocks separated by 7 context lines
        lines = ["+add1"] + [" ctx"] * 7 + ["+add2"]
        hunk = {
            "old_start": 1, "old_count": 7, "new_start": 1, "new_count": 9,
            "context": " fn", "header": "@@ -1,7 +1,9 @@ fn",
            "lines": lines,
        }
        result = split_hunk(hunk)
        # First sub-hunk should contain +add1 and trailing context
        first_changes = [l for l in result[0]["lines"] if l and l[0] in ("+", "-")]
        assert len(first_changes) == 1
        assert first_changes[0] == "+add1"

    def test_split_hunk_second_part_content(self):
        lines = ["+add1"] + [" ctx"] * 7 + ["+add2"]
        hunk = {
            "old_start": 1, "old_count": 7, "new_start": 1, "new_count": 9,
            "context": " fn", "header": "@@ -1,7 +1,9 @@ fn",
            "lines": lines,
        }
        result = split_hunk(hunk)
        # Second sub-hunk should contain +add2 and leading context
        second_changes = [l for l in result[1]["lines"] if l and l[0] in ("+", "-")]
        assert len(second_changes) == 1
        assert second_changes[0] == "+add2"

    def test_split_hunk_offsets(self):
        # +add1 at position 0, then 7 context, then +add2 at position 8
        # First hunk starts at original old_start=10, new_start=10
        # Second hunk should offset past the first change block + context
        lines = ["+add1"] + [" ctx"] * 7 + ["+add2"]
        hunk = {
            "old_start": 10, "old_count": 7, "new_start": 10, "new_count": 9,
            "context": "", "header": "@@ -10,7 +10,9 @@",
            "lines": lines,
        }
        result = split_hunk(hunk)
        # First sub-hunk should start at original position
        assert result[0]["old_start"] == 10
        assert result[0]["new_start"] == 10
        # Second sub-hunk should be offset
        assert result[1]["old_start"] > 10
        assert result[1]["new_start"] > 10

    def test_split_hunk_headers_are_valid(self):
        lines = ["+add1"] + [" ctx"] * 7 + ["-del1"]
        hunk = {
            "old_start": 5, "old_count": 8, "new_start": 5, "new_count": 8,
            "context": " func", "header": "@@ -5,8 +5,8 @@ func",
            "lines": lines,
        }
        result = split_hunk(hunk)
        assert len(result) == 2
        for h in result:
            # Each header should be parseable
            old_s, old_c, new_s, new_c, ctx = parse_hunk_header(h["header"])
            assert old_s == h["old_start"]
            assert old_c == h["old_count"]
            assert new_s == h["new_start"]
            assert new_c == h["new_count"]
            assert ctx == h["context"]

    def test_split_hunk_counts_match_lines(self):
        lines = ["+add1"] + [" ctx"] * 7 + ["+add2"]
        hunk = {
            "old_start": 1, "old_count": 7, "new_start": 1, "new_count": 9,
            "context": "", "header": "@@ -1,7 +1,9 @@",
            "lines": lines,
        }
        result = split_hunk(hunk)
        for h in result:
            actual_old = sum(1 for l in h["lines"] if l and l[0] in (" ", "-"))
            actual_new = sum(1 for l in h["lines"] if l and l[0] in (" ", "+"))
            assert h["old_count"] == actual_old, f"old_count mismatch: {h['old_count']} != {actual_old}"
            assert h["new_count"] == actual_new, f"new_count mismatch: {h['new_count']} != {actual_new}"

    def test_two_blocks_with_small_gap_not_split(self):
        # Two change blocks separated by 3 context lines (< 3*2=6)
        lines = ["+add1"] + [" ctx"] * 3 + ["+add2"]
        hunk = {
            "old_start": 1, "old_count": 3, "new_start": 1, "new_count": 5,
            "context": "", "header": "@@ -1,3 +1,5 @@",
            "lines": lines,
        }
        result = split_hunk(hunk)
        assert len(result) == 1

    def test_empty_hunk(self):
        hunk = {
            "old_start": 1, "old_count": 0, "new_start": 1, "new_count": 0,
            "context": "", "header": "@@ -1 +1 @@",
            "lines": [],
        }
        result = split_hunk(hunk)
        assert len(result) == 1

    def test_three_blocks_partial_split(self):
        # 3 change blocks: gap1=7 (splittable), gap2=3 (not splittable)
        # Should split into 2 hunks: block1 alone, blocks 2+3 together
        lines = (
            ["+add1"]
            + [" ctx"] * 7
            + ["+add2"]
            + [" ctx"] * 3
            + ["+add3"]
        )
        hunk = {
            "old_start": 1, "old_count": 10, "new_start": 1, "new_count": 13,
            "context": "", "header": "@@ -1,10 +1,13 @@",
            "lines": lines,
        }
        result = split_hunk(hunk)
        assert len(result) == 2

    def test_three_blocks_partial_split_content(self):
        lines = (
            ["+add1"]
            + [" ctx"] * 7
            + ["+add2"]
            + [" ctx"] * 3
            + ["+add3"]
        )
        hunk = {
            "old_start": 1, "old_count": 10, "new_start": 1, "new_count": 13,
            "context": "", "header": "@@ -1,10 +1,13 @@",
            "lines": lines,
        }
        result = split_hunk(hunk)
        # First sub-hunk: only +add1
        first_changes = [l for l in result[0]["lines"] if l and l[0] in ("+", "-")]
        assert first_changes == ["+add1"]
        # Second sub-hunk: +add2 and +add3 (kept together due to small gap)
        second_changes = [l for l in result[1]["lines"] if l and l[0] in ("+", "-")]
        assert second_changes == ["+add2", "+add3"]

    def test_three_blocks_partial_split_counts(self):
        lines = (
            ["+add1"]
            + [" ctx"] * 7
            + ["+add2"]
            + [" ctx"] * 3
            + ["+add3"]
        )
        hunk = {
            "old_start": 1, "old_count": 10, "new_start": 1, "new_count": 13,
            "context": "", "header": "@@ -1,10 +1,13 @@",
            "lines": lines,
        }
        result = split_hunk(hunk)
        for h in result:
            actual_old = sum(1 for l in h["lines"] if l and l[0] in (" ", "-"))
            actual_new = sum(1 for l in h["lines"] if l and l[0] in (" ", "+"))
            assert h["old_count"] == actual_old
            assert h["new_count"] == actual_new


# --- filter_hunk_lines ---

class TestFilterHunkLines:
    def test_select_addition(self):
        hunk = {
            "old_start": 1, "old_count": 2, "new_start": 1, "new_count": 3,
            "context": "",
            "lines": [" ctx", "+added", " ctx2"],
        }
        result = filter_hunk_lines(hunk, {1})
        assert result is not None
        assert any(l.startswith("+") for l in result["lines"])

    def test_select_deletion(self):
        hunk = {
            "old_start": 1, "old_count": 3, "new_start": 1, "new_count": 2,
            "context": "",
            "lines": [" ctx", "-removed", " ctx2"],
        }
        result = filter_hunk_lines(hunk, {1})
        assert result is not None
        assert any(l.startswith("-") for l in result["lines"])

    def test_unselected_deletion_becomes_context(self):
        hunk = {
            "old_start": 1, "old_count": 3, "new_start": 1, "new_count": 4,
            "context": "",
            "lines": [" ctx", "-removed", "+added", " ctx2"],
        }
        # Select only the addition (change 2), not the deletion (change 1)
        result = filter_hunk_lines(hunk, {2})
        assert result is not None
        # The "-removed" should become " removed" (context)
        assert " removed" in result["lines"]

    def test_unselected_addition_removed(self):
        hunk = {
            "old_start": 1, "old_count": 2, "new_start": 1, "new_count": 4,
            "context": "",
            "lines": [" ctx", "+add1", "+add2", " ctx2"],
        }
        # Select only first addition
        result = filter_hunk_lines(hunk, {1})
        assert result is not None
        assert "+add1" in result["lines"]
        assert "+add2" not in result["lines"]

    def test_no_changes_remain(self):
        hunk = {
            "old_start": 1, "old_count": 2, "new_start": 1, "new_count": 3,
            "context": "",
            "lines": [" ctx", "+added", " ctx2"],
        }
        # Select nothing valid
        result = filter_hunk_lines(hunk, set())
        assert result is None

    def test_select_both_addition_and_deletion(self):
        hunk = {
            "old_start": 10, "old_count": 3, "new_start": 10, "new_count": 3,
            "context": "",
            "lines": [" ctx", "-old_line", "+new_line", " ctx2"],
        }
        # Select both the deletion (1) and addition (2)
        result = filter_hunk_lines(hunk, {1, 2})
        assert result is not None
        assert "-old_line" in result["lines"]
        assert "+new_line" in result["lines"]

    def test_select_only_deletion_from_replacement(self):
        hunk = {
            "old_start": 10, "old_count": 3, "new_start": 10, "new_count": 3,
            "context": "",
            "lines": [" ctx", "-old_line", "+new_line", " ctx2"],
        }
        # Select only the deletion, skip the addition
        result = filter_hunk_lines(hunk, {1})
        assert result is not None
        assert "-old_line" in result["lines"]
        assert "+new_line" not in result["lines"]

    def test_header_counts_updated_correctly(self):
        hunk = {
            "old_start": 5, "old_count": 4, "new_start": 5, "new_count": 6,
            "context": " func",
            "lines": [" ctx", "+add1", "+add2", "+add3", " ctx2"],
        }
        # Select only 1 of 3 additions
        result = filter_hunk_lines(hunk, {1})
        assert result is not None
        # old_count=2 (2 context), new_count=3 (2 context + 1 addition)
        assert "@@ -5,2 +5,3 @@ func" == result["header"]

    def test_trailing_empty_line_preserved(self):
        hunk = {
            "old_start": 1, "old_count": 2, "new_start": 1, "new_count": 3,
            "context": "",
            "lines": [" ctx", "+added", ""],
        }
        result = filter_hunk_lines(hunk, {1})
        assert result is not None
        assert "" in result["lines"]


# --- build_patch ---

class TestBuildPatch:
    def test_patch_ends_with_newline(self):
        header = "diff --git a/f b/f\n--- a/f\n+++ b/f"
        hunks = [{"header": "@@ -1,2 +1,3 @@", "lines": [" ctx", "+new", " ctx2"]}]
        result = build_patch(header, hunks)
        assert result.endswith("\n")

    def test_patch_contains_header_and_hunks(self):
        header = "diff --git a/f b/f\n--- a/f\n+++ b/f"
        hunks = [{"header": "@@ -1,2 +1,3 @@", "lines": [" ctx", "+new"]}]
        result = build_patch(header, hunks)
        assert "diff --git" in result
        assert "@@ -1,2 +1,3 @@" in result
        assert "+new" in result

    def test_patch_multiple_hunks(self):
        header = "diff --git a/f b/f\n--- a/f\n+++ b/f"
        hunks = [
            {"header": "@@ -1,2 +1,3 @@", "lines": [" a", "+b", " c"]},
            {"header": "@@ -10,2 +11,3 @@", "lines": [" x", "+y", " z"]},
        ]
        result = build_patch(header, hunks)
        assert "@@ -1,2 +1,3 @@" in result
        assert "@@ -10,2 +11,3 @@" in result
        assert "+b" in result
        assert "+y" in result


# --- CLI: add_partial command ---

class TestAddPartialCLI:
    """Test the click command via CliRunner."""

    def setup_method(self):
        self.runner = CliRunner()

    def _invoke(self, args, diff_output=""):
        with patch("gitmore.add_partial.get_diff", return_value=diff_output):
            return self.runner.invoke(add_partial, args)

    # -- validation --

    def test_lines_without_hunk_errors(self):
        result = self._invoke(["foo.py", "--lines", "1"])
        assert result.exit_code != 0
        assert "--lines requires --hunk" in result.output

    def test_list_with_hunk_errors(self):
        result = self._invoke(["foo.py", "--list", "--hunk", "1"])
        assert result.exit_code != 0
        assert "--list cannot be combined" in result.output

    def test_list_with_lines_errors(self):
        result = self._invoke(["foo.py", "--list", "--lines", "1"])
        assert result.exit_code != 0

    # -- no changes --

    def test_no_unstaged_changes(self):
        result = self._invoke(["foo.py"])
        assert result.exit_code == 0
        assert "No unstaged changes" in result.output

    # -- listing --

    def test_default_lists_hunks(self):
        result = self._invoke(["foo.py"], diff_output=SAMPLE_DIFF)
        assert result.exit_code == 0
        assert "Found 2 hunk(s)" in result.output
        assert "=== Hunk 1 ===" in result.output
        assert "=== Hunk 2 ===" in result.output

    def test_explicit_list_flag(self):
        result = self._invoke(["foo.py", "--list"], diff_output=SAMPLE_DIFF)
        assert result.exit_code == 0
        assert "Found 2 hunk(s)" in result.output

    def test_list_shows_numbered_changes(self):
        result = self._invoke(["foo.py", "--list"], diff_output=SAMPLE_DIFF)
        assert "[1]" in result.output

    # -- hunk staging --

    def test_stage_single_hunk(self):
        with patch("gitmore.add_partial.get_diff", return_value=TWO_HUNK_DIFF), \
             patch("gitmore.add_partial.apply_patch", return_value=True) as mock_apply:
            result = self.runner.invoke(add_partial, ["bar.py", "--hunk", "1"])
        assert result.exit_code == 0
        assert "Staged hunk(s) 1 from bar.py" in result.output
        mock_apply.assert_called_once()

    def test_stage_multiple_hunks(self):
        with patch("gitmore.add_partial.get_diff", return_value=TWO_HUNK_DIFF), \
             patch("gitmore.add_partial.apply_patch", return_value=True) as mock_apply:
            result = self.runner.invoke(add_partial, ["bar.py", "--hunk", "1,2"])
        assert result.exit_code == 0
        assert "Staged hunk(s) 1,2 from bar.py" in result.output
        mock_apply.assert_called_once()

    def test_stage_hunk_range(self):
        with patch("gitmore.add_partial.get_diff", return_value=TWO_HUNK_DIFF), \
             patch("gitmore.add_partial.apply_patch", return_value=True):
            result = self.runner.invoke(add_partial, ["bar.py", "--hunk", "1-2"])
        assert result.exit_code == 0
        assert "Staged hunk(s)" in result.output

    def test_invalid_hunk_number(self):
        with patch("gitmore.add_partial.get_diff", return_value=TWO_HUNK_DIFF):
            result = self.runner.invoke(add_partial, ["bar.py", "--hunk", "99"])
        assert result.exit_code != 0
        assert "No valid hunks selected" in result.output

    # -- line staging --

    def test_stage_lines_from_hunk(self):
        with patch("gitmore.add_partial.get_diff", return_value=TWO_HUNK_DIFF), \
             patch("gitmore.add_partial.apply_patch", return_value=True) as mock_apply:
            result = self.runner.invoke(add_partial, ["bar.py", "--hunk", "2", "--lines", "1"])
        assert result.exit_code == 0
        assert "Staged lines" in result.output
        mock_apply.assert_called_once()

    def test_lines_with_multi_hunk_errors(self):
        with patch("gitmore.add_partial.get_diff", return_value=TWO_HUNK_DIFF):
            result = self.runner.invoke(add_partial, ["bar.py", "--hunk", "1,2", "--lines", "1"])
        assert result.exit_code != 0
        assert "single --hunk number" in result.output

    def test_lines_with_range_hunk_errors(self):
        with patch("gitmore.add_partial.get_diff", return_value=TWO_HUNK_DIFF):
            result = self.runner.invoke(add_partial, ["bar.py", "--hunk", "1-2", "--lines", "1"])
        assert result.exit_code != 0
        assert "single --hunk number" in result.output

    def test_invalid_line_numbers(self):
        with patch("gitmore.add_partial.get_diff", return_value=TWO_HUNK_DIFF):
            result = self.runner.invoke(add_partial, ["bar.py", "--hunk", "1", "--lines", "99"])
        assert result.exit_code != 0
        assert "No valid lines selected" in result.output

    # -- missing file argument --

    def test_missing_file_argument(self):
        result = self.runner.invoke(add_partial, [])
        assert result.exit_code != 0
        assert "Missing argument" in result.output

    # -- filter returns None during line staging --

    def test_line_staging_no_changes_remain(self):
        # Hunk with only an addition; selecting nothing valid → filter returns None
        # Use a diff where hunk 1 has 1 changed line, select line 99 (out of range)
        # Already covered by test_invalid_line_numbers, but this tests the
        # "No changes remain after filtering" path specifically
        single_add_diff = """\
diff --git a/x.py b/x.py
index aaa..bbb 100644
--- a/x.py
+++ b/x.py
@@ -1,3 +1,4 @@
 a
 b
+only_change
 c
"""
        with patch("gitmore.add_partial.get_diff", return_value=single_add_diff), \
             patch("gitmore.add_partial.filter_hunk_lines", return_value=None):
            result = self.runner.invoke(add_partial, ["x.py", "--hunk", "1", "--lines", "1"])
        assert result.exit_code == 0
        assert "No changes remain" in result.output

    # -- patch content verification --

    def test_hunk_staging_patch_content(self):
        """Verify the actual patch sent to apply_patch contains the right hunks."""
        with patch("gitmore.add_partial.get_diff", return_value=TWO_HUNK_DIFF), \
             patch("gitmore.add_partial.apply_patch", return_value=True) as mock_apply:
            self.runner.invoke(add_partial, ["bar.py", "--hunk", "1"])
        patch_text = mock_apply.call_args[0][0]
        assert "diff --git" in patch_text
        assert "+added1" in patch_text
        # Hunk 2 content should NOT be in the patch
        assert "-removed" not in patch_text
        assert "+replaced" not in patch_text

    def test_line_staging_patch_content(self):
        """Verify line-level staging produces correct patch with only selected lines."""
        with patch("gitmore.add_partial.get_diff", return_value=TWO_HUNK_DIFF), \
             patch("gitmore.add_partial.apply_patch", return_value=True) as mock_apply:
            # Hunk 2 has: -removed, +replaced (changes 1 and 2)
            # Select only the addition (change 2)
            self.runner.invoke(add_partial, ["bar.py", "--hunk", "2", "--lines", "2"])
        patch_text = mock_apply.call_args[0][0]
        assert "+replaced" in patch_text
        # The unselected deletion should become context (space-prefixed)
        assert "-removed" not in patch_text
        assert " removed" in patch_text

    def test_stage_all_hunks_patch_content(self):
        """Staging all hunks includes all changes."""
        with patch("gitmore.add_partial.get_diff", return_value=TWO_HUNK_DIFF), \
             patch("gitmore.add_partial.apply_patch", return_value=True) as mock_apply:
            self.runner.invoke(add_partial, ["bar.py", "--hunk", "1-2"])
        patch_text = mock_apply.call_args[0][0]
        assert "+added1" in patch_text
        assert "-removed" in patch_text
        assert "+replaced" in patch_text

    # -- triple conflict --

    def test_list_with_hunk_and_lines_errors(self):
        result = self._invoke(["foo.py", "--list", "--hunk", "1", "--lines", "1"])
        assert result.exit_code != 0
        assert "--list cannot be combined" in result.output

    # -- boundary hunk numbers --

    def test_hunk_zero(self):
        with patch("gitmore.add_partial.get_diff", return_value=TWO_HUNK_DIFF):
            result = self.runner.invoke(add_partial, ["bar.py", "--hunk", "0"])
        assert result.exit_code != 0
        assert "No valid hunks selected" in result.output

    def test_hunk_negative(self):
        """Negative number: parse_spec treats '-1' as range start, produces ValueError."""
        with patch("gitmore.add_partial.get_diff", return_value=TWO_HUNK_DIFF):
            result = self.runner.invoke(add_partial, ["bar.py", "--hunk", "-1"])
        # Click may interpret -1 as a flag; either way it should not succeed
        assert result.exit_code != 0

    def test_hunk_non_numeric(self):
        with patch("gitmore.add_partial.get_diff", return_value=TWO_HUNK_DIFF):
            result = self.runner.invoke(add_partial, ["bar.py", "--hunk", "abc"])
        assert result.exit_code != 0

    # -- short flags --

    def test_short_flag_H(self):
        with patch("gitmore.add_partial.get_diff", return_value=TWO_HUNK_DIFF), \
             patch("gitmore.add_partial.apply_patch", return_value=True):
            result = self.runner.invoke(add_partial, ["bar.py", "-H", "1"])
        assert result.exit_code == 0
        assert "Staged hunk(s) 1" in result.output

    def test_short_flag_l(self):
        result = self._invoke(["foo.py", "-l"], diff_output=SAMPLE_DIFF)
        assert result.exit_code == 0
        assert "Found 2 hunk(s)" in result.output

    def test_short_flag_L(self):
        with patch("gitmore.add_partial.get_diff", return_value=TWO_HUNK_DIFF), \
             patch("gitmore.add_partial.apply_patch", return_value=True):
            result = self.runner.invoke(add_partial, ["bar.py", "-H", "2", "-L", "1"])
        assert result.exit_code == 0
        assert "Staged lines" in result.output

    # -- deletion-only and addition-only diffs --

    def test_deletion_only_diff(self):
        diff = """\
diff --git a/f.py b/f.py
index aaa..bbb 100644
--- a/f.py
+++ b/f.py
@@ -1,3 +1,2 @@
 keep
-deleted
 keep2
"""
        with patch("gitmore.add_partial.get_diff", return_value=diff), \
             patch("gitmore.add_partial.apply_patch", return_value=True) as mock_apply:
            result = self.runner.invoke(add_partial, ["f.py", "--hunk", "1"])
        assert result.exit_code == 0
        assert "Staged" in result.output
        patch_text = mock_apply.call_args[0][0]
        assert "-deleted" in patch_text

    def test_addition_only_diff(self):
        diff = """\
diff --git a/f.py b/f.py
index aaa..bbb 100644
--- a/f.py
+++ b/f.py
@@ -1,2 +1,3 @@
 keep
+added
 keep2
"""
        with patch("gitmore.add_partial.get_diff", return_value=diff), \
             patch("gitmore.add_partial.apply_patch", return_value=True) as mock_apply:
            result = self.runner.invoke(add_partial, ["f.py", "--hunk", "1"])
        assert result.exit_code == 0
        assert "Staged" in result.output
        patch_text = mock_apply.call_args[0][0]
        assert "+added" in patch_text

    # -- line staging: select all lines --

    def test_line_staging_select_all_lines(self):
        with patch("gitmore.add_partial.get_diff", return_value=TWO_HUNK_DIFF), \
             patch("gitmore.add_partial.apply_patch", return_value=True) as mock_apply:
            # Hunk 2 has 2 changed lines (-removed, +replaced), select both
            result = self.runner.invoke(add_partial, ["bar.py", "--hunk", "2", "--lines", "1-2"])
        assert result.exit_code == 0
        assert "Staged lines" in result.output
        patch_text = mock_apply.call_args[0][0]
        assert "-removed" in patch_text
        assert "+replaced" in patch_text

    # -- apply failure during line staging --

    def test_apply_patch_failure_line_staging(self):
        with patch("gitmore.add_partial.get_diff", return_value=TWO_HUNK_DIFF), \
             patch("gitmore.add_partial.apply_patch", return_value=False):
            result = self.runner.invoke(add_partial, ["bar.py", "--hunk", "2", "--lines", "1"])
        assert result.exit_code == 0
        assert "Staged" not in result.output

    # -- parameter order --

    def test_options_before_file(self):
        with patch("gitmore.add_partial.get_diff", return_value=TWO_HUNK_DIFF), \
             patch("gitmore.add_partial.apply_patch", return_value=True):
            result = self.runner.invoke(add_partial, ["--hunk", "1", "bar.py"])
        assert result.exit_code == 0
        assert "Staged hunk(s) 1" in result.output

    def test_lines_before_hunk(self):
        with patch("gitmore.add_partial.get_diff", return_value=TWO_HUNK_DIFF), \
             patch("gitmore.add_partial.apply_patch", return_value=True):
            result = self.runner.invoke(add_partial, ["bar.py", "--lines", "1", "--hunk", "2"])
        assert result.exit_code == 0
        assert "Staged lines" in result.output

    def test_file_between_options(self):
        with patch("gitmore.add_partial.get_diff", return_value=TWO_HUNK_DIFF), \
             patch("gitmore.add_partial.apply_patch", return_value=True):
            result = self.runner.invoke(add_partial, ["--hunk", "2", "bar.py", "--lines", "1"])
        assert result.exit_code == 0
        assert "Staged lines" in result.output

    def test_list_flag_after_file(self):
        result = self._invoke(["foo.py", "-l"], diff_output=SAMPLE_DIFF)
        assert result.exit_code == 0
        assert "Found 2 hunk(s)" in result.output

    def test_list_flag_before_file(self):
        result = self._invoke(["-l", "foo.py"], diff_output=SAMPLE_DIFF)
        assert result.exit_code == 0
        assert "Found 2 hunk(s)" in result.output

    # -- apply failure --

    def test_apply_patch_failure(self):
        with patch("gitmore.add_partial.get_diff", return_value=TWO_HUNK_DIFF), \
             patch("gitmore.add_partial.apply_patch", return_value=False):
            result = self.runner.invoke(add_partial, ["bar.py", "--hunk", "1"])
        assert result.exit_code == 0
        assert "Staged" not in result.output
