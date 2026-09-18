#!/usr/bin/env python3
"""Shared helpers for the Anno 1800 -> AppFlowy import scripts.

- AppFlowy: thin client for the AppFlowy-Cloud 0.9.64 REST API of the add-on
- State: manifest of every page the scripts created/reuse (tools/anno1800_data/state.json)
- fetch(): disk-cached downloads (html/ and icons/ under the data directory)
- block builders producing the JSON that /page-view/{id}/append-block accepts,
  including AppFlowy page mentions ("$" run with a mention attribute)
"""
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "anno1800_data"
HTML_DIR = DATA_DIR / "html"
ICON_DIR = DATA_DIR / "icons"
PARSED_DIR = DATA_DIR / "parsed"
STATE_FILE = DATA_DIR / "state.json"
SITE = "https://www.annoinfo.de/"
UA = {"User-Agent": "Mozilla/5.0 (appflowy-import)"}
OFFLINE = False


# ----------------------------------------------------------------------------
# downloads with disk cache
# ----------------------------------------------------------------------------
def cache_path(url):
    u = urllib.parse.urlparse(url)
    path = u.path.replace("//", "/")
    if "/images/anno_1800/" in path:
        return ICON_DIR / path.split("/images/anno_1800/", 1)[1]
    if path.startswith("/"):
        path = path[1:]
    return HTML_DIR / path


def fetch(url):
    """Return the bytes of url, from disk if cached, else download and store."""
    url = urllib.parse.urljoin(SITE, url)
    p = cache_path(url)
    if p.exists():
        return p.read_bytes()
    if OFFLINE:
        raise SystemExit(f"offline: {url} not cached at {p}")
    p.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                data = r.read()
            break
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                raise
            time.sleep(2)
    p.write_bytes(data)
    return data


def fetch_text(url):
    return fetch(url).decode("utf-8", errors="replace")


def fix_mojibake(s):
    """Some detail pages are double-encoded (ProduktionsgebÃ¤ude)."""
    if s and ("Ã" in s or "Â" in s):
        for enc in ("cp1252", "latin-1"):
            try:
                return s.encode(enc).decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
    return s


