#!/usr/bin/env python3
"""Build the Anno 1800 wiki in AppFlowy (space Gaming > page "Anno 1800") from
the parsed annoinfo.de data in tools/anno1800_data/parsed/.

Two phases so that every cross-reference can be resolved:
  create   page skeletons (name + icon) for all kinds, ids recorded in state.json
  fill     append the page bodies (with AppFlowy page mentions "$")
  parents  append child lists to the parent pages (Anno 1800, Waren, Gebäude, …)
  verify   compare the live folder tree with state.json and the parsed data

Sub-commands: sync-state | create | fill | parents | verify | all
Options: --kinds ziv,geb,ketten,items,waren   --only NAME   --limit N
         --relink (create: trash + recreate the existing goods pages)   --offline

Environment: AF_BASE, AF_EMAIL, AF_PASSWORD (see appflowy_client.py)
"""
import argparse
import collections
import json
import re
import sys
import time

import appflowy_client as ac
from appflowy_client import (AppFlowy, State, PARSED_DIR, fetch, norm, para, bullet, heading, divider,
                             image, mention, join_runs, label_line, create_page_with_icon, append_section,
                             replace_body, replace_tail)

SPACE, GAME = "Gaming", "Anno 1800"
ROOT_NAMES = {"Region": "region_root", "Waren": "waren_root", "Zivilisationsstufen": "ziv_root",
              "Gebäude": "geb_root", "Produktionsketten": "ketten_root", "Tiere": "items_root",
              "Artefakte": "items_root", "Pflanzen": "items_root", "Vorlagen": "vorlagen"}
ITEM_KINDS = {"tiere": ("Tiere", "Zoo", "3dicons/gebaeude/icon_zoo.webp"),
              "artefakte": ("Artefakte", "Museum", "3dicons/gebaeude/icon_museum.webp"),
              "pflanzen": ("Pflanzen", "Botanischer Garten", "3dicons/gebaeude/icon_botanic_garden.webp")}
IMG = "https://www.annoinfo.de/images/anno_1800/"
REGION_ALIAS = {"kap trelawney": "Alte Welt", "alte welt / kap trelawney": "Alte Welt"}
CHUNK = 40


def load(name):
    return json.loads((PARSED_DIR / f"{name}.json").read_text())


