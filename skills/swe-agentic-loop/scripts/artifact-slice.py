#!/usr/bin/env python3
"""artifact-slice.py - shrink a diff to a diffstat plus only the wanted hunks.

The orchestrator measures once and hands the agent a small results file; the
agent judges, it does not measure. This tool is how a 78 KB diff becomes a few
KB of relevant hunks for the Tier B executive. Generic: no host paths, no
project names, no dependencies beyond python3.

Usage:
  artifact-slice.py --diff FILE [--path PATTERN ...] [--max-bytes N]
  artifact-slice.py --file FILE  [--path PATTERN ...] [--max-bytes N]
  artifact-slice.py              [--path PATTERN ...] [--max-bytes N]   # stdin
  artifact-slice.py --stat-only  --diff FILE

  --diff FILE     read the unified diff from FILE
  --path PATTERN  keep only file sections whose path contains PATTERN
                  (repeatable; default: keep every section)
  --max-bytes N   hard cap on emitted bytes (default 8192)
  --stat-only     print only the diffstat
  -h, --help      show this help

Exit codes: 0 ok, 2 bad usage, 1 read error.
"""
import argparse
import sys


def show_help():
    print(__doc__.strip())


def split_sections(text):
    """Split a unified diff into (path, section_text) file sections."""
    sections = []
    cur_path = None
    cur_lines = []
    for line in text.splitlines(keepends=True):
        if line.startswith("diff --git "):
            if cur_lines:
                sections.append((cur_path, "".join(cur_lines)))
            cur_lines = [line]
            cur_path = None
            parts = line.split()
            if len(parts) >= 4:
                cur_path = parts[3]
                if cur_path.startswith("b/"):
                    cur_path = cur_path[2:]
        else:
            cur_lines.append(line)
    if cur_lines:
        sections.append((cur_path, "".join(cur_lines)))
    return sections


def diffstat(name, text):
    add = del_ = 0
    for line in text.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            add += 1
        elif line.startswith("-") and not line.startswith("---"):
            del_ += 1
    return add, del_


def main(argv):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--diff")
    parser.add_argument("--file")
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--max-bytes", type=int, default=8192)
    parser.add_argument("--stat-only", action="store_true")
    parser.add_argument("-h", "--help", action="store_true")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2

    if args.help:
        show_help()
        return 0

    if args.diff:
        try:
            with open(args.diff, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 1
    elif args.file:
        try:
            with open(args.file, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 1
    else:
        text = sys.stdin.read()

    sections = split_sections(text)

    stat_lines = []
    selected = []
    for name, body in sections:
        add, del_ = diffstat(name, body)
        stat_lines.append(" %-40s | %4d %s" % (name or "?", add + del_,
                                               "+" * min(add, 40)))
        if args.path:
            if any(pat in (name or "") for pat in args.path):
                selected.append((name, body))
        else:
            selected.append((name, body))

    header = "diffstat:\n" + ("\n".join(stat_lines) if stat_lines else " (empty)")
    if args.stat_only:
        out = header + "\n"
    else:
        out = header + "\n"
        for name, body in selected:
            out += body

    raw = out.encode("utf-8")
    if len(raw) > args.max_bytes:
        marker = "\n... [artifact-slice: output truncated at %d bytes]\n" % args.max_bytes
        keep = args.max_bytes - len(marker.encode("utf-8"))
        if keep < 0:
            keep = 0
        raw = raw[:keep] + marker.encode("utf-8")
    sys.stdout.write(raw.decode("utf-8", errors="replace"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
