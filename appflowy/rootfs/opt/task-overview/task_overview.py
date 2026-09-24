#!/usr/bin/env python3
"""Collect the cards of every board whose status is in a chosen set onto one page.

The page (default "Offene Aufgaben") is found by name anywhere in the sidebar,
created in the first space if missing, and fully rewritten on each run: one
section per status, and within it one heading per board (page mention plus
sidebar path) listing the card titles.

Inside the add-on the task_overview service runs this whenever a board changes.
It also runs standalone against any AppFlowy 0.9.64 server:

  AF_BASE=... AF_EMAIL=... AF_PASSWORD=... python3 task_overview.py
  ... --status Doing --status "To Do"   statuses to track, in section order
  ... --status-field Status             name of the single-select field
  ... --workspace "Name"                workspace name or id (default: the first one)
  ... --dry-run                         print instead of writing the page
  ... --dump "Board name"               print a board's fields and first rows
  ... --exclude "Archiv"                skip boards under a sidebar path (repeatable)

Writing the page needs `pip install pycrdt`.
"""
import argparse
import json
import os
import secrets
import string
import sys
import time
import urllib.error
import urllib.request

DEFAULT_STATUSES = ["Doing", "To Do"]
BOARD_LAYOUTS = (2, "Board")
ROW_CHUNK = 100


def log(msg):
    print(f"[task_overview] {msg}", file=sys.stderr, flush=True)


# ----------------------------------------------------------------------------
# minimal AppFlowy-Cloud 0.9.64 client (subset of tools/appflowy_client.py)
# ----------------------------------------------------------------------------
class AppFlowy:
    def __init__(self):
        self.base = os.environ.get("AF_BASE", "").rstrip("/")
        self.email = os.environ.get("AF_EMAIL")
        self.password = os.environ.get("AF_PASSWORD")
        if not (self.base and self.email and self.password):
            sys.exit("AF_BASE, AF_EMAIL and AF_PASSWORD must be set")
        self.token = None
        self.login()

    def login(self):
        d = self._raw("POST", "/gotrue/token?grant_type=password",
                      {"email": self.email, "password": self.password}, auth=False)
        self.token = d["access_token"]

    def _raw(self, method, path, body=None, auth=True):
        h = {"Accept": "application/json"}
        if auth:
            h["Authorization"] = "Bearer " + self.token
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read() or b"{}")

    def call(self, method, path, body=None):
        last = None
        for attempt in range(4):
            try:
                resp = self._raw(method, path, body)
            except urllib.error.HTTPError as e:
                txt = e.read()[:400]
                if e.code == 401 and attempt < 3:
                    self.login()
                    continue
                if e.code >= 500 and attempt < 3:
                    time.sleep(2 * (attempt + 1))
                    last = f"HTTP {e.code}: {txt!r}"
                    continue
                raise SystemExit(f"{method} {path} -> HTTP {e.code}: {txt!r}")
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if attempt < 3:
                    time.sleep(2 * (attempt + 1))
                    last = str(e)
                    continue
                raise SystemExit(f"{method} {path} -> {e}")
            if "code" in resp and resp["code"] != 0:
                raise SystemExit(f"{method} {path} -> app error {resp['code']}: {resp.get('message')}")
            return resp.get("data") if "data" in resp else resp
        raise SystemExit(f"{method} {path} failed: {last}")

    def workspaces(self):
        return self.call("GET", "/api/workspace")

    def folder(self, ws):
        return self.call("GET", f"/api/workspace/{ws}/folder?depth=10")

    def create_page(self, ws, parent_id, name):
        return self.call("POST", f"/api/workspace/{ws}/page-view",
                         {"parent_view_id": parent_id, "layout": 0, "name": name})["view_id"]

    def page_block_types(self, ws, view_id):
        d = self.call("GET", f"/api/workspace/v1/{ws}/collab/{view_id}/json?collab_type=0")
        doc = d["collab"]["document"]
        blocks, cm = doc["blocks"], doc["meta"]["children_map"]
        return [blocks[k]["ty"] for k in cm.get(blocks[doc["page_id"]]["children"], [])]


def runs_to_delta(runs):
    delta = []
    for r in runs:
        if isinstance(r, str):
            if r:
                delta.append({"insert": r})
        elif "page" in r:
            delta.append({"insert": "$", "attributes": {"mention": {"type": "page", "page_id": r["page"]}}})
    return delta


def para(*runs):
    return {"type": "paragraph", "data": {"delta": runs_to_delta(runs)}}


def heading(level, *runs):
    return {"type": "heading", "data": {"level": level, "delta": runs_to_delta(runs)}}


def divider():
    return {"type": "divider", "data": {}}


def mention(view_id):
    return {"page": view_id}


def _nanoid(n=10):
    alphabet = string.ascii_letters + string.digits + "_-"
    return "".join(secrets.choice(alphabet) for _ in range(n))