# ----------------------------------------------------------------------------
# link resolution
# ----------------------------------------------------------------------------
class Links:
    def __init__(self, state, data):
        self.state, self.d = state, data
        self.ware_by_anchor = {}
        self.ware_by_icon = collections.defaultdict(list)
        self.ware_by_name = {}
        for c in data["waren"]:
            for g in c["goods"]:
                self.ware_by_anchor[g["anchor"]] = g["name"]
                self.ware_by_icon[g["icon"].rsplit("/", 1)[-1]].append(g["name"])
                self.ware_by_name[norm(g["name"])] = g["name"]
        self.level_names = [l["name"] for r in data["zivilisation"] for l in r["levels"]]
        self.building_by_id = {b["id"]: b for b in data["gebaeude"]}
        self.buildings = data["gebaeude"]
        # page names must be unique below one category: disambiguate by region / id
        cnt = collections.Counter(b["name"] for b in self.buildings)
        seen = collections.Counter()
        for b in self.buildings:
            if cnt[b["name"]] > 1:
                reg = b["regions"][0] if b["regions"] else b["region_text"]
                page = f"{b['name']} ({reg})" if reg else b["name"]
                seen[page] += 1
                if seen[page] > 1:
                    page = f"{b['name']} ({reg}, {b['id']})"
                b["page_name"] = page
            else:
                b["page_name"] = b["name"]
        self.chains = {c["key"]: c for r in data["ketten"] for c in r["chains"]}
        self.unresolved = collections.Counter()

    # --- generic
    def vid(self, kind, name):
        return self.state.vid(kind, name)

    def by_extra(self, kind, key, value):
        for p in self.state.data["pages"]:
            if p["kind"] == kind and p.get(key) == value:
                return p["view_id"]
        return None

    def ref(self, vid, text, href=None, note=None):
        """mention when the page exists, else plain text (optionally linked)."""
        if vid:
            return mention(vid)
        self.unresolved[text] += 1
        return {"text": text, "href": href} if href else text

    # --- specific
    def region(self, name):
        n = norm(name)
        name = REGION_ALIAS.get(n, name)
        return self.vid("region", name)

    def region_refs(self, names):
        out = []
        for n in names:
            n = n.strip()
            if n:
                out.append(self.ref(self.region(n), n))
        return join_runs(out)

    def level(self, name):
        name = (name or "").strip()
        if not name:
            return None
        v = self.vid("level", name)
        if v:
            return v
        # singular/plural variants (Ingenieur -> Ingenieure, Artista -> Artistas)
        for ln in self.level_names:
            if norm(ln).startswith(norm(name)) or norm(name).startswith(norm(ln)):
                return self.vid("level", ln)
        return None

    def level_ref(self, name):
        return self.ref(self.level(name), name) if name else None

    def ware_name(self, anchor=None, name=None, icon=None):
        if anchor and anchor in self.ware_by_anchor:
            return self.ware_by_anchor[anchor]
        if icon:
            cands = self.ware_by_icon.get(icon.rsplit("/", 1)[-1], [])
            if len(cands) == 1:
                return cands[0]
            if name and cands:
                for c in cands:
                    if norm(c) in norm(name):
                        return c
        if name:
            n = norm(re.sub(r"\((neue|alte) welt\)|\(arktis\)|\(enbesa\)|\(hacienda\)", "", name, flags=re.I)).strip()
            if n in self.ware_by_name:
                return self.ware_by_name[n]
            alias = {"fische": "Fisch", "pemmikan": "Pemmican", "schreibmaschine": "Schreibmaschinen",
                     "ziegelsteine": "Zieglesteine", "fussballe": "Fussbälle"}
            if n in alias:
                return alias[n]
            for k, v in self.ware_by_name.items():
                if k == n or k.rstrip("s") == n.rstrip("s"):
                    return v
        return None

    def ware(self, anchor=None, name=None, icon=None):
        if anchor:
            v = self.by_extra("ware", "anchor", anchor)
            if v:
                return v
        wn = self.ware_name(anchor, name, icon)
        if wn and not anchor:
            for c in self.d["waren"]:
                for g in c["goods"]:
                    if g["name"] == wn:
                        v = self.by_extra("ware", "anchor", g["anchor"])
                        if v:
                            return v
        return self.vid("ware", wn) if wn else None

    def ware_ref(self, anchor=None, name=None, icon=None, href=None):
        wn = self.ware_name(anchor, name, icon)
        return self.ref(self.ware(anchor, name, icon), wn or name or anchor, href)

    def building(self, site_id=None, name=None):
        if site_id is not None:
            v = self.by_extra("building", "site_id", site_id)
            if v:
                return v
        if name:
            v = self.vid("building", name)
            if v:
                return v
            # duplicate names carry a region suffix: take the first site entry with that name
            for b in self.buildings:
                if norm(b["name"]) == norm(name):
                    return self.by_extra("building", "site_id", b["id"])
        return None

    def building_ref(self, site_id=None, name=None, href=None):
        b = self.building_by_id.get(site_id) if site_id else None
        text = b["page_name"] if b else name
        return self.ref(self.building(site_id, name), text, href)

    def chain_ref(self, key, name=None):
        c = self.chains.get(key)
        return self.ref(self.by_extra("chain", "key", key) if c else None, (c or {}).get("name", name or key))

    def geb_cat(self, name):
        return self.vid("geb_cat", name)

    def set_name(self, kind, key):
        for st in self.d[kind]["sets"]:
            if st["key"] == key:
                return st["name"]
        return f"{ITEM_KINDS[kind][0]} ohne Set" if key == "s_0" else key

    def set_ref(self, kind, key):
        return self.ref(self.by_extra("set", "key", f"{kind}:{key}"), self.set_name(kind, key))

    def runs_with_mentions(self, runs):
        """Replace ware / building / level links inside parsed runs by mentions."""
        out = []
        for r in runs:
            if isinstance(r, dict) and r.get("href"):
                href = r["href"]
                m = re.search(r"(waren_[a-z]+)\.html#(\d+)", href)
                if m:
                    out.append(self.ware_ref(anchor=f"{m.group(1)}#{m.group(2)}", name=r["text"], href=href))
                    continue
                m = re.search(r"gebaeude/detail/(\d+)\.html", href)
                if m:
                    out.append(self.building_ref(int(m.group(1)), r["text"], href))
                    continue
                m = re.search(r"zivilisation\.html#(.+)$", href)
                if m:
                    out.append(self.level_ref(r["text"]))
                    continue
                m = re.search(r"(produktionsketten(?:-\d)?)\.html#(\d+)", href)
                if m:
                    out.append(self.chain_ref(f"{m.group(1)}#{m.group(2)}", r["text"]))
                    continue
                out.append(r)
            else:
                out.append(r)
        return out

    # --- "Beeinflusst …" targets -> building ids
    GROUPS = {
        "zoos": lambda b: b["name"] == "Zoo",
        "museen": lambda b: b["name"] == "Museum",
        "botanischen garten": lambda b: b["name"].startswith("Botanischer Garten"),
        "botanische garten": lambda b: b["name"].startswith("Botanischer Garten"),
        "wohnhauser": lambda b: b["kategorie"] == "Wohngebäude",
        "krankenhauser": lambda b: "hospital" in norm(b["name"]) or "krankenhaus" in norm(b["name"]),
        "kontore": lambda b: norm(b["name"]).startswith("kontor"),
        "anlegestellen": lambda b: "anlegestelle" in norm(b["name"]),
        "besucherhafen": lambda b: "touristenhafen" in norm(b["name"]) or "besucherhafen" in norm(b["name"]),
        "rathauser": lambda b: norm(b["name"]).startswith("rathaus"),
        "handelskammern": lambda b: "handelskammer" in norm(b["name"]),
        "gelehrtenhauser": lambda b: "gelehrten" in norm(b["name"]),
        "kulturellen gebaude": lambda b: b["kategorie"] == "Kulturelle Gebäude",
        "kulturelle gebaude": lambda b: b["kategorie"] == "Kulturelle Gebäude",
        "offentlichen gebaude": lambda b: b["kategorie"] == "Öffentliche Gebäude",
        "monumente": lambda b: b["kategorie"] == "Monumente",
        "tierhofe": lambda b: b["art"] == "Tierfarm",
        "steinbruche": lambda b: "steinbruch" in norm(b["name"]),
        "fischereien": lambda b: "fischerei" in norm(b["name"]),
        "jagdhutten": lambda b: "jagdh" in norm(b["name"]),
        "holzfaller": lambda b: norm(b["name"]).startswith("holzf"),
        "einkaufspassagen": lambda b: "einkaufspassage" in norm(b["name"]),
        "restaurants": lambda b: "restaurant" in norm(b["name"]),
        "kinos": lambda b: b["name"] == "Kino",
        "alpakafarmen": lambda b: "alpaka" in norm(b["name"]),
        "rinder": lambda b: "rinder" in norm(b["name"]),
        "nandu": lambda b: "nandu" in norm(b["name"]),
        "hacienda": lambda b: norm(b["name"]).startswith("hacienda"),
    }
    LEVEL_STEMS = ("bauern", "arbeiter", "handwerker", "ingenieur", "investor", "jornalero", "obrero", "artista",
                   "entdecker", "techniker", "hirten", "alteste", "gelehrte", "touristen")

    def affected_buildings(self, target):
        """'Beeinflusst alle Wohnhäuser' -> [building ids]; returns (ids, unresolved terms)."""
        t = re.sub(r"^Beeinflusst\s+", "", target)
        t = re.sub(r"\s+auf der Insel.*$", "", t)
        terms = [x.strip() for x in re.split(r",|\bund\b|&|/", t) if x.strip()]
        ids, bad = [], []
        for term in terms:
            tn = norm(re.sub(r"^alle\s+", "", term))
            hit = False
            for key, fn in self.GROUPS.items():
                if tn.startswith(key):
                    ids += [b["id"] for b in self.buildings if fn(b)]
                    hit = True
                    break
            if hit:
                continue
            exact = [b["id"] for b in self.buildings if norm(b["name"]) == tn]
            if exact:
                ids += exact
                continue
            # "Arbeiter-", "Obrero-Häuser", "Jornalero Häuser": residences of that level
            stem_lvl = re.sub(r"[-\s]*hauser.*$|-$", "", tn).strip()
            if stem_lvl in self.LEVEL_STEMS or any(stem_lvl.startswith(x) for x in self.LEVEL_STEMS):
                res = [b["id"] for b in self.buildings if b["kategorie"] == "Wohngebäude" and norm(b["name"]).startswith(stem_lvl[:6])]
                if res:
                    ids += res
                    continue
            stem = tn.rstrip("sne")
            pref = [b["id"] for b in self.buildings if norm(b["name"]).rstrip("sne").startswith(stem) and len(stem) > 4]
            if pref:
                ids += pref
            else:
                bad.append(term)
        seen, uniq = set(), []
        for i in ids:
            if i not in seen:
                seen.add(i)
                uniq.append(i)
        return uniq, bad


