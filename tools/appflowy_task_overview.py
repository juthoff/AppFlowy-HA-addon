#!/usr/bin/env python3
"""Collect the cards of every board whose status is in a chosen set onto one page.

The page (default "Offene Aufgaben") is found by name anywhere in the sidebar,
created in the first space if missing, and fully rewritten on each run: one
section per status, and within it one heading per board (page mention plus
sidebar path) listing the card titles.

  AF_BASE=... AF_EMAIL=... AF_PASSWORD=... python3 appflowy_task_overview.py
  ... --status Doing --status "To Do"   statuses to track, in section order
  ... --status-field Status             name of the single-select field
  ... --dry-run                         print instead of writing the page
  ... --dump "Board name"               print a board's fields and first rows
  ... --exclude "Archiv"                skip boards under a sidebar path (repeatable)

Writing the page needs `pip install pycrdt`.
"""
import argparse
import json
import sys
import time

from appflowy_client import AppFlowy, divider, heading, mention, para, replace_body

DEFAULT_STATUSES = ["Doing", "To Do"]
BOARD_LAYOUTS = (2, "Board")
ROW_CHUNK = 100


def walk_folder(tree):
    """Flatten the folder tree in sidebar order: view_id -> {name, path, parent_path, layout, is_space}."""
    pages = {}

    def rec(node, parents):
        for child in node.get("children") or []:
            name = child.get("name") or "(ohne Titel)"
            pages[child["view_id"]] = {"view_id": child["view_id"], "name": name,
                                       "path": " / ".join(parents + [name]),
                                       "parent_path": " / ".join(parents),
                                       "layout": child.get("layout"), "is_space": parents == []}
            rec(child, parents + [name])

    rec(tree, [])
    return pages


def resolve(pages, key):
    hits = [p for p in pages.values() if key in (p["view_id"], p["path"], p["name"])]
    if len(hits) > 1:
        sys.exit(f"{key!r} is ambiguous: " + "; ".join(p["path"] for p in hits))
    return hits[0] if hits else None


def excluded(page, exclude):
    return any(page["view_id"] == e or page["path"] == e or page["path"].startswith(e + " / ") for e in exclude)


def board_databases(af, ws, pages, exclude):
    """(database_id, board page) for each database shown as a board in the sidebar, in sidebar order."""
    order = {vid: i for i, vid in enumerate(pages)}
    found = []
    for db in af.call("GET", f"/api/workspace/{ws}/database"):
        boards = [pages[v["view_id"]] for v in db.get("views", [])
                  if v["view_id"] in pages and pages[v["view_id"]]["layout"] in BOARD_LAYOUTS]
        boards = [b for b in boards if not excluded(b, exclude)]
        if boards:
            found.append((db["id"], min(boards, key=lambda b: order[b["view_id"]])))
    return sorted(found, key=lambda f: order[f[1]["view_id"]])


def fields(af, ws, db_id):
    return af.call("GET", f"/api/workspace/{ws}/database/{db_id}/fields")


def rows(af, ws, db_id):
    ids = [r["id"] for r in af.call("GET", f"/api/workspace/{ws}/database/{db_id}/row")]
    out = []
    for i in range(0, len(ids), ROW_CHUNK):
        out += af.call("GET", f"/api/workspace/{ws}/database/{db_id}/row/detail"
                              f"?ids={','.join(ids[i:i + ROW_CHUNK])}")
    return out


def option_names(field):
    """Select option id -> name; type_option may be keyed by field type and nested as a JSON string."""
    names = {}

    def rec(v):
        if isinstance(v, str) and v[:1] in "{[":
            try:
                v = json.loads(v)
            except ValueError:
                return
        if isinstance(v, dict):
            if "id" in v and "name" in v:
                names[v["id"]] = v["name"]
            for x in v.values():
                rec(x)
        elif isinstance(v, list):
            for x in v:
                rec(x)

    rec(field.get("type_option"))
    return names


def cell_values(value, names):
    """A select cell as a list of option names, whether the server sends names, ids, a list or a comma string."""
    if value is None:
        return []
    items = value if isinstance(value, list) else str(value).split(",")
    out = []
    for it in items:
        if isinstance(it, dict):
            it = it.get("name") or it.get("id") or ""
        it = str(it).strip()
        if it:
            out.append(names.get(it, it))
    return out


def card_title(value):
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    return str(value or "").strip() or "(ohne Titel)"