def replace_body(af, ws, view_id, blocks, tries=3):
    """Replace the page's whole body with `blocks` as one Yjs update."""
    from pycrdt import Array, Doc, Map, Text
    expect = [b["type"] for b in blocks]
    for attempt in range(tries):
        raw = bytes(af.call("GET", f"/api/workspace/{ws}/page-view/{view_id}")["data"]["encoded_collab"])
        doc = Doc()
        doc.apply_update(raw)
        sv = doc.get_state()
        document = doc.get("data", type=Map)["document"]
        bmap, cmap, tmap = document["blocks"], document["meta"]["children_map"], document["meta"]["text_map"]
        pid = document["page_id"]
        kids = cmap[bmap[pid]["children"]]

        def delete_block(bid):
            b = bmap[bid]
            ch, ext = b.get("children"), b.get("external_id")
            if ch and ch in cmap:
                for c in list(cmap[ch]):
                    delete_block(c)
                del cmap[ch]
            if ext and ext in tmap:
                del tmap[ext]
            del bmap[bid]

        with doc.transaction():
            for bid in list(kids):
                delete_block(bid)
            if len(kids):
                del kids[0:len(kids)]
            for i, block in enumerate(blocks):
                bid, ch, ext = _nanoid(), _nanoid(), _nanoid()
                data = dict(block.get("data", {}))
                delta = data.pop("delta", None)
                bmap[bid] = Map({"id": bid, "ty": block["type"], "parent": pid, "children": ch,
                                 "data": json.dumps(data, ensure_ascii=False),
                                 "external_id": ext if delta is not None else None,
                                 "external_type": "text" if delta is not None else None})
                cmap[ch] = Array([])
                if delta is not None:
                    tmap[ext] = Text()
                    t = tmap[ext]
                    pos = 0
                    for op in delta:
                        s = op["insert"]
                        if op.get("attributes"):
                            t.insert(pos, s, op["attributes"])
                        else:
                            t.insert(pos, s)
                        pos += len(s)
                kids.insert(i, bid)
        update = doc.get_update(sv)
        af.call("POST", f"/api/workspace/v1/{ws}/collab/{view_id}/web-update",
                {"doc_state": list(update), "collab_type": 0})
        time.sleep(0.4)
        if af.page_block_types(ws, view_id) == expect:
            return
        log(f"rewrite mismatch on {view_id}, retry {attempt + 1}")
    raise SystemExit(f"rewrite kept failing for {view_id}")


# ----------------------------------------------------------------------------
# boards -> overview
# ----------------------------------------------------------------------------
def pick_workspace(af, key):
    spaces = af.workspaces()
    if not spaces:
        sys.exit(f"{af.email} has no workspace yet; log in once with AppFlowy Web or the app")
    if not key:
        return spaces[0]
    for w in spaces:
        if key in (w["workspace_id"], w.get("workspace_name")):
            return w
    sys.exit(f"workspace {key!r} not found; available: "
             + ", ".join(repr(w.get("workspace_name")) for w in spaces))


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
    ap.add_argument("--workspace", help="workspace name or id (default: the first one)")
    ap.add_argument("--status", action="append", help=f"default: {DEFAULT_STATUSES}")
    ap.add_argument("--status-field", default="Status")
    ap.add_argument("--summary-page", default="Offene Aufgaben")
    ap.add_argument("--exclude", action="append", default=[], help="view_id or sidebar path to skip")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--dump", metavar="BOARD", help="print a board's fields and first rows, then exit")
    args = ap.parse_args()
    statuses = args.status or DEFAULT_STATUSES

    af = AppFlowy()
    w = pick_workspace(af, args.workspace)
    ws = w["workspace_id"]
    log(f"account {af.email}, workspace {w.get('workspace_name')!r} ({ws})")
    pages = walk_folder(af.folder(ws))

    if args.dump:
        return dump(af, ws, pages, args.dump)

    boards = board_databases(af, ws, pages, args.exclude)
    by_status, missing = collect(af, ws, boards, statuses, args.status_field)
    for b in missing:
        log(f"übersprungen (kein Feld {args.status_field!r}): {b['path']}")
    n_cards = sum(len(c) for groups in by_status.values() for _, c in groups)
    log(f"{n_cards} Karten in {len(boards)} Boards, {len(missing)} übersprungen")

    if args.dry_run:
        return print_results(by_status)

    summary = resolve(pages, args.summary_page)
    if summary is None:
        space = next(p for p in pages.values() if p["is_space"])
        vid = af.create_page(ws, space["view_id"], args.summary_page)
        log(f"Seite {args.summary_page!r} in {space['name']!r} angelegt")
    else:
        vid = summary["view_id"]
    replace_body(af, ws, vid, render_blocks(by_status, len(boards)))
    log(f"{args.summary_page!r} aktualisiert")


if __name__ == "__main__":
    main()