# ----------------------------------------------------------------------------
# body builders
# ----------------------------------------------------------------------------
def prose(blocks, L, level=3):
    out = []
    for b in blocks:
        r = L.runs_with_mentions(b["runs"])
        if b["kind"] == "heading":
            out.append(heading(level, *r))
        elif b["kind"] == "bullet":
            out.append(bullet(*r))
        else:
            out.append(para(*r))
    return out


def count_fmt(txt):
    return re.sub(r"(\d+)\.00x", r"\1x", txt)


def body_level(lv, L):
    b = [para(p) for p in lv["description"]] or [para(lv["name"])]
    b.append(para())
    b.append(label_line("Region", L.ref(L.region(lv["region"]), lv["region"])))
    if lv["dlc"]:
        b.append(label_line("DLC", ", ".join(lv["dlc"])))
    b.append(para("Baukosten Haus:"))
    for bk in lv["baukosten"]:
        b.append(bullet(f"{bk['count']}x " if bk["count"] else "", L.ware_ref(bk["ware"], bk["name"], href=bk["href"])))
    if lv["house"]:
        b.append(label_line("Wohnhaus", lv["house"]))
    for sec in lv["sections"]:
        b += [divider(), heading(2, sec["title"])]
        for grp in sec["groups"]:
            b.append(para(f"{grp['label']} {grp['note']}".strip() + ":"))
            for n in grp["needs"]:
                if n["ware"]:
                    target = L.ware_ref(n["ware"], n["name"], href=n["href"])
                elif n["building_id"]:
                    target = L.building_ref(n["building_id"], n["name"], n["href"])
                else:
                    target = n["name"]
                extra = []
                if n["dlc"]:
                    extra.append("[" + ", ".join(n["dlc"]) + "]")
                if n["condition"]:
                    extra.append(f"({n['condition']})")
                if n["effect"]:
                    eff = n["effect"]
                    eff = re.sub(r"^\+(\d+)\s+(?!Zufriedenheit|Forschung|Attraktiv)(\S.*)$", r"+\1 Einwohner (\2)", eff)
                    extra.append(f"({eff})")
                b.append(bullet(target, " " + " ".join(extra) if extra else ""))
    b += [divider(), para("Quelle: ", {"text": "annoinfo.de", "href": lv["url"]})]
    return [x for x in b if x]


def body_building(bd, L, sets_by_building):
    b = prose(bd["prose"], L) or [para(bd.get("overview_info") or bd["name"])]
    b.append(para())
    regs = bd["regions"] or [x.strip() for x in bd["region_text"].split(",") if x.strip()]
    b.append(label_line("Region", *L.region_refs(regs)))
    b.append(label_line("Zivilisationsstufe", L.level_ref(bd["level"])))
    b.append(label_line("Kategorie", L.ref(L.geb_cat(bd["kategorie"]), bd["kategorie"])))
    b.append(label_line("Art", bd["art"]))
    if bd["workforce"]:
        m = re.match(r"(.*?)\s*(\(.*\))?$", bd["workforce"])
        b.append(label_line("Arbeitskraft", L.level_ref(m.group(1).strip()), " " + (m.group(2) or "")))
    for key in ("Bedingung", "Vorraussetzung", "Voraussetzung"):
        if key in bd["allgemein"]:
            b.append(label_line("Voraussetzung", *L.runs_with_mentions(bd["allgemein"][key])))
    if "Wirkung" in bd["allgemein"]:
        b.append(label_line("Wirkung", *L.runs_with_mentions(bd["allgemein"]["Wirkung"])))
    if bd["dlc"] and bd["dlc"].lower() != "keine":
        b.append(label_line("DLC", bd["dlc"]))
    if bd["baukosten"]:
        b += [divider(), heading(2, "Baukosten")]
        for bk in bd["baukosten"]:
            r = L.runs_with_mentions(bk["runs"])
            r = [count_fmt(x) if isinstance(x, str) else x for x in r]
            b.append(bullet(*r))
    if bd["infos"]:
        b.append(heading(2, "Weitere Informationen"))
        for label, r in bd["infos"]:
            b.append(bullet(f"{label}: ", *L.runs_with_mentions(r)))
    if bd["produktion"]:
        b.append(heading(2, "Produktion"))
        for label, v in bd["produktion"].items():
            r = L.runs_with_mentions(v["runs"])
            b.append(bullet(f"{label}: ", *r))
        if bd["chain"] and "Produktionskette" not in bd["produktion"]:
            b.append(bullet("Produktionskette: ", L.chain_ref(bd["chain"])))
    sets = sets_by_building.get(bd["id"], [])
    if sets:
        b += [divider(), heading(2, "Beeinflusst durch Items")]
        for kind, st, aff in sets:
            b.append(bullet(L.set_ref(kind, st["key"]), f" ({ITEM_KINDS[kind][0]}): " + "; ".join(aff["effects"])))
    b += [divider(), para("Quelle: ", {"text": "annoinfo.de", "href": bd["url"]})]
    return [x for x in b if x]


