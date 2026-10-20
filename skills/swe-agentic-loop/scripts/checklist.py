#!/usr/bin/env python3
"""checklist.py - render / tick / validate the task-spec acceptance checklist.

The checklist is the definition of done, made executable. A box may be ticked
only with the evidence that backs it: ticking without evidence is refused, and
--require-all fails while any box is unticked. Generic: no host paths, no
project names, standard library only.

Usage:
  checklist.py render   --file F
  checklist.py tick     --file F --item N --evidence "EVIDENCE" [--no-write]
  checklist.py validate --file F [--require-all]
  checklist.py --help

  render    print the checklist with a per-box index and state
  tick      mark box N (1-based, in file order) as done and record the evidence
  validate  report ticked/unticked; with --require-all exit non-zero if any box
            is unticked

Exit codes: 0 ok, 1 validation failed (unticked box with --require-all),
2 bad usage / tick without evidence, 3 file error.
"""
import argparse
import re
import sys

BOX = re.compile(r"^(\s*)- \[([ xX])\](\s*)(.*)$")


def show_help():
    print(__doc__.strip())


def read_lines(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read().splitlines(keepends=True)


def box_indices(lines):
    return [i for i, ln in enumerate(lines) if BOX.match(ln)]


def cmd_render(lines):
    idx = 0
    for ln in lines:
        m = BOX.match(ln)
        if m:
            idx += 1
            state = m.group(2)
            text = m.group(4).rstrip("\n")
            print("%2d [%s] %s" % (idx, state, text))
        else:
            sys.stdout.write(ln if ln.endswith("\n") else ln + "\n")
    return 0


def cmd_tick(lines, item, evidence, write, path):
    if not evidence or not evidence.strip():
        print("error: refusing to tick without evidence", file=sys.stderr)
        return 2
    idx = box_indices(lines)
    if item < 1 or item > len(idx):
        print("error: item %d out of range (1..%d)" % (item, len(idx)),
              file=sys.stderr)
        return 2
    pos = idx[item - 1]
    m = BOX.match(lines[pos])
    text = m.group(4).rstrip("\n")
    # Drop any previously recorded evidence so re-ticking stays idempotent.
    text = re.sub(r"\s+--\s+evidence:.*$", "", text)
    newline = "- [x] %s -- evidence: %s\n" % (text, evidence.strip())
    lines[pos] = newline
    if write:
        with open(path, "w", encoding="utf-8") as fh:
            fh.writelines(lines)
    print("ticked box %d: %s" % (item, newline.strip()))
    return 0


def cmd_validate(lines, require_all):
    done = todo = 0
    unticked = []
    for i, ln in enumerate(lines):
        m = BOX.match(ln)
        if not m:
            continue
        if m.group(2).lower() == "x":
            done += 1
        else:
            todo += 1
            unticked.append(m.group(4).rstrip("\n"))
    print("ticked=%d unticked=%d" % (done, todo))
    for u in unticked:
        print("  [ ] %s" % u)
    if require_all and todo > 0:
        print("validate FAILED: %d box(es) unticked" % todo, file=sys.stderr)
        return 1
    return 0


def main(argv):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-h", "--help", action="store_true")
    sub = parser.add_subparsers(dest="cmd")
    for name in ("render", "tick", "validate"):
        p = sub.add_parser(name, add_help=False)
        p.add_argument("--file", required=True)
        p.add_argument("--item", type=int)
        p.add_argument("--evidence", default="")
        p.add_argument("--no-write", action="store_true")
        p.add_argument("--require-all", action="store_true")
        p.add_argument("-h", "--help", action="store_true")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2

    if args.help or not args.cmd:
        show_help()
        return 0 if args.help else 2

    if getattr(args, "help", False):
        show_help()
        return 0

    try:
        lines = read_lines(args.file)
    except OSError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 3

    if args.cmd == "render":
        return cmd_render(lines)
    if args.cmd == "tick":
        if args.item is None:
            print("error: tick requires --item", file=sys.stderr)
            return 2
        return cmd_tick(lines, args.item, args.evidence,
                        not args.no_write, args.file)
    if args.cmd == "validate":
        return cmd_validate(lines, args.require_all)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
