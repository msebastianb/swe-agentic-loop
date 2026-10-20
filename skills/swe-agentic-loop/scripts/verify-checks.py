#!/usr/bin/env python3
"""verify-checks.py - one deterministic bundle of pre-submission checks.

The expensive part of a review is the number of turns, not the message size:
the reviewer spent its turns *measuring* (CR counts, JSON parse, changed files,
forbidden strings, diffstat). Those are deterministic, so the orchestrator runs
them once here and hands the agent a small results file; the agent judges, it
does not measure. Generic: no host paths, no project names, standard library
only.

Usage:
  verify-checks.py --repo DIR [--files F ...] [--forbid S ...]
                   [--checklist F] [--out FILE]

  --repo DIR       repository / work tree to inspect (required)
  --files F ...    files to scan for CR/CRLF and ```json blocks
                   (default: the modified files reported by git)
  --forbid S ...   forbidden substrings to scan for in the scanned files
  --checklist F    checklist file whose [ ]/[x] state is summarised
  --out FILE       write the compact report here (default: stdout)
  -h, --help       show this help

Exit codes: 0 report produced, 2 bad usage, 1 could not inspect the repo.
"""
import argparse
import json
import os
import subprocess
import sys


def show_help():
    print(__doc__.strip())


def git(repo, *args):
    try:
        p = subprocess.run(["git", "-C", repo, *args],
                           capture_output=True, text=True)
        return p.returncode, p.stdout, p.stderr
    except OSError as exc:
        return 127, "", str(exc)


def cr_counts(path):
    with open(path, "rb") as fh:
        data = fh.read()
    cr = data.count(b"\r")
    crlf = data.count(b"\r\n")
    return len(data), cr, crlf


def json_blocks(path):
    """Return (ok_count, [error messages]) for ```json fences in a text file."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError as exc:
        return 0, ["cannot read: %s" % exc]
    ok = 0
    errors = []
    inside = False
    buf = []
    start = 0
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("```json"):
            inside = True
            buf = []
            start = i
            continue
        if inside and stripped.startswith("```"):
            inside = False
            blob = "\n".join(buf)
            try:
                json.loads(blob)
                ok += 1
            except json.JSONDecodeError as exc:
                errors.append("%s:%d json parse error: %s" % (path, start, exc))
            buf = []
            continue
        if inside:
            buf.append(line)
    if inside:
        errors.append("%s:%d unterminated ```json block" % (path, start))
    return ok, errors


def main(argv):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--repo", required=False)
    parser.add_argument("--files", nargs="*", default=None)
    parser.add_argument("--forbid", action="append", default=[])
    parser.add_argument("--checklist")
    parser.add_argument("--out")
    parser.add_argument("-h", "--help", action="store_true")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2

    if args.help:
        show_help()
        return 0
    if not args.repo:
        print("error: --repo is required", file=sys.stderr)
        return 2

    repo = args.repo
    if not os.path.isdir(repo):
        print("error: not a directory: %s" % repo, file=sys.stderr)
        return 1

    lines = []
    lines.append("verify-checks bundle")
    lines.append("repo: %s" % repo)

    # Modified files, from git status --porcelain.
    rc, out, err = git(repo, "status", "--porcelain")
    if rc != 0:
        lines.append("git status: FAILED (%s)" % (err.strip() or rc))
        modified = []
    else:
        modified = [ln[3:].strip() for ln in out.splitlines() if ln.strip()]
        lines.append("modified files (%d):" % len(modified))
        for m in modified:
            lines.append("  %s" % m)

    scan_files = args.files if args.files is not None else modified
    lines.append("scanned files (%d): %s" % (len(scan_files), ", ".join(scan_files) or "-"))

    # CR / CRLF counts.
    lines.append("CR/CRLF counts:")
    cr_total = 0
    for f in scan_files:
        p = f if os.path.isabs(f) else os.path.join(repo, f)
        if not os.path.isfile(p):
            lines.append("  %s: MISSING" % f)
            continue
        size, cr, crlf = cr_counts(p)
        cr_total += cr
        lines.append("  %s: bytes=%d CR=%d CRLF=%d" % (f, size, cr, crlf))
    lines.append("CR total: %d" % cr_total)

    # ```json block parse.
    lines.append("json blocks:")
    json_ok = 0
    json_errors = []
    for f in scan_files:
        p = f if os.path.isabs(f) else os.path.join(repo, f)
        if not os.path.isfile(p):
            continue
        ok, errs = json_blocks(p)
        json_ok += ok
        json_errors.extend(errs)
        if ok or errs:
            lines.append("  %s: ok=%d errors=%d" % (f, ok, len(errs)))
    for e in json_errors:
        lines.append("  ERROR %s" % e)
    lines.append("json blocks parsed ok: %d, errors: %d" % (json_ok, len(json_errors)))

    # Forbidden strings.
    lines.append("forbidden strings:")
    for s in args.forbid:
        hits = []
        for f in scan_files:
            p = f if os.path.isabs(f) else os.path.join(repo, f)
            if not os.path.isfile(p):
                continue
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as fh:
                    for i, line in enumerate(fh, 1):
                        if s in line:
                            hits.append("%s:%d" % (f, i))
            except OSError:
                continue
        lines.append("  %r: %d hit(s)%s" % (s, len(hits),
                     (" -> " + ", ".join(hits[:10])) if hits else ""))

    # Checklist state.
    if args.checklist and os.path.isfile(args.checklist):
        done = todo = 0
        with open(args.checklist, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                ls = line.strip()
                if ls.startswith("- [x]") or ls.startswith("- [X]"):
                    done += 1
                elif ls.startswith("- [ ]"):
                    todo += 1
        lines.append("checklist:")
        lines.append("  ticked=%d unticked=%d" % (done, todo))
    elif args.checklist:
        lines.append("checklist: MISSING (%s)" % args.checklist)

    # git diff --check (whitespace errors).
    rc, out, err = git(repo, "diff", "--check")
    lines.append("git diff --check: %s" % ("clean" if rc == 0 else "ISSUES"))
    for ln in out.splitlines()[:20]:
        lines.append("  %s" % ln)

    report = "\n".join(lines) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report)
        print("wrote %d bytes to %s" % (len(report.encode("utf-8")), args.out))
    else:
        sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