def norm(name):
    n = unicodedata.normalize("NFKD", (name or "").lower())
    n = "".join(c for c in n if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", n).strip()


# ----------------------------------------------------------------------------
# block builders (SerdeBlock JSON for append-block)
# ----------------------------------------------------------------------------
def runs_to_delta(runs):
    """runs: str | {"text"} | {"text","href"} | {"page": view_id} | list of those."""
    delta = []
    for r in runs:
        if r is None:
            continue
        if isinstance(r, str):
            if r:
                delta.append({"insert": r})
        elif "page" in r:
            delta.append({"insert": "$", "attributes": {"mention": {"type": "page", "page_id": r["page"]}}})
        elif r.get("href"):
            delta.append({"insert": r["text"], "attributes": {"href": r["href"]}})
        elif r.get("text"):
            delta.append({"insert": r["text"]})
    return delta


def para(*runs):
    return {"type": "paragraph", "data": {"delta": runs_to_delta(runs)}}


def bullet(*runs):
    return {"type": "bulleted_list", "data": {"delta": runs_to_delta(runs)}}


def heading(level, *runs):
    return {"type": "heading", "data": {"level": level, "delta": runs_to_delta(runs)}}


def divider():
    return {"type": "divider", "data": {}}


def image(url):
    return {"type": "image", "data": {"url": url, "image_type": 1, "align": "center"}}


def mention(view_id):
    return {"page": view_id}


def join_runs(items, sep=", "):
    """Interleave runs with a separator string."""
    out = []
    for i, it in enumerate(items):
        if i:
            out.append(sep)
        if isinstance(it, list):
            out.extend(it)
        else:
            out.append(it)
    return out


def label_line(label, *runs):
    """'Label: ' + runs, or None when there is nothing to say."""
    flat = [r for r in runs if r]
    if not flat:
        return None
    return para(f"{label}: ", *flat)


def block_types(blocks):
    return [b["type"] for b in blocks]


# ----------------------------------------------------------------------------
# AppFlowy REST client
# ----------------------------------------------------------------------------
class AppFlowy:
    def __init__(self, base=None, email=None, password=None):
        self.base = (base or os.environ.get("AF_BASE", "")).rstrip("/")
        self.email = email or os.environ.get("AF_EMAIL")
        self.password = password or os.environ.get("AF_PASSWORD")
        if not (self.base and self.email and self.password):
            sys.exit("AF_BASE, AF_EMAIL and AF_PASSWORD must be set")
        self.token = None
        self.login()

    def login(self):
        d = self._raw("POST", "/gotrue/token?grant_type=password",
                      {"email": self.email, "password": self.password}, auth=False)
        self.token = d["access_token"]

    def _raw(self, method, path, body=None, auth=True, headers=None, raw_body=None):
        h = {"Accept": "application/json"}
        if auth:
            h["Authorization"] = "Bearer " + self.token
        data = raw_body
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        if headers:
            h.update(headers)
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read() or b"{}")

    def call(self, method, path, body=None, **kw):
        last = None
        for attempt in range(4):
            try:
                resp = self._raw(method, path, body, **kw)
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

    # --- workspace / folder ---
    def workspaces(self):
        return self.call("GET", "/api/workspace")

    def folder(self, ws):
        return self.call("GET", f"/api/workspace/{ws}/folder?depth=10")

    def create_page(self, ws, parent_id, name):
        return self.call("POST", f"/api/workspace/{ws}/page-view",
                         {"parent_view_id": parent_id, "layout": 0, "name": name})["view_id"]

    def rename_page(self, ws, view_id, name):
        self.call("POST", f"/api/workspace/{ws}/page-view/{view_id}/update-name", {"name": name})

    def move_page(self, ws, view_id, new_parent_id, prev_view_id=None):
        self.call("POST", f"/api/workspace/{ws}/page-view/{view_id}/move",
                  {"new_parent_view_id": new_parent_id, "prev_view_id": prev_view_id})

    def trash_page(self, ws, view_id):
        self.call("POST", f"/api/workspace/{ws}/page-view/{view_id}/move-to-trash", {})

    def set_icon_url(self, ws, view_id, url):
        self.call("POST", f"/api/workspace/{ws}/page-view/{view_id}/update-icon",
                  {"icon": {"ty": 1, "value": url}})

    def append_blocks(self, ws, view_id, blocks):
        self.call("POST", f"/api/workspace/{ws}/page-view/{view_id}/append-block", {"blocks": blocks})

    def upload_blob(self, ws, parent_dir, content, content_type="image/webp"):
        d = self.call("PUT", f"/api/file_storage/{ws}/v1/blob/{parent_dir}", raw_body=content,
                      headers={"Content-Type": content_type, "Content-Length": str(len(content))})
        fid = d["file_id"]
        return f"{self.base}/api/file_storage/{ws}/v1/blob/{parent_dir}/{urllib.parse.quote(fid, safe='')}", fid

    def page_json(self, ws, view_id):
        d = self.call("GET", f"/api/workspace/v1/{ws}/collab/{view_id}/json?collab_type=0")
        return d["collab"]["document"]

    def page_block_types(self, ws, view_id):
        doc = self.page_json(ws, view_id)
        blocks, cm = doc["blocks"], doc["meta"]["children_map"]
        return [blocks[k]["ty"] for k in cm.get(blocks[doc["page_id"]]["children"], [])]

    def append_verified(self, ws, view_id, blocks, tries=3):
        """Append in chunks and re-read; the server was seen dropping the first block."""
        if not blocks:
            return
        expect = block_types(blocks)
        for attempt in range(tries):
            self.append_blocks(ws, view_id, blocks)
            time.sleep(0.4)
            types = self.page_block_types(ws, view_id)
            if types[-len(expect):] == expect:
                return
            print(f"    append lost blocks on {view_id} (tail {types[-len(expect):]}), retry {attempt + 1}",
                  flush=True)
        raise SystemExit(f"append kept failing for {view_id}")


