"""Command-line interface.

nl-pii mask  < input.txt > masked.txt  --mapping mapping.json
nl-pii restore < reply.txt --mapping mapping.json
nl-pii check < input.txt            # list what would be masked, exit 1 if anything found
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from nl_zorg_pii.filter import PiiFilter


def _read(path: str | None) -> str:
    return Path(path).read_text(encoding="utf-8") if path else sys.stdin.read()


def cmd_mask(args: argparse.Namespace) -> int:
    f = PiiFilter(extra_names=args.name or (), all_dates=args.all_dates)
    result = f.mask(_read(args.file))
    sys.stdout.write(result.text)
    if args.mapping:
        Path(args.mapping).write_text(
            json.dumps(result.mapping, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if args.verbose:
        print(f"\n[nl-pii] masked: {result.counts()}", file=sys.stderr)
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    mapping = json.loads(Path(args.mapping).read_text(encoding="utf-8"))
    sys.stdout.write(PiiFilter.restore(_read(args.file), mapping))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    f = PiiFilter(extra_names=args.name or (), all_dates=args.all_dates)
    text = _read(args.file)
    matches = f.find(text)
    for m in matches:
        line = text.count("\n", 0, m.start) + 1
        shown = m.value if args.show else "*" * min(len(m.value), 12)
        print(f"line {line}: {m.kind:<14} {shown}")
    print(f"{len(matches)} item(s) found", file=sys.stderr)
    return 1 if matches else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nl-pii", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("file", nargs="?", help="Input file (default: stdin)")
        sp.add_argument("--name", action="append", help="Extra first name to recognise; repeatable")
        sp.add_argument("--all-dates", action="store_true", help="Mask every date, not only DOB")

    m = sub.add_parser("mask", help="Replace personal data with placeholders")
    common(m)
    m.add_argument("--mapping", help="Write placeholder→value mapping to this JSON file")
    m.add_argument("-v", "--verbose", action="store_true")
    m.set_defaults(func=cmd_mask)

    r = sub.add_parser("restore", help="Put original values back using a mapping file")
    r.add_argument("file", nargs="?")
    r.add_argument("--mapping", required=True)
    r.set_defaults(func=cmd_restore)

    c = sub.add_parser("check", help="Report personal data without changing the text")
    common(c)
    c.add_argument("--show", action="store_true", help="Print the matched values in full")
    c.set_defaults(func=cmd_check)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