def body_chain(ch, L, buildings_by_chain, diagram_url):
    b = [para(p) for p in ch["description"]] or [para(ch["name"])]
    b.append(para())
    wn = L.ware_name(name=ch["name"], icon=ch["icon"])
    if wn:
        b.append(label_line("Produkt", L.ware_ref(name=wn)))
    elif L.building(name=ch["name"]):
        b.append(label_line("Gebäude", L.building_ref(name=ch["name"])))
    else:
        b.append(label_line("Produkt", ch["name"]))
    b.append(label_line("Region", *L.region_refs([ch["region"]])))
    b.append(label_line("Zivilisationsstufe", L.level_ref(ch["level"])))
    if ch["voraussetzung"] and ch["voraussetzung"] not in ("—", "-"):
        b.append(label_line("Voraussetzung", ch["voraussetzung"]))
    if ch["baukosten"] or ch["unterhalt"]:
        b.append(heading(2, "Kosten"))
        for x in ch["baukosten"] + ch["unterhalt"]:
            b.append(bullet(x))
    if ch["produktion"]:
        b.append(heading(2, "Produktion"))
        for x in ch["produktion"]:
            b.append(bullet(x))
    blds = buildings_by_chain.get(ch["key"], [])
    if blds:
        b.append(para("Gebäude: ", *join_runs([L.building_ref(i) for i in blds])))
    b += [divider(), heading(2, "Produktionskette")]
    if diagram_url:
        b.append(image(diagram_url))
    b.append(para("Quelle: ", {"text": "annoinfo.de", "href": ch["url"]}))
    return [x for x in b if x]


def body_item(it, kind, set_key, L):
    title, bname, _ = ITEM_KINDS[kind]
    b = [para(it["description"] or it["name"]), para()]
    b.append(label_line("Sammlung", L.ref(L.vid("items_root", title), title)))
    if set_key:
        b.append(label_line("Set", L.set_ref(kind, set_key)))
    else:
        b.append(label_line("Set", "keins"))
    b.append(label_line("Gebäude", L.ref(L.building(name=bname), bname)))
    if it["properties"]:
        b.append(heading(2, "Eigenschaften"))
        b += [bullet(p) for p in it["properties"]]
    if it["expedition"]:
        b.append(heading(2, "Expeditionsbonus"))
        b += [bullet(p) for p in it["expedition"]]
    if it["dlc"]:
        b.append(label_line("DLC", ", ".join(it["dlc"])))
    return [x for x in b if x]


def body_set(st, kind, L, items_vids):
    title, bname, _ = ITEM_KINDS[kind]
    b = [para(p) for p in st["description"]] or [para(st["name"])]
    b.append(para())
    b.append(label_line("Sammlung", L.ref(L.vid("items_root", title), title)))
    b.append(label_line("Gebäude", L.ref(L.building(name=bname), bname)))
    if st["bonis"]:
        b.append(heading(2, "Set-Bonus"))
        b += [bullet(x) for x in st["bonis"]]
    for aff in st["affects"]:
        ids, bad = L.affected_buildings(aff["target"])
        b.append(heading(2, aff["target"]))
        b += [bullet(x) for x in aff["effects"]]
        if ids:
            b.append(para("Gebäude: ", *join_runs([L.building_ref(i) for i in ids])))
        for t in bad:
            L.unresolved["affects:" + t] += 1
    b.append(heading(2, title))
    for it in st["items"]:
        b.append(bullet(L.ref(items_vids.get(it["anchor"]), it["name"])))
    b += [divider(), para("Quelle: ", {"text": "annoinfo.de", "href": st["url"]})]
    return [x for x in b if x]


def body_ware(g, cat, L, needed_by, produced_by, used_by):
    b = [para(g["description"]) if g["description"] else para(g["name"]), para()]
    b.append(label_line("Kategorie", L.ref(L.vid("waren_cat", cat["name"]), cat["name"])))
    for label, runs in g["fields"]:
        if label == "Zivilisationsstufe":
            b.append(label_line(label, L.level_ref(g["level"])))
        elif label == "Region":
            b.append(label_line(label, *L.region_refs(g["regions"])))
        elif label == "Produktionsgebäude":
            b.append(label_line(label, L.building_ref(g["building_id"], runs[0]["text"] if isinstance(runs[0], dict) else str(runs[0]))))
        elif label == "Produktionskette":
            b.append(label_line(label, L.chain_ref(g["chain"])))
        else:
            b.append(label_line(label, *runs))
    nb = needed_by.get(g["anchor"], [])
    if nb:
        b.append(label_line("Benötigt von", *join_runs([L.level_ref(n) for n in nb])))
    pb = produced_by.get(g["anchor"], [])
    if pb:
        b.append(label_line("Hergestellt in", *join_runs([L.building_ref(i) for i in pb])))
    ub = used_by.get(g["anchor"], [])
    if ub:
        b.append(label_line("Verwendet in", *join_runs([L.building_ref(i) for i in ub])))
    b += [divider(), para("Quelle: ", {"text": "annoinfo.de", "href": "https://www.annoinfo.de/Anno_1800/" + g["anchor"].replace("#", ".html#")})]
    return [x for x in b if x]