# ----------------------------------------------------------------------------
# manifest of created pages
# ----------------------------------------------------------------------------
class State:
    """state.json: {"workspace": ws, "pages": [ {kind,name,parent,view_id,icon_src,icon_url,file_id,blocks} ]}"""

    def __init__(self, path=STATE_FILE):
        self.path = Path(path)
        self.data = {"workspace": None, "pages": []}
        if self.path.exists():
            self.data = json.loads(self.path.read_text())
        self._index()

    def _index(self):
        self.by_id = {p["view_id"]: p for p in self.data["pages"]}
        self.by_kind_name = {}
        self.by_parent_name = {}
        for p in self.data["pages"]:
            self.by_kind_name.setdefault((p["kind"], norm(p["name"])), p)
            self.by_parent_name[(p.get("parent"), norm(p["name"]))] = p

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1))
        tmp.replace(self.path)

    @property
    def workspace(self):
        return self.data["workspace"]

    @workspace.setter
    def workspace(self, ws):
        self.data["workspace"] = ws

    def get(self, kind, name):
        return self.by_kind_name.get((kind, norm(name)))

    def vid(self, kind, name):
        p = self.get(kind, name)
        return p["view_id"] if p else None

    def child(self, parent_id, name):
        return self.by_parent_name.get((parent_id, norm(name)))

    def children(self, parent_id, kind=None):
        return [p for p in self.data["pages"] if p.get("parent") == parent_id and (kind is None or p["kind"] == kind)]

    def record(self, kind, name, parent, view_id, icon_src=None, icon_url=None, file_id=None, blocks=None,
               extra=None):
        p = self.by_id.get(view_id)
        if p is None:
            p = {"kind": kind, "name": name, "parent": parent, "view_id": view_id}
            self.data["pages"].append(p)
        p.update({"kind": kind, "name": name, "parent": parent})
        if icon_src is not None:
            p["icon_src"] = icon_src
        if icon_url is not None:
            p["icon_url"] = icon_url
        if file_id is not None:
            p["file_id"] = file_id
        if blocks is not None:
            p["blocks"] = blocks
        if extra:
            p.update(extra)
        self._index()
        self.save()
        return p

    def remove(self, view_id):
        self.data["pages"] = [p for p in self.data["pages"] if p["view_id"] != view_id]
        self._index()
        self.save()

    def append_blocks(self, view_id, blocks):
        p = self.by_id[view_id]
        p.setdefault("blocks", []).extend(blocks)
        self.save()


# ----------------------------------------------------------------------------
# common page operations
# ----------------------------------------------------------------------------
def upload_icon(af, ws, view_id, icon_url_on_site):
    """Download (cached) the site icon, upload it next to the page, set it as page icon."""
    content = fetch(icon_url_on_site)
    url, fid = af.upload_blob(ws, view_id, content, "image/webp")
    af.set_icon_url(ws, view_id, url)
    return url, fid


def create_page_with_icon(af, state, kind, name, parent_id, icon_src=None, blocks=None, extra=None):
    ws = state.workspace
    vid = af.create_page(ws, parent_id, name)
    url = fid = None
    if icon_src:
        url, fid = upload_icon(af, ws, vid, icon_src)
    state.record(kind, name, parent_id, vid, icon_src, url, fid, [], extra)
    if blocks:
        af.append_verified(ws, vid, blocks)
        state.append_blocks(vid, blocks)
    return vid


def append_section(af, state, view_id, blocks):
    """Append blocks to an existing page and remember them (skips if the same
    blocks were already appended, judged by the last recorded blocks)."""
    p = state.by_id.get(view_id)
    if p is not None and p.get("blocks") and p["blocks"][-len(blocks):] == blocks:
        return False
    af.append_verified(state.workspace, view_id, blocks)
    if p is not None:
        state.append_blocks(view_id, blocks)
    return True


# ----------------------------------------------------------------------------
# in-place document editing (needs `pip install pycrdt`)
# ----------------------------------------------------------------------------
def _nanoid(n=10):
    import secrets
    import string
    alphabet = string.ascii_letters + string.digits + "_-"
    return "".join(secrets.choice(alphabet) for _ in range(n))


def rewrite_children(af, ws, view_id, keep, blocks, tries=3):
    """Replace the page's top-level blocks from index `keep` on with `blocks`,
    as one Yjs update sent to /collab/{id}/web-update. keep=0 replaces the whole
    body; keep=len(children)-n replaces the last n blocks."""
    from pycrdt import Doc, Map, Array, Text
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
            k = max(0, min(keep, len(kids)))
            for bid in list(kids)[k:]:
                delete_block(bid)
            if len(kids) > k:
                del kids[k:len(kids)]
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
                kids.insert(k + i, bid)
        update = doc.get_update(sv)
        af.call("POST", f"/api/workspace/v1/{ws}/collab/{view_id}/web-update",
                {"doc_state": list(update), "collab_type": 0})
        time.sleep(0.4)
        types = af.page_block_types(ws, view_id)
        if types[k:] == block_types(blocks):
            return
        print(f"    rewrite mismatch on {view_id} (got {types[k:][:5]}…), retry {attempt + 1}", flush=True)
    raise SystemExit(f"rewrite kept failing for {view_id}")


def replace_body(af, ws, view_id, blocks):
    rewrite_children(af, ws, view_id, 0, blocks)


def replace_tail(af, ws, view_id, drop_last, blocks):
    n = len(af.page_block_types(ws, view_id))
    rewrite_children(af, ws, view_id, max(0, n - drop_last), blocks)
