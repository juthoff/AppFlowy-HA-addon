#!/usr/bin/env python3
"""Parse the annoinfo.de Anno 1800 pages into tools/anno1800_data/parsed/*.json.

Pure function of the cached HTML (downloads on a cache miss unless --offline).
  waren.json         7 categories, 192 goods
  zivilisation.json  4 regions, 16 levels
  gebaeude.json      272 buildings (overview + detail pages)
  ketten.json        4 regions, 108 production chains
  tiere.json / artefakte.json / pflanzen.json   item sets + items
"""
import argparse
import html
import json
import re
import sys

import appflowy_client as ac
from appflowy_client import fetch_text, fix_mojibake, norm, PARSED_DIR

A18 = "https://www.annoinfo.de/Anno_1800/"

REGION_NAMES = {"Alte Welt / Kap Trelawney": "Alte Welt", "Alte Welt": "Alte Welt", "Neue Welt": "Neue Welt",
                "Arktis": "Arktis", "Enbesa": "Enbesa", "Kap Trelawney": "Alte Welt"}
REQUIREMENT_ICONS = {"icon_electricity": "Elektrizität", "icon_heating": "Heizung", "icon_water_drop": "Wasser"}


# ----------------------------------------------------------------------------
# small html helpers
# ----------------------------------------------------------------------------
def clean(fragment):
    t = re.sub(r"<script.*?</script>", "", fragment, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = fix_mojibake(t)
    return re.sub(r"\s+", " ", t).strip()


def img_alts(fragment):
    return [fix_mojibake(html.unescape(a)) for a in re.findall(r'<img[^>]*alt="([^"]*)"', fragment)]


def first_img_src(fragment):
    m = re.search(r'<img[^>]*src="([^"]+)"', fragment)
    return m.group(1).replace("../../", "https://www.annoinfo.de/").replace(".de//", ".de/") if m else None


def runs(fragment, keep_img_alt=False):
    """Fragment -> list of runs (plain text and {'text','href'} links), images dropped
    (or replaced by their alt text)."""
    frag = re.sub(r"<script.*?</script>", "", fragment, flags=re.S)
    frag = re.sub(r"<sup>.*?</sup>", " ", frag, flags=re.S)
    if keep_img_alt:
        frag = re.sub(r'<img[^>]*alt="([^"]*)"[^>]*>', r" \1 ", frag)
    else:
        frag = re.sub(r"<img[^>]*>", " ", frag)
    out = []
    pos = 0
    for a in re.finditer(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', frag, re.S):
        before = clean(frag[pos:a.start()])
        if before:
            out.append(before + " ")
        text = clean(a.group(2))
        href = a.group(1)
        if href.startswith("/"):
            href = "https://www.annoinfo.de" + href
        if text:
            out.append({"text": text, "href": href})
        pos = a.end()
    tail = clean(frag[pos:])
    if tail:
        if out and isinstance(out[-1], dict):
            tail = " " + tail
        out.append(tail)
    # tidy: merge adjacent strings, normalise spaces around links
    merged = []
    for r in out:
        if merged and isinstance(r, str) and isinstance(merged[-1], str):
            merged[-1] += r
        else:
            merged.append(r)
    res = []
    for i, r in enumerate(merged):
        if isinstance(r, str):
            r = re.sub(r"\s+", " ", r)
            r = re.sub(r"\s+([,.;:)])", r"\1", r)
            if i == 0:
                r = r.lstrip()
            if i == len(merged) - 1:
                r = r.rstrip()
            if r:
                res.append(r)
        else:
            res.append(r)
    return res


def runs_text(rs):
    return "".join(r if isinstance(r, str) else r["text"] for r in rs).strip()


def detail_id(href):
    m = re.search(r"gebaeude/detail/(\d+)\.html", href or "")
    return int(m.group(1)) if m else None


def chain_key(href):
    m = re.search(r"(produktionsketten(?:-\d)?)\.html#(\d+)", href or "")
    return f"{m.group(1)}#{m.group(2)}" if m else None


def ware_anchor(href):
    m = re.search(r"(waren_[a-z]+)\.html#(\d+)", href or "")
    return f"{m.group(1)}#{m.group(2)}" if m else None


def dlc_names(fragment):
    return [fix_mojibake(html.unescape(a)) for a in re.findall(r'dlc_icons/[^"]+"[^>]*alt="([^"]*)"', fragment)]


def prose_blocks(fragment):
    """Prose of a text column -> list of {"kind","runs"}; tolerant of nested/unclosed tags."""
    frag = re.sub(r"<script.*?</script>", "", fragment, flags=re.S)
    frag = re.sub(r"<!--.*?-->", "", frag, flags=re.S)
    out = []
    kind = "para"
    pos = 0
    for m in re.finditer(r"<(/?)(p|h3|h4|h5|li|ul|ol|div|br|table|tr)\b[^>]*>", frag, re.I):
        seg = frag[pos:m.start()]
        r = runs(seg)
        if r:
            out.append({"kind": kind, "runs": r})
        closing, tag = m.group(1) == "/", m.group(2).lower()
        if not closing and tag in ("h3", "h4", "h5"):
            kind = "heading"
        elif not closing and tag == "li":
            kind = "bullet"
        elif not closing and tag in ("p", "div", "br", "ul", "ol", "table", "tr"):
            kind = "para"
        elif closing:
            kind = "para"
        pos = m.end()
    r = runs(frag[pos:])
    if r:
        out.append({"kind": kind, "runs": r})
    return out


def page_intro(page_html):
    """Prose of the page header (between the 'Annoinfo.de - …' h2 and the meta list)."""
    m = re.search(r"<h2>Annoinfo\.de[^<]*</h2>(.*?)<ul class=\"meta\">", page_html, re.S)
    if not m:
        return []
    return [b for b in prose_blocks(m.group(1)) if not re.match(r"^\d\d\.\d\d\.\d{4}", runs_text(b["runs"]))]


def li_items(fragment):
    return re.findall(r"<li[^>]*>(.*?)</li>", fragment, re.S)


# ----------------------------------------------------------------------------
# Waren
# ----------------------------------------------------------------------------
WAREN_PAGES = ["waren_rohstoffe", "waren_konsumgueter", "waren_baumaterialien", "waren_agrarprodukte",
               "waren_zwischenprodukte", "waren_ressoursen", "waren_post"]
CATEGORY_RENAME = {"Strategische Ressoursen": "Strategische Ressourcen"}


def parse_ware_li(li):
    m = re.match(r"\s*<(strong|b)>(?:<u>)?(.*?):(?:</u>)?</(?:strong|b)>(.*)$", li, re.S)
    if not m:
        return None
    label, body = clean(m.group(2)), m.group(3)
    if label in ("Erfordert", "Optional"):
        names = [REQUIREMENT_ICONS.get(i, i) for i in re.findall(r"icons/misc/([a-z_]+?)(?:_\d+)?\.webp", body)]
        rest = clean(body)
        if rest:
            names.append(rest)
        return label, [", ".join(names)]
    return label, runs(body)


def parse_waren():
    cats = []
    for page in WAREN_PAGES:
        s = fetch_text(A18 + page + ".html")
        cat = re.search(r'<img width="48" height="48" src="([^"]+/waren/cat/[^"]+)" alt="([^"]*)"', s)
        name = html.unescape(cat.group(2))
        c = {"key": page, "name": CATEGORY_RENAME.get(name, name), "icon": cat.group(1), "goods": []}
        parts = re.split(r'<h3 class="major" id="(\d+)">', s)
        for i in range(1, len(parts), 2):
            anchor, body = parts[i], parts[i + 1]
            head = re.search(r'<img[^>]*src="([^"]+)"[^>]*alt="([^"]*)"[^>]*>\s*([^<]*)</span>', body)
            if not head or "/waren/" not in head.group(1):
                continue
            gname = clean(head.group(3)) or html.unescape(head.group(2))
            after = body.split("</h3>", 1)[1]
            desc_html, _, rest = after.partition("<ul>")
            fields = []
            for li in li_items(rest.split("</ul>", 1)[0]):
                p = parse_ware_li(li)
                if p:
                    fields.append(p)
            fd = dict(fields)
            g = {"anchor": f"{page}#{anchor}", "name": gname, "icon": head.group(1), "description": clean(desc_html),
                 "fields": fields,
                 "level": runs_text(fd.get("Zivilisationsstufe", [])),
                 "regions": [x.strip() for x in runs_text(fd.get("Region", [])).split(",") if x.strip()],
                 "building_id": next((detail_id(r["href"]) for r in fd.get("Produktionsgebäude", []) if isinstance(r, dict)), None),
                 "chain": next((chain_key(r["href"]) for r in fd.get("Produktionskette", []) if isinstance(r, dict)), None)}
            c["goods"].append(g)
        cats.append(c)
    return cats


# ----------------------------------------------------------------------------
# Zivilisationsstufen
# ----------------------------------------------------------------------------
def parse_need_li(li):
    """<li> of a need list -> dict."""
    frag = re.sub(r"<sup>\s*</sup>", "", li)
    dlc = dlc_names(frag)
    frag_nodlc = re.sub(r'<a[^>]*href="[^"]*dlc\.html[^"]*"[^>]*>.*?</a>', " ", frag, flags=re.S)
    small = re.search(r"<small>(.*?)</small>", frag_nodlc, re.S)
    small_txt = ""
    if small:
        small_txt = html.unescape(re.sub(r'<img[^>]*alt="([^"]*)"[^>]*>', r" \1 ", small.group(1)))
        small_txt = clean(small_txt)
        frag_nodlc = frag_nodlc[:small.start()] + frag_nodlc[small.end():]
    a = re.search(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', frag_nodlc, re.S)
    name = clean(a.group(2)) if a else clean(frag_nodlc)
    href = a.group(1) if a else None
    paren = re.findall(r"\(([^()]*)\)", small_txt)
    effect = next((p.strip() for p in paren if p.strip().startswith("+")), None)
    condition = [p.strip() for p in paren if not p.strip().startswith("+")]
    return {"name": name, "href": href, "building_id": detail_id(href), "ware": ware_anchor(href),
            "dlc": dlc, "condition": ", ".join(condition), "effect": effect}


def parse_zivilisation():
    s = fetch_text(A18 + "zivilisation.html")
    art = s[s.find("<article"):s.find("<aside")]
    # overview: level -> DLC
    ov_start = art.find(">Übersicht<")
    ov_end = art.find("<h2", ov_start + 20)
    overview = art[ov_start:ov_end]
    dlc_by_level = {}
    for li in li_items(overview):
        m = re.search(r'<a href="#([^"]+)"', li)
        if m:
            dlc_by_level[html.unescape(m.group(1))] = dlc_names(li)
    parts = re.split(r"(?=<h2)", art)
    region, order = None, []
    regions = {}
    for p in parts:
        head_html = p.split("</h2>")[0]
        head = clean(head_html)
        if head in REGION_NAMES and "worlds/" in head_html:
            region = REGION_NAMES[head]
            regions.setdefault(region, {"name": region, "icon": first_img_src(head_html), "levels": []})
            order.append(region) if region not in order else None
            continue
        if region is None or "3dicons/zivilisation/icon_resident" not in head_html:
            continue
        name = head
        icon = first_img_src(head_html)
        body = p.split("</h2>", 1)[1]
        cut = body.find('<h3 class="major" id="Stadtstatus"')
        if cut < 0:
            cut = body.find(">Stadtstatus<")
        if cut > 0:
            body = body[:cut]
        # description: text before the portrait figure
        desc_html = body.split("<figure", 1)[0]
        desc_html = re.sub(r"<!--.*?-->", "", desc_html, flags=re.S)
        paras = [clean(x) for x in re.split(r"<br\s*/?>|</p>|</div>", desc_html)]
        paras = [x for x in paras if x]
        # Baukosten Haus
        bk = re.search(r"<strong>Baukosten Haus</strong>\s*<ul[^>]*>(.*?)</ul>", body, re.S)
        baukosten = []
        if bk:
            for li in li_items(bk.group(1)):
                r = runs(li)
                cnt = re.search(r"([\d.,]+)x", runs_text(r))
                a = next((x for x in r if isinstance(x, dict)), None)
                baukosten.append({"count": cnt.group(1).replace(".00", "") if cnt else "",
                                  "name": a["text"] if a else runs_text(r), "href": a["href"] if a else None,
                                  "ware": ware_anchor(a["href"]) if a else None})
        # sections Grundbedürfnisse / Lebensqualität
        sections = []
        secs = re.split(r"<h4[^>]*>", body)
        for sec in secs[1:]:
            title = clean(sec.split("</h4>")[0])
            rest = sec.split("</h4>", 1)[1]
            rest = rest.split("<figure", 1)[0]
            labels = []
            for m in re.finditer(r"<strong>(.*?)</strong>\s*(?:<small>(.*?)</small>)?\s*<ul[^>]*>(.*?)</ul>", rest, re.S):
                label = clean(m.group(1))
                sub = clean(m.group(2) or "")
                needs = [parse_need_li(li) for li in li_items(m.group(3))]
                labels.append({"label": label, "note": sub, "needs": needs})
            if labels:
                sections.append({"title": title, "groups": labels})
        house = re.search(r"<figure>.*?haeuser/.*?</figure>\s*(.*?)(?:</div>|$)", body, re.S)
        house_txt = clean(house.group(1)) if house else ""
        regions[region]["levels"].append({
            "name": name, "region": region, "icon": icon, "dlc": dlc_by_level.get(name, []),
            "description": paras, "baukosten": baukosten, "sections": sections, "house": house_txt,
            "url": A18 + "zivilisation.html#" + name})
    return [regions[r] for r in order]


# ----------------------------------------------------------------------------
# Gebäude
# ----------------------------------------------------------------------------
def parse_gebaeude():
    s = fetch_text(A18 + "gebaeude.html")
    art = s[s.find("<article"):s.find("<aside")]
    buildings = {}
    order = []
    region = level = None
    for chunk in re.split(r"(?=<h2)", art):
        head_html = chunk.split("</h2>")[0]
        head = clean(head_html)
        if "worlds/" in head_html and head.split("/")[0].strip() in REGION_NAMES:
            region = REGION_NAMES[head.split("/")[0].strip()]
        elif "3dicons/zivilisation/icon_resident" in head_html:
            level = head
        for tr in re.findall(r"<tr>(.*?)</tr>", chunk, re.S):
            m = re.search(r'gebaeude/detail/(\d+)\.html"[^>]*>(.*?)</a>', tr, re.S)
            if not m:
                continue
            bid = int(m.group(1))
            tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
            info = clean(tds[2]) if len(tds) > 2 else ""
            entry = buildings.setdefault(bid, {"id": bid, "name": clean(m.group(2)), "icon": first_img_src(tds[0]),
                                               "overview_info": info, "regions": [], "levels": []})
            if region and region not in entry["regions"]:
                entry["regions"].append(region)
            if level and level not in entry["levels"]:
                entry["levels"].append(level)
            if bid not in order:
                order.append(bid)
    for bid in order:
        parse_building_detail(buildings[bid])
    return [buildings[b] for b in order]


def parse_building_detail(b):
    s = fetch_text(A18 + f"gebaeude/detail/{b['id']}.html")
    art = s[s.find("<article"):s.find("<aside")]
    b["url"] = A18 + f"gebaeude/detail/{b['id']}.html"
    h2 = re.search(r"<h2[^>]*>(.*?)</h2>", art, re.S)
    if h2:
        name = clean(h2.group(1))
        if name:
            b["name"] = name
        icon = first_img_src(h2.group(1))
        if icon:
            b["icon"] = icon
    pic = re.search(r'class="fullscreen fit"\s+src="([^"]+)"', art)
    b["image"] = pic.group(1) if pic else None
    left = art.split('<div class="allgemein">')[0]
    left = left.split("<!-- HTML - Beschreibung ausgeben -->")[-1]
    b["prose"] = prose_blocks(left)
    # labelled sections
    def section(cls):
        i = art.find('<div class="%s">' % cls)
        if i < 0:
            return ""
        j = art.find(" End -->", i)
        return art[i:j if j > 0 else i + 20000]
    fields = {}
    for li in li_items(section("allgemein")):
        m = re.match(r"\s*<(?:strong|b)>(.*?):?</(?:strong|b)>(.*)$", li, re.S)
        if m:
            fields[clean(m.group(1)).rstrip(":")] = runs(m.group(2))
    b["allgemein"] = fields
    b["region_text"] = runs_text(fields.get("Region", []))
    lvl = fields.get("Zivilisationsstufe", [])
    b["level"] = runs_text(lvl)
    b["workforce"] = runs_text(fields.get("Arbeitskraft", []))
    b["kategorie"] = runs_text(fields.get("Kategorie", [])) or "Sonstige Gebäude"
    b["art"] = runs_text(fields.get("Art", []))
    b["dlc"] = runs_text(fields.get("Benötigte(s) DLC(s)", []))
    b["baukosten"] = []
    for li in li_items(section("baukosten")):
        r = runs(li)
        a = next((x for x in r if isinstance(x, dict)), None)
        b["baukosten"].append({"runs": r, "ware": ware_anchor(a["href"]) if a else None})
    b["infos"] = []
    for li in li_items(section("infos")):
        m = re.match(r"\s*<(?:strong|b)>(.*?):?</(?:strong|b)>(.*)$", li, re.S)
        if m:
            b["infos"].append([clean(m.group(1)).rstrip(":"), runs(m.group(2))])
    prod = {}
    for li in li_items(section("produktion")):
        m = re.match(r"\s*<(?:strong|b)>(.*?):?</(?:strong|b)>(.*)$", li, re.S)
        if m:
            label = clean(m.group(1)).rstrip(":")
            r = runs(m.group(2))
            prod[label] = {"runs": r, "wares": [ware_anchor(x["href"]) for x in r if isinstance(x, dict) and ware_anchor(x["href"])],
                           "chain": next((chain_key(x["href"]) for x in r if isinstance(x, dict) and chain_key(x["href"])), None)}
    b["produktion"] = prod
    b["chain"] = next((v["chain"] for v in prod.values() if v["chain"]), None)
    b["inputs"] = prod.get("Eingangsprodukt/e", {}).get("wares", [])
    b["outputs"] = prod.get("Ausgangsprodukt/e", {}).get("wares", [])


# ----------------------------------------------------------------------------
# Produktionsketten
# ----------------------------------------------------------------------------
KETTEN_PAGES = [("produktionsketten", "Alte Welt"), ("produktionsketten-2", "Neue Welt"),
                ("produktionsketten-3", "Arktis"), ("produktionsketten-4", "Enbesa")]


def parse_ketten():
    out = []
    for page, region in KETTEN_PAGES:
        s = fetch_text(A18 + page + ".html")
        art = s[s.find("<article"):s.find("<aside")]
        reg = {"key": page, "name": region, "url": A18 + page + ".html", "chains": [],
               "intro": page_intro(s)}
        level = None
        for chunk in re.split(r"(?=<h2 |<h3 )", art):
            if chunk.startswith("<h2"):
                hh = chunk.split("</h2>")[0]
                if "3dicons/zivilisation/icon_resident" in hh:
                    level = clean(hh)
                continue
            m = re.match(r'<h3 class="major" id="(\d+)"[^>]*>(.*?)</h3>(.*)', chunk, re.S)
            if not m:
                continue
            anchor, head, body = m.group(1), m.group(2), m.group(3)
            body = body.split("<h2", 1)[0]
            name = clean(head)
            icon = first_img_src(head)
            desc = [clean(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", body.split('<ul class="prodketten_top">')[0], re.S)]
            top = {}
            topm = re.search(r'<ul class="prodketten_top">(.*?)</ul>', body, re.S)
            if topm:
                for li in li_items(topm.group(1)):
                    mm = re.match(r"\s*<strong>(?:<u>)?(.*?):?(?:</u>)?</strong>(.*)$", li, re.S)
                    if mm:
                        top[clean(mm.group(1)).rstrip(":")] = clean(re.sub(r'<img[^>]*alt="([^"]*)"[^>]*>', "", mm.group(2)))
            lists = {}
            for mm in re.finditer(r"<strong>(.*?):</strong>\s*<ul class=\"prodketten\">(.*?)</ul>", body, re.S):
                items = [clean(re.sub(r'<img[^>]*alt="([^"]*)"[^>]*>', r" \1: ", li)) for li in li_items(mm.group(2))]
                lists[clean(mm.group(1))] = items
            fig = re.search(r'<figure>\s*<img[^>]*src="([^"]+)"', body)
            reg["chains"].append({"key": f"{page}#{anchor}", "name": name, "icon": icon, "region": region,
                                  "level": level, "description": [d for d in desc if d],
                                  "voraussetzung": top.get("Voraussetzung", ""), "region_text": top.get("Region", ""),
                                  "baukosten": lists.get("Baukosten", []), "unterhalt": lists.get("Unterhalt", []),
                                  "produktion": lists.get("Produktion", []),
                                  "diagram": fig.group(1).split("?")[0] if fig else None,
                                  "url": A18 + page + ".html#" + anchor})
        out.append(reg)
    return out


# ----------------------------------------------------------------------------
# Tiere / Artefakte / Pflanzen
# ----------------------------------------------------------------------------
ITEM_PAGES = {"tiere": ("Tiere", "Tiere"), "artefakte": ("Artefakte", "Artefakte"), "pflanzen": ("Pflanzen", "Pflanzen")}


def parse_item_block(pm, body):
    """<p id=N><strong>Name</strong> - text</p> followed by the columns up to the next <hr>."""
    anchor = pm.group(1)
    name = clean(pm.group(2))
    desc = clean(pm.group(3))
    desc = re.sub(r"^\s*-\s*", "", desc)
    icon = first_img_src(body)
    props, bonus, dlc = [], [], []
    e = re.search(r"<strong>Eigenschaften:</strong>\s*<ul[^>]*>(.*?)</ul>", body, re.S)
    if e:
        for li in li_items(e.group(1)):
            if "dlc_icons" in li:
                dlc += dlc_names(li)
                continue
            props.append(clean(re.sub(r'<img[^>]*alt="([^"]*)"[^>]*>', r" \1: ", li)))
    x = re.search(r"<strong>Expeditionsbonus:</strong>\s*<ul[^>]*>(.*?)</ul>", body, re.S)
    if x:
        for li in li_items(x.group(1)):
            bonus.append(clean(re.sub(r'<img[^>]*alt="([^"]*)"[^>]*>', "", li)))
    return {"anchor": anchor, "name": name, "description": desc, "icon": icon, "properties": props,
            "expedition": bonus, "dlc": dlc}


def parse_items(kind):
    title, _ = ITEM_PAGES[kind]
    s = fetch_text(A18 + kind + ".html")
    art = s[s.find("<article"):s.find("<aside")]
    art = art.split("<h4>Kommentarbereich")[0]
    intro_blocks = page_intro(s)
    res = {"kind": kind, "name": title, "url": A18 + kind + ".html", "intro": intro_blocks, "sets": [], "loose": []}
    item_re = re.compile(r'<p id="(\d+)"><strong>(.*?)</strong>(.*?)</p>(.*?)(?=<hr>|<h3|<h2|$)', re.S)
    # sets (h3 id=s_N); the "ohne Set" group follows as <h2 id="s_0">
    sets_part = re.split(r"<h2[^>]*>\s*<span>\s*%s in Sets\s*</span>\s*</h2>" % title, art, maxsplit=1)
    loose_parts = re.split(r'<h2[^>]*id="s_0"[^>]*>.*?</h2>', art, maxsplit=1, flags=re.S)
    if len(sets_part) == 2:
        sets_html = re.split(r'<h2[^>]*id="s_0"', sets_part[1])[0]
        for chunk in re.split(r'(?=<h3 class="major" id="s_)', sets_html)[1:]:
            hm = re.match(r'<h3 class="major" id="(s_\d+)"><span>(.*?)</span></h3>(.*)', chunk, re.S)
            sid, head, body = hm.group(1), hm.group(2), hm.group(3)
            name = clean(head)
            desc = [clean(p) for p in re.findall(r"<p>(.*?)</p>", body.split("<h3", 1)[0], re.S)]
            bonis = []
            bm = re.search(r"<strong>Bonis:</strong>\s*<ul[^>]*>(.*?)</ul>", body, re.S)
            if bm:
                bonis = [clean(li) for li in li_items(bm.group(1))]
            affects = []
            for am in re.finditer(r"<strong>(Beeinflusst[^<]*?):?</strong>\s*<ul[^>]*>(.*?)</ul>", body, re.S):
                affects.append({"target": clean(am.group(1)).rstrip(":"), "effects": [clean(li) for li in li_items(am.group(2))]})
            items = [parse_item_block(im, im.group(4)) for im in item_re.finditer(body)]
            res["sets"].append({"key": sid, "name": name, "icon": first_img_src(head), "description": [d for d in desc if d],
                                "bonis": bonis, "affects": affects, "items": items,
                                "url": A18 + kind + ".html#" + sid})
    if len(loose_parts) == 2:
        res["loose_intro"] = [clean(p) for p in re.findall(r"<p>(.*?)</p>", loose_parts[1].split("<div", 1)[0], re.S)]
        res["loose"] = [parse_item_block(im, im.group(4)) for im in item_re.finditer(loose_parts[1])]
    return res


def parse_intros():
    return {name: page_intro(fetch_text(A18 + name + ".html"))
            for name in ("waren", "gebaeude", "zivilisation", "produktionsketten")}


# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--only", choices=["waren", "zivilisation", "gebaeude", "ketten", "tiere", "artefakte", "pflanzen"])
    args = ap.parse_args()
    ac.OFFLINE = args.offline
    PARSED_DIR.mkdir(parents=True, exist_ok=True)

    def dump(name, data):
        (PARSED_DIR / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))

    if args.only in (None, "waren"):
        w = parse_waren()
        dump("waren", w)
        print("waren:", [(c["name"], len(c["goods"])) for c in w], "total", sum(len(c["goods"]) for c in w))
    if args.only in (None, "zivilisation"):
        z = parse_zivilisation()
        dump("zivilisation", z)
        lv = [l for r in z for l in r["levels"]]
        print("zivilisation:", [(r["name"], len(r["levels"])) for r in z], "levels", len(lv))
        bad = [l["name"] for l in lv if not l["baukosten"] or len(l["sections"]) < 2 or not l["description"]]
        print("  incomplete levels:", bad)
    if args.only in (None, "gebaeude"):
        g = parse_gebaeude()
        dump("gebaeude", g)
        import collections
        print("gebaeude:", len(g), collections.Counter(b["kategorie"] for b in g).most_common())
        print("  without kategorie:", [b["name"] for b in g if not b["kategorie"]][:20])
        print("  without prose:", len([b for b in g if not b["prose"]]), " with chain:", len([b for b in g if b["chain"]]))
    if args.only in (None, "ketten"):
        k = parse_ketten()
        dump("ketten", k)
        print("ketten:", [(r["name"], len(r["chains"])) for r in k], "total", sum(len(r["chains"]) for r in k))
        print("  without diagram:", [c["name"] for r in k for c in r["chains"] if not c["diagram"]])
    if args.only is None:
        intros = parse_intros()
        dump("intros", intros)
        print("intros:", {k: len(v) for k, v in intros.items()})
    for kind in ("tiere", "artefakte", "pflanzen"):
        if args.only in (None, kind):
            it = parse_items(kind)
            dump(kind, it)
            n_set = sum(len(s["items"]) for s in it["sets"])
            print(f"{kind}: sets {len(it['sets'])}, items in sets {n_set}, loose {len(it['loose'])}, total {n_set + len(it['loose'])}")
            print("  sets without affects:", [s["name"] for s in it["sets"] if not s["affects"]])


if __name__ == "__main__":
    main()
