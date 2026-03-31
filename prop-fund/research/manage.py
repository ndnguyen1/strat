#!/usr/bin/env python3
"""
Twitter/X account tracker for crypto options & DeFi research.
Usage:
  python manage.py add @handle
  python manage.py list
  python manage.py list --focus options
  python manage.py list --type builder
  python manage.py list --quality 4
  python manage.py search gamma
  python manage.py edit @handle
  python manage.py stats
"""

import csv
import sys
import os
import argparse
from datetime import date
from tabulate import tabulate

CSV_PATH = os.path.join(os.path.dirname(__file__), "accounts.csv")

FIELDS = ["handle", "name", "focus", "type", "quality", "active", "notes", "source", "added_date"]

FOCUS_OPTIONS  = ["options", "defi", "both", "macro", "research"]
TYPE_OPTIONS   = ["builder", "analyst", "trader", "researcher", "educator", "fund"]
QUALITY_RANGE  = range(1, 6)  # 1–5


def load() -> list[dict]:
    if not os.path.exists(CSV_PATH):
        return []
    with open(CSV_PATH, newline="") as f:
        return list(csv.DictReader(f))


def save(rows: list[dict]):
    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def normalize_handle(h: str) -> str:
    return h.lstrip("@").lower()


def prompt(label: str, options: list = None, default: str = "") -> str:
    if options:
        label = f"{label} [{'/'.join(options)}]"
    if default:
        label = f"{label} (default: {default})"
    val = input(f"  {label}: ").strip()
    if not val and default:
        return default
    if options and val not in options:
        print(f"    Invalid choice. Options: {options}")
        return prompt(label, options, default)
    return val


def cmd_add(args):
    rows = load()
    handle = normalize_handle(args.handle)

    if any(r["handle"] == handle for r in rows):
        print(f"@{handle} already exists. Use `edit` to update.")
        return

    print(f"\nAdding @{handle}")
    name    = prompt("Name / display name")
    focus   = prompt("Focus", FOCUS_OPTIONS)
    type_   = prompt("Type", TYPE_OPTIONS)
    quality = prompt("Quality score (1=meh, 5=must follow)", list(map(str, QUALITY_RANGE)))
    active  = prompt("Still active?", ["yes", "no"], default="yes")
    notes   = prompt("Notes (what makes them worth following)")
    source  = prompt("How did you find them?", default="manual")

    row = {
        "handle":     handle,
        "name":       name,
        "focus":      focus,
        "type":       type_,
        "quality":    quality,
        "active":     active,
        "notes":      notes,
        "source":     source,
        "added_date": date.today().isoformat(),
    }
    rows.append(row)
    save(rows)
    print(f"\nSaved @{handle}.")


def cmd_edit(args):
    rows = load()
    handle = normalize_handle(args.handle)
    match = [r for r in rows if r["handle"] == handle]
    if not match:
        print(f"@{handle} not found.")
        return

    row = match[0]
    print(f"\nEditing @{handle} (press Enter to keep current value)")

    for field in ["name", "focus", "type", "quality", "active", "notes", "source"]:
        opts = None
        if field == "focus":   opts = FOCUS_OPTIONS
        if field == "type":    opts = TYPE_OPTIONS
        if field == "quality": opts = list(map(str, QUALITY_RANGE))
        if field == "active":  opts = ["yes", "no"]

        current = row[field]
        label = f"{field} (current: {current!r})"
        val = prompt(label, opts, default=current)
        row[field] = val

    save(rows)
    print(f"\nUpdated @{handle}.")


def cmd_list(args):
    rows = load()

    if args.focus:
        rows = [r for r in rows if r["focus"] == args.focus]
    if args.type:
        rows = [r for r in rows if r["type"] == args.type]
    if args.quality:
        rows = [r for r in rows if int(r.get("quality") or 0) >= args.quality]
    if args.active:
        rows = [r for r in rows if r["active"] == "yes"]

    rows = sorted(rows, key=lambda r: int(r.get("quality") or 0), reverse=True)

    if not rows:
        print("No accounts match your filters.")
        return

    display = [
        {
            "handle":  "@" + r["handle"],
            "name":    r["name"],
            "focus":   r["focus"],
            "type":    r["type"],
            "quality": r["quality"],
            "active":  r["active"],
            "notes":   r["notes"][:60] + ("…" if len(r["notes"]) > 60 else ""),
        }
        for r in rows
    ]
    print(tabulate(display, headers="keys", tablefmt="rounded_outline"))
    print(f"\n{len(rows)} account(s)")


def cmd_search(args):
    rows = load()
    q = args.query.lower()
    matches = [
        r for r in rows
        if q in r["handle"].lower()
        or q in r["name"].lower()
        or q in r["notes"].lower()
        or q in r["focus"].lower()
    ]
    if not matches:
        print("No matches.")
        return

    display = [
        {
            "handle":  "@" + r["handle"],
            "name":    r["name"],
            "focus":   r["focus"],
            "quality": r["quality"],
            "notes":   r["notes"][:70],
        }
        for r in matches
    ]
    print(tabulate(display, headers="keys", tablefmt="rounded_outline"))


def cmd_stats(args):
    rows = load()
    if not rows:
        print("No accounts yet.")
        return

    total = len(rows)
    by_focus = {}
    by_type  = {}
    for r in rows:
        by_focus[r["focus"]] = by_focus.get(r["focus"], 0) + 1
        by_type[r["type"]]   = by_type.get(r["type"], 0) + 1

    active = sum(1 for r in rows if r["active"] == "yes")
    avg_q  = sum(int(r.get("quality") or 0) for r in rows) / total

    print(f"\nTotal accounts : {total}")
    print(f"Active         : {active}")
    print(f"Avg quality    : {avg_q:.1f}/5\n")
    print("By focus:")
    for k, v in sorted(by_focus.items(), key=lambda x: -x[1]):
        print(f"  {k:<12} {v}")
    print("\nBy type:")
    for k, v in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {k:<12} {v}")


def main():
    parser = argparse.ArgumentParser(description="Crypto Twitter account tracker")
    sub = parser.add_subparsers(dest="cmd")

    p_add = sub.add_parser("add", help="Add an account")
    p_add.add_argument("handle")

    p_edit = sub.add_parser("edit", help="Edit an account")
    p_edit.add_argument("handle")

    p_list = sub.add_parser("list", help="List accounts")
    p_list.add_argument("--focus",   choices=FOCUS_OPTIONS)
    p_list.add_argument("--type",    choices=TYPE_OPTIONS, dest="type")
    p_list.add_argument("--quality", type=int, metavar="MIN")
    p_list.add_argument("--active",  action="store_true")

    p_search = sub.add_parser("search", help="Search accounts")
    p_search.add_argument("query")

    sub.add_parser("stats", help="Summary stats")

    args = parser.parse_args()

    dispatch = {
        "add":    cmd_add,
        "edit":   cmd_edit,
        "list":   cmd_list,
        "search": cmd_search,
        "stats":  cmd_stats,
    }

    if args.cmd not in dispatch:
        parser.print_help()
        return

    try:
        from tabulate import tabulate  # noqa: F401
    except ImportError:
        print("Missing dependency. Run: pip install tabulate")
        sys.exit(1)

    dispatch[args.cmd](args)


if __name__ == "__main__":
    main()