def collect(af, ws, boards, statuses, status_field):
    """{status: [(board page, [card titles])]} plus boards lacking the status field."""
    wanted = {s.casefold(): s for s in statuses}
    by_status = {s: [] for s in statuses}
    missing = []
    for db_id, board in boards:
        flds = fields(af, ws, db_id)
        sf = next((f for f in flds if f["name"].casefold() == status_field.casefold()), None)
        primary = next((f for f in flds if f.get("is_primary")), None)
        if sf is None or primary is None:
            missing.append(board)
            continue
        names = option_names(sf)
        cards = {s: [] for s in statuses}
        for r in rows(af, ws, db_id):
            for v in cell_values(r["cells"].get(sf["name"]), names):
                if v.casefold() in wanted:
                    cards[wanted[v.casefold()]].append(card_title(r["cells"].get(primary["name"])))
        for s in statuses:
            if cards[s]:
                by_status[s].append((board, cards[s]))
    return by_status, missing


def render_blocks(by_status, n_boards):
    n_cards = sum(len(c) for groups in by_status.values() for _, c in groups)
    blocks = [para(f"Stand {time.strftime('%d.%m.%Y %H:%M')}: {n_cards} Karten "
                   f"({n_boards} Boards durchsucht)."), divider()]
    for status, groups in by_status.items():
        blocks.append(heading(2, f"{status} ({sum(len(c) for _, c in groups)})"))
        if not groups:
            blocks.append(para("Keine Karten."))
        for board, cards in groups:
            runs = [mention(board["view_id"])]
            if board["parent_path"]:
                runs.append(f"  ·  {board['parent_path']}")
            blocks.append(heading(3, *runs))
            blocks.extend({"type": "bulleted_list", "data": {"delta": [{"insert": t}]}} for t in cards)
    return blocks


def print_results(by_status):
    for status, groups in by_status.items():
        print(f"\n== {status} ({sum(len(c) for _, c in groups)})")
        for board, cards in groups:
            print(f"  {board['path']}")
            for t in cards:
                print(f"    - {t}")


def dump(af, ws, pages, key):
    page = resolve(pages, key) or sys.exit(f"no page {key!r}")
    for db in af.call("GET", f"/api/workspace/{ws}/database"):
        if any(v["view_id"] == page["view_id"] for v in db.get("views", [])):
            print(json.dumps({"database_id": db["id"], "views": db["views"], "folder_layout": page["layout"],
                              "fields": fields(af, ws, db["id"]), "rows": rows(af, ws, db["id"])[:5]},
                             ensure_ascii=False, indent=1))
            return
    sys.exit(f"{page['path']!r} is not a database view (folder layout {page['layout']!r})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", help="workspace id (default: the first one)")
    ap.add_argument("--status", action="append", help=f"default: {DEFAULT_STATUSES}")
    ap.add_argument("--status-field", default="Status")
    ap.add_argument("--summary-page", default="Offene Aufgaben")
    ap.add_argument("--exclude", action="append", default=[], help="view_id or sidebar path to skip")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--dump", metavar="BOARD", help="print a board's fields and first rows, then exit")
    args = ap.parse_args()
    statuses = args.status or DEFAULT_STATUSES

    af = AppFlowy()
    ws = args.workspace or af.workspaces()[0]["workspace_id"]
    pages = walk_folder(af.folder(ws))

    if args.dump:
        return dump(af, ws, pages, args.dump)

    boards = board_databases(af, ws, pages, args.exclude)
    by_status, missing = collect(af, ws, boards, statuses, args.status_field)
    for b in missing:
        print(f"  übersprungen (kein Feld {args.status_field!r}): {b['path']}", file=sys.stderr)
    print(f"{len(boards)} Boards durchsucht, {len(missing)} übersprungen", file=sys.stderr)

    if args.dry_run:
        return print_results(by_status)

    summary = resolve(pages, args.summary_page)
    if summary is None:
        space = next(p for p in pages.values() if p["is_space"])
        vid = af.create_page(ws, space["view_id"], args.summary_page)
        print(f"Seite {args.summary_page!r} in {space['name']!r} angelegt", file=sys.stderr)
    else:
        vid = summary["view_id"]
    replace_body(af, ws, vid, render_blocks(by_status, len(boards)))
    print(f"{args.summary_page!r} aktualisiert", file=sys.stderr)


if __name__ == "__main__":
    main()