# ----------------------------------------------------------------------------
# the importer
# ----------------------------------------------------------------------------
class Importer:
    def __init__(self, args):
        self.args = args
        self.state = State()
        self.data = {n: load(n) for n in ("waren", "zivilisation", "gebaeude", "ketten", "tiere", "artefakte", "pflanzen", "intros")}
        self.af = None
        self.L = Links(self.state, self.data)
        self.created = self.filled = self.skipped = 0

    def connect(self):
        if self.af is None:
            self.af = AppFlowy()
        return self.af

    @property
    def ws(self):
        return self.state.workspace

    def wanted(self, kind_flag):
        return not self.args.kinds or kind_flag in self.args.kinds

    def only_ok(self, name):
        return not self.args.only or norm(self.args.only) == norm(name)

    # ------------------------------------------------------------------ sync
    def sync_state(self):
        af = self.connect()
        ws = self.state.workspace
        tree = None
        if not ws:
            for w in af.workspaces():
                t = af.folder(w["workspace_id"])
                if any(norm(c.get("name", "")) == norm(SPACE) for c in t.get("children", [])):
                    ws, tree = w["workspace_id"], t
                    break
            if not ws:
                sys.exit(f"no workspace with a space {SPACE!r}")
            self.state.workspace = ws
        tree = tree or af.folder(ws)
        space = next(c for c in tree["children"] if norm(c["name"]) == norm(SPACE))
        game = next(c for c in space["children"] if norm(c["name"]) == norm(GAME))
        live = {}
        cats = {b["kategorie"] for b in self.data["gebaeude"]}

        def icon_of(n):
            ic = n.get("icon") or {}
            return ic.get("value") if ic.get("ty") == 1 else None

        def rec(kind, n, parent, extra=None):
            live[n["view_id"]] = True
            old = self.state.by_id.get(n["view_id"])
            e = dict(extra or {})
            if old is None:
                e["legacy"] = True
            self.state.record(kind, n["name"], parent, n["view_id"], icon_url=icon_of(n), extra=e)

        rec("root", game, space["view_id"])
        for c in game.get("children", []):
            kind = ROOT_NAMES.get(c["name"], "other")
            rec(kind, c, game["view_id"])
            for cc in c.get("children", []):
                if kind == "region_root":
                    rec("region", cc, c["view_id"])
                elif kind == "waren_root":
                    rec("waren_cat", cc, c["view_id"])
                    for g in cc.get("children", []):
                        if g["name"].startswith("["):
                            rec("vorlage", g, cc["view_id"])
                        else:
                            rec("ware", g, cc["view_id"], self._ware_extra(cc["name"], g["name"]))
                elif kind == "ziv_root":
                    rec("level", cc, c["view_id"])
                elif kind == "geb_root":
                    if cc["name"] in cats:
                        rec("geb_cat", cc, c["view_id"])
                        for g in cc.get("children", []):
                            rec("building", g, cc["view_id"], self._building_extra(g["name"]))
                    else:
                        rec("building", cc, c["view_id"], self._building_extra(cc["name"]))
                elif kind == "ketten_root":
                    rec("ketten_region", cc, c["view_id"])
                    for g in cc.get("children", []):
                        rec("chain", g, cc["view_id"])
                elif kind == "items_root":
                    rec("set", cc, c["view_id"])
                    for g in cc.get("children", []):
                        rec("item", g, cc["view_id"])
                elif kind == "vorlagen":
                    rec("vorlage", cc, c["view_id"])
                else:
                    rec("other", cc, c["view_id"])
        gone = [p for p in self.state.data["pages"] if p["view_id"] not in live and p["kind"] != "space"]
        for p in gone:
            self.state.remove(p["view_id"])
        print(f"sync-state: {len(live)} live pages recorded, {len(gone)} stale records removed")
        print("  by kind:", dict(collections.Counter(p["kind"] for p in self.state.data["pages"])))

    def _ware_extra(self, cat_name, name):
        for c in self.data["waren"]:
            if norm(c["name"]) == norm(cat_name):
                for g in c["goods"]:
                    if norm(g["name"]) == norm(name):
                        return {"anchor": g["anchor"]}
        return {}

    def _building_extra(self, name):
        for b in self.data["gebaeude"]:
            if norm(b["name"]) == norm(name):
                return {"site_id": b["id"]}
        return {}

    # ------------------------------------------------------------------ create
    def create_all(self):
        self.connect()
        if not self.state.workspace:
            self.sync_state()
        root = self.state.get("root", GAME)
        if not root:
            self.sync_state()
            root = self.state.get("root", GAME)
        self.root_id = root["view_id"]
        if self.wanted("geb"):
            self.create_gebaeude()
        if self.wanted("ziv"):
            self.create_zivilisation()
        if self.wanted("ketten"):
            self.create_ketten()
        if self.wanted("items"):
            for kind in ITEM_KINDS:
                self.create_items(kind)
        if self.wanted("waren"):
            self.create_waren()
        print(f"create: created {self.created}, skipped {self.skipped}")

    def ensure(self, kind, name, parent_id, icon_src=None, extra=None):
        """Return the view_id of the page (kind,name) under parent, creating it when missing."""
        p = self.state.child(parent_id, name)
        if p and p["kind"] == kind:
            self.skipped += 1
            if extra:
                self.state.record(kind, name, parent_id, p["view_id"], extra=extra)
            return p["view_id"]
        if self.args.limit is not None and self.created >= self.args.limit:
            return None
        vid = create_page_with_icon(self.af, self.state, kind, name, parent_id, icon_src, extra=extra)
        self.created += 1
        print(f"  created {kind} {name!r} {vid}", flush=True)
        time.sleep(0.15)
        return vid

    def create_gebaeude(self):
        gr = self.state.get("geb_root", "Gebäude")
        if not gr:
            sys.exit("Gebäude page missing")
        cats = []
        for b in self.data["gebaeude"]:
            if b["kategorie"] not in cats:
                cats.append(b["kategorie"])
        cat_ids = {}
        for c in cats:
            icon = next(b["icon"] for b in self.data["gebaeude"] if b["kategorie"] == c)
            cat_ids[c] = self.ensure("geb_cat", c, gr["view_id"], icon)
        for b in self.data["gebaeude"]:
            if not self.only_ok(b["name"]):
                continue
            existing = self.L.by_extra("building", "site_id", b["id"]) or (
                self.state.vid("building", b["name"]) if b["page_name"] == b["name"] else None)
            if existing:
                p = self.state.by_id[existing]
                if p["parent"] != cat_ids[b["kategorie"]] and cat_ids[b["kategorie"]]:
                    self.af.move_page(self.ws, existing, cat_ids[b["kategorie"]])
                    self.state.record("building", p["name"], cat_ids[b["kategorie"]], existing,
                                      extra={"site_id": b["id"]})
                    print(f"  moved {p['name']!r} -> {b['kategorie']!r}")
                elif "site_id" not in p:
                    self.state.record("building", p["name"], p["parent"], existing, extra={"site_id": b["id"]})
                self.skipped += 1
                continue
            if cat_ids[b["kategorie"]]:
                self.ensure("building", b["page_name"], cat_ids[b["kategorie"]], b["icon"], {"site_id": b["id"]})

    def create_zivilisation(self):
        zr = self.state.get("ziv_root", "Zivilisationsstufen")
        if zr and zr.get("legacy"):
            self.af.trash_page(self.ws, zr["view_id"])
            for p in list(self.state.data["pages"]):
                if p.get("parent") == zr["view_id"]:
                    self.state.remove(p["view_id"])
            self.state.remove(zr["view_id"])
            print(f"  trashed legacy Zivilisationsstufen {zr['view_id']}")
            zr = None
        zid = zr["view_id"] if zr else self.ensure("ziv_root", "Zivilisationsstufen", self.root_id,
                                                    IMG + "3dicons/zivilisation/icon_resident_bauern.webp")
        for r in self.data["zivilisation"]:
            for lv in r["levels"]:
                if self.only_ok(lv["name"]):
                    self.ensure("level", lv["name"], zid, lv["icon"], {"region": r["name"]})

    def create_ketten(self):
        kid = self.ensure("ketten_root", "Produktionsketten", self.root_id, IMG + "3dicons/gebaeude/icon_depot.webp")
        for r in self.data["ketten"]:
            reg = self.state.get("region", r["name"])
            icon = (reg or {}).get("icon_src") or IMG + {"Alte Welt": "icons/worlds/icon_session_moderate.webp",
                                                        "Neue Welt": "icons/worlds/icon_session_southamerica.webp",
                                                        "Arktis": "icons/worlds/icon_session_passage.webp",
                                                        "Enbesa": "icons/worlds/icon_session_landoflions.webp"}[r["name"]]
            rid = self.ensure("ketten_region", r["name"], kid, icon, {"key": r["key"]})
            for ch in r["chains"]:
                if self.only_ok(ch["name"]):
                    self.ensure("chain", ch["name"], rid, ch["icon"], {"key": ch["key"]})

    def create_items(self, kind):
        title, bname, icon = ITEM_KINDS[kind]
        d = self.data[kind]
        for items in [st["items"] for st in d["sets"]] + [d["loose"]]:
            cnt = collections.Counter(i["name"] for i in items)
            seen = collections.Counter()
            for i in items:
                if cnt[i["name"]] > 1:
                    seen[i["name"]] += 1
                    i["page_name"] = f"{i['name']} ({seen[i['name']]})"
                else:
                    i["page_name"] = i["name"]
        rid = self.ensure("items_root", title, self.root_id, IMG + icon)
        for st in d["sets"]:
            sid = self.ensure("set", st["name"], rid, st["icon"], {"key": f"{kind}:{st['key']}", "collection": kind})
            for it in st["items"]:
                if self.only_ok(it["name"]) and sid:
                    self.ensure("item", it["page_name"], sid, it["icon"], {"key": f"{kind}:{it['anchor']}", "collection": kind, "set": st["key"]})
        if d["loose"]:
            lname = f"{title} ohne Set"
            lid = self.ensure("set", lname, rid, d["loose"][0]["icon"], {"key": f"{kind}:s_0", "collection": kind, "loose": True})
            for it in d["loose"]:
                if self.only_ok(it["name"]) and lid:
                    self.ensure("item", it["page_name"], lid, it["icon"], {"key": f"{kind}:{it['anchor']}", "collection": kind, "set": None})

    def create_waren(self):
        wr = self.state.get("waren_root", "Waren")
        for c in self.data["waren"]:
            cid = self.ensure("waren_cat", c["name"], wr["view_id"], c["icon"])
            for g in c["goods"]:
                if not self.only_ok(g["name"]):
                    continue
                p = self.state.child(cid, g["name"])
                if p and self.args.relink and p.get("legacy"):
                    self.af.trash_page(self.ws, p["view_id"])
                    self.state.remove(p["view_id"])
                    print(f"  trashed legacy ware {g['name']!r}")
                    p = None
                if p is None and self.args.limit is not None and self.created >= self.args.limit:
                    continue
                self.ensure("ware", g["name"], cid, g["icon"], {"anchor": g["anchor"]})

    # ------------------------------------------------------------------ fill
    def fill_all(self):
        self.connect()
        L = self.L
        # reverse indexes
        sets_by_building = collections.defaultdict(list)
        for kind in ITEM_KINDS:
            for st in self.data[kind]["sets"]:
                for aff in st["affects"]:
                    ids, _ = L.affected_buildings(aff["target"])
                    for i in ids:
                        sets_by_building[i].append((kind, st, aff))
        buildings_by_chain = collections.defaultdict(list)
        produced_by, used_by = collections.defaultdict(list), collections.defaultdict(list)
        for b in self.data["gebaeude"]:
            if b["chain"]:
                buildings_by_chain[b["chain"]].append(b["id"])
            for a in b["outputs"]:
                produced_by[a].append(b["id"])
            for a in b["inputs"]:
                used_by[a].append(b["id"])
        needed_by = collections.defaultdict(list)
        for r in self.data["zivilisation"]:
            for lv in r["levels"]:
                for sec in lv["sections"]:
                    for grp in sec["groups"]:
                        for n in grp["needs"]:
                            if n["ware"] and lv["name"] not in needed_by[n["ware"]]:
                                needed_by[n["ware"]].append(lv["name"])
                for bk in lv["baukosten"]:
                    if bk["ware"] and lv["name"] not in needed_by[bk["ware"]]:
                        needed_by[bk["ware"]].append(lv["name"])

        def fill(page, blocks):
            if page is None or page.get("legacy"):
                self.skipped += 1
                return
            if page.get("filled") and not (self.args.refresh and page.get("blocks") != blocks):
                self.skipped += 1
                return
            if self.args.limit is not None and self.filled >= self.args.limit:
                return
            replace_body(self.af, self.ws, page["view_id"], blocks)
            self.state.record(page["kind"], page["name"], page["parent"], page["view_id"], blocks=blocks,
                              extra={"filled": True})
            self.filled += 1
            print(f"  {'refreshed' if page.get('filled') else 'filled'} {page['kind']} {page['name']!r}", flush=True)
            time.sleep(0.1)

        if self.wanted("geb"):
            for b in self.data["gebaeude"]:
                if not self.only_ok(b["name"]):
                    continue
                vid = L.by_extra("building", "site_id", b["id"])
                page = self.state.by_id.get(vid)
                if page and page.get("legacy"):
                    continue  # hand-written pages stay as they are
                fill(page, body_building(b, L, sets_by_building))
        if self.wanted("ziv"):
            for r in self.data["zivilisation"]:
                for lv in r["levels"]:
                    if self.only_ok(lv["name"]):
                        fill(self.state.get("level", lv["name"]), body_level(lv, L))
        if self.wanted("ketten"):
            for r in self.data["ketten"]:
                for ch in r["chains"]:
                    if not self.only_ok(ch["name"]):
                        continue
                    page = self.state.by_id.get(L.by_extra("chain", "key", ch["key"]))
                    if page is None or (page.get("filled") and not self.args.refresh):
                        self.skipped += 1
                        continue
                    url = page.get("diagram_url")
                    if not url and ch["diagram"]:
                        url, fid = self.af.upload_blob(self.ws, page["view_id"], fetch(ch["diagram"]), "image/webp")
                        self.state.record(page["kind"], page["name"], page["parent"], page["view_id"],
                                          extra={"diagram_url": url, "diagram_src": ch["diagram"]})
                    fill(page, body_chain(ch, L, buildings_by_chain, url))
        if self.wanted("items"):
            for kind in ITEM_KINDS:
                d = self.data[kind]
                item_vids = {}
                for p in self.state.data["pages"]:
                    if p["kind"] == "item" and p.get("collection") == kind:
                        item_vids[p["key"].split(":", 1)[1]] = p["view_id"]
                for st in d["sets"]:
                    page = self.state.by_id.get(L.by_extra("set", "key", f"{kind}:{st['key']}"))
                    if self.only_ok(st["name"]):
                        fill(page, body_set(st, kind, L, item_vids))
                    for it in st["items"]:
                        if self.only_ok(it["name"]):
                            fill(self.state.by_id.get(item_vids.get(it["anchor"])), body_item(it, kind, st["key"], L))
                for it in d["loose"]:
                    if self.only_ok(it["name"]):
                        fill(self.state.by_id.get(item_vids.get(it["anchor"])), body_item(it, kind, None, L))
        if self.wanted("waren"):
            for c in self.data["waren"]:
                for g in c["goods"]:
                    if self.only_ok(g["name"]):
                        page = self.state.by_id.get(L.by_extra("ware", "anchor", g["anchor"])) or self.state.get("ware", g["name"])
                        if page and page.get("legacy"):
                            continue
                        fill(page, body_ware(g, c, L, needed_by, produced_by, used_by))
        print(f"fill: filled {self.filled}, skipped {self.skipped}")
        if L.unresolved:
            print("unresolved references (kept as text):", L.unresolved.most_common(40))

    # ------------------------------------------------------------------ parents
    def parents(self):
        self.connect()
        L = self.L
        st = self.state

        def lst(page, key, blocks):
            if page is None:
                return
            old = page.get("list_blocks") if page.get(key) else None
            if old == blocks:
                return
            if old is not None:
                replace_tail(self.af, self.ws, page["view_id"], len(old), blocks)
            elif page.get("filled") or page.get("legacy") or page["kind"] in ("root", "waren_root", "geb_root", "waren_cat"):
                replace_tail(self.af, self.ws, page["view_id"], 0, blocks)
            else:
                replace_body(self.af, self.ws, page["view_id"], blocks)
            st.record(page["kind"], page["name"], page["parent"], page["view_id"], extra={key: True, "list_blocks": blocks})
            print(f"  {'updated' if old is not None else 'listed'} children on {page['name']!r}", flush=True)

        intros = self.data["intros"]
        # Anno 1800 root
        root = st.get("root", GAME)
        names = ["Region", "Waren", "Zivilisationsstufen", "Gebäude", "Produktionsketten", "Tiere", "Artefakte", "Pflanzen"]
        refs = [st.child(root["view_id"], n) for n in names]
        lst(root, "lists_v1", [divider(), heading(2, "Bereiche")] + [bullet(mention(p["view_id"])) for p in refs if p])
        # Waren
        wr = st.get("waren_root", "Waren")
        blocks = prose(intros.get("waren", []), L) + [divider(), heading(2, "Kategorien")]
        for c in self.data["waren"]:
            p = st.get("waren_cat", c["name"])
            if p:
                blocks.append(bullet(mention(p["view_id"]), f" ({len(c['goods'])} Waren)"))
        lst(wr, "lists_v1", blocks)
        for c in self.data["waren"]:
            p = st.get("waren_cat", c["name"])
            items = [bullet(L.ware_ref(g["anchor"], g["name"])) for g in c["goods"]]
            lst(p, "lists_v1", [heading(2, "Waren")] + items)
        # Zivilisationsstufen
        zr = st.get("ziv_root", "Zivilisationsstufen")
        blocks = prose(intros.get("zivilisation", []), L)
        for r in self.data["zivilisation"]:
            blocks += [divider(), heading(2, r["name"]), para("Region: ", L.ref(L.region(r["name"]), r["name"]))]
            for lv in r["levels"]:
                blocks.append(bullet(L.level_ref(lv["name"]), f"  [{', '.join(lv['dlc'])}]" if lv["dlc"] else ""))
        lst(zr, "lists_v1", blocks)
        # Gebäude
        gr = st.get("geb_root", "Gebäude")
        blocks = prose(intros.get("gebaeude", []), L) + [divider(), heading(2, "Kategorien")]
        cats = []
        for b in self.data["gebaeude"]:
            if b["kategorie"] not in cats:
                cats.append(b["kategorie"])
        for c in cats:
            p = st.get("geb_cat", c)
            n = len([b for b in self.data["gebaeude"] if b["kategorie"] == c])
            if p:
                blocks.append(bullet(mention(p["view_id"]), f" ({n} Gebäude)"))
        lst(gr, "lists_v1", blocks)
        for c in cats:
            p = st.get("geb_cat", c)
            blocks = [heading(2, "Gebäude")]
            for b in self.data["gebaeude"]:
                if b["kategorie"] == c:
                    blocks.append(bullet(L.building_ref(b["id"]), " (" + ", ".join(b["regions"]) + (f"; {b['level']}" if b["level"] else "") + ")"))
            lst(p, "lists_v1", blocks)
        # Produktionsketten
        kr = st.get("ketten_root", "Produktionsketten")
        blocks = prose(intros.get("produktionsketten", []), L) + [divider(), heading(2, "Regionen")]
        for r in self.data["ketten"]:
            p = st.get("ketten_region", r["name"])
            if p:
                blocks.append(bullet(mention(p["view_id"]), f" ({len(r['chains'])} Ketten)"))
        lst(kr, "lists_v1", blocks)
        for r in self.data["ketten"]:
            p = st.get("ketten_region", r["name"])
            blocks = prose(r["intro"], L) + [divider(), para("Region: ", L.ref(L.region(r["name"]), r["name"]))]
            level = None
            for ch in r["chains"]:
                if ch["level"] != level:
                    level = ch["level"]
                    blocks.append(heading(2, level or "Ketten"))
                    if L.level(level):
                        blocks.append(para("Zivilisationsstufe: ", L.level_ref(level)))
                blocks.append(bullet(L.chain_ref(ch["key"])))
            lst(p, "lists_v1", blocks)
        # Items
        for kind, (title, bname, _) in ITEM_KINDS.items():
            d = self.data[kind]
            ir = st.get("items_root", title)
            blocks = prose(d["intro"], L) + [divider(), para("Gebäude: ", L.ref(L.building(name=bname), bname)), heading(2, "Sets")]
            for s in d["sets"]:
                p = st.by_id.get(L.by_extra("set", "key", f"{kind}:{s['key']}"))
                if p:
                    blocks.append(bullet(mention(p["view_id"]), f" ({len(s['items'])})"))
            loose = st.by_id.get(L.by_extra("set", "key", f"{kind}:s_0"))
            if loose:
                blocks += [heading(2, "Ohne Set"), bullet(mention(loose["view_id"]), f" ({len(d['loose'])})")]
            lst(ir, "lists_v1", blocks)
            if loose:
                items = [p for p in st.data["pages"] if p["kind"] == "item" and p.get("parent") == loose["view_id"]]
                blocks = [para(x) for x in d.get("loose_intro", [])] + [heading(2, title)]
                blocks += [bullet(mention(p["view_id"])) for p in items]
                lst(loose, "lists_v1", blocks)
        print("parents done")

    # ------------------------------------------------------------------ recreate
    def recreate(self):
        """Trash the filled, script-made pages named by --only (or --kinds) so that
        `create` + `fill` rebuild them with fully resolvable references."""
        self.connect()
        live = {p["view_id"] for p in self.state.data["pages"]}

        def dangling(p):
            return any(op.get("attributes", {}).get("mention", {}).get("page_id") not in live
                       for b in p.get("blocks", []) for op in b.get("data", {}).get("delta", [])
                       if "mention" in op.get("attributes", {}))
        victims = [p for p in self.state.data["pages"]
                   if p.get("filled") and not p.get("legacy") and self.only_ok(p["name"])
                   and (not self.args.kinds or p["kind"] in self.args.kinds)
                   and (not self.args.dangling or dangling(p))]
        if not self.args.only and not self.args.kinds and not self.args.dangling:
            sys.exit("recreate needs --only NAME, --kinds KIND,… or --dangling")
        for p in victims:
            self.af.trash_page(self.ws, p["view_id"])
            self.state.remove(p["view_id"])
            print(f"  trashed {p['kind']} {p['name']!r} {p['view_id']}", flush=True)
        print(f"recreate: trashed {len(victims)} pages; run create + fill next")

    # ------------------------------------------------------------------ verify
    def verify(self):
        af = self.connect()
        tree = af.folder(self.ws)
        live = {}

        def walk(n, parent=None):
            live[n["view_id"]] = (n["name"], parent, bool(n.get("icon")))
            for c in n.get("children", []):
                walk(c, n["view_id"])
        walk(tree)
        st = self.state
        missing = [p for p in st.data["pages"] if p["view_id"] not in live]
        print("state pages:", len(st.data["pages"]), " missing live:", len(missing), [p["name"] for p in missing][:10])
        counts = collections.Counter(p["kind"] for p in st.data["pages"] if p["view_id"] in live)
        print("live by kind:", dict(counts))
        exp = {"level": 16, "building": 272, "chain": 108, "ware": 192,
               "item": sum(len(s["items"]) for k in ITEM_KINDS for s in self.data[k]["sets"]) + sum(len(self.data[k]["loose"]) for k in ITEM_KINDS)}
        for k, v in exp.items():
            print(f"  {k}: {counts.get(k, 0)} / expected {v}", "OK" if counts.get(k, 0) == v else "MISMATCH")
        # duplicates per parent
        dup = collections.Counter((p["parent"], norm(p["name"])) for p in st.data["pages"] if p["view_id"] in live)
        print("duplicate names under one parent:", [k for k, v in dup.items() if v > 1][:10])
        # dangling mentions
        dangling = collections.Counter()
        for p in st.data["pages"]:
            for b in p.get("blocks", []):
                for op in b.get("data", {}).get("delta", []):
                    m = op.get("attributes", {}).get("mention")
                    if m and m.get("page_id") not in live:
                        dangling[p["name"]] += 1
        print("pages with dangling mentions:", dangling.most_common(10) or "none")
        unfilled = [p["name"] for p in st.data["pages"] if p["kind"] in ("level", "building", "chain", "ware", "item", "set")
                    and not p.get("filled") and not p.get("legacy") and not p.get("loose")]
        print("unfilled pages:", len(unfilled), unfilled[:10])
        noicon = [p["name"] for p in st.data["pages"] if p["view_id"] in live and not live[p["view_id"]][2] and p["kind"] not in ("root", "region_root", "waren_root", "vorlagen", "vorlage", "other", "region")]
        print("pages without icon:", len(noicon), noicon[:10])
        # spot-check block sequences
        import random
        random.seed(7)
        sample = [p for p in st.data["pages"] if p.get("filled") and p["view_id"] in live]
        for p in random.sample(sample, min(6, len(sample))):
            types = af.page_block_types(self.ws, p["view_id"])
            exp_types = [b["type"] for b in p.get("blocks", [])]
            ok = types[-len(exp_types):] == exp_types if exp_types else True
            print(f"  {p['kind']} {p['name']!r}: {'OK' if ok else 'BLOCKS DIFFER'} ({len(types)} blocks)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["sync-state", "create", "fill", "parents", "recreate", "verify", "all"])
    ap.add_argument("--kinds", help="comma list of ziv,geb,ketten,items,waren")
    ap.add_argument("--only")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--relink", action="store_true")
    ap.add_argument("--dangling", action="store_true", help="recreate: only pages with mentions to trashed pages")
    ap.add_argument("--refresh", action="store_true", help="fill: rewrite pages whose regenerated body differs")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    args.kinds = args.kinds.split(",") if args.kinds else None
    ac.OFFLINE = args.offline
    imp = Importer(args)
    if args.command == "sync-state":
        imp.sync_state()
    elif args.command == "create":
        imp.create_all()
    elif args.command == "fill":
        imp.fill_all()
    elif args.command == "parents":
        imp.parents()
    elif args.command == "recreate":
        imp.recreate()
    elif args.command == "verify":
        imp.verify()
    elif args.command == "all":
        imp.sync_state()
        imp.create_all()
        imp.fill_all()
        imp.parents()
        imp.verify()


if __name__ == "__main__":
    main()
