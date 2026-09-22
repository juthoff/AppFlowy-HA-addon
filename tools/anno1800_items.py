#!/usr/bin/env python3
"""Build tools/anno1800_data/parsed/items.json: every Anno 1800 "Item"
(general equippable items and specialists across all slot types, the
Museum/Botanischer-Garten/Zoo collectible sets, build permits, and quest
items) with a German name, rarity, human-readable effects, resolved target
buildings/ships, and a locally downloaded icon.

Source: https://github.com/jansepke/anno-toolkit (MIT), which ships the raw
game-extracted item data plus a German/English text table and icon art. The
effect-label and rendering rules below are a direct port of that repo's own
src/data/AnnoItemFactory.ts and src/components/items-page/ItemEffects.tsx,
and the upgrade->label table is transcribed verbatim from src/anno-config.ts.

Pure function of the cached upstream JSON/icons (downloaded on a cache miss
unless --offline), same convention as anno1800_parse.py.
"""
import argparse
import html
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "anno1800_data"
TOOLKIT_DIR = DATA_DIR / "toolkit"
ICON_DIR = DATA_DIR / "icons_items"
PARSED_DIR = DATA_DIR / "parsed"
TOOLKIT_BASE = "https://raw.githubusercontent.com/jansepke/anno-toolkit/main"
UA = {"User-Agent": "Mozilla/5.0 (anno1800-items)"}
OFFLINE = False

# ----------------------------------------------------------------------------
# category -> (asset file stem, German label)
# ----------------------------------------------------------------------------
CATEGORIES = [
    ("harboroffice", "harborofficeitem", "Hafenmeisterei"),
    ("guildhouse", "guildhouseitem", "Handelskammer"),
    ("townhall", "townhallitem", "Rathaus"),
    ("lodge", "lodgeitem", "Quartier"),
    ("shipspecialist", "shipspecialist", "Schiffsspezialisten"),
    ("vehicle", "vehicleitem", "Fahrzeuge"),
    ("warship", "warshipitem", "Kriegsschiffe"),
    ("ship", "shipitem", "Schiffe"),
    ("sailship", "sailshipitem", "Segelschiffe"),
    ("steamship", "steamshipitem", "Dampfschiffe"),
    ("airship", "airshipitem", "Luftschiffe"),
    ("aarhantship", "aarhantshipitem", "Aarhant-Schiff"),
    ("zoo", "cultureitem", "Zoo"),
    ("museum", "museumitem", "Museum"),
    ("botanicgarden", "botanicgardenitem", "Botanischer Garten"),
    ("pavilion", "pavilionitem", "Pavillon"),
    ("divingvessel", "divingvesselitem", "Tauchboot"),
    ("fluff", "fluffitem", "Sonstiges"),
    ("headquarter", "headquarteritem", "Hauptquartier"),
    ("dockland", "docklanditem", "Anlegestelle"),
    ("buildpermit", "buildpermititem", "Baugenehmigung"),
    ("quest", "questitem", "Questgegenstände"),
]

# rarity key -> Anno text-table labelId (src/anno-config.ts: rarities)
RARITIES = {
    "common": 118002,
    "uncommon": 118003,
    "rare": 118004,
    "epic": 118005,
    "legendary": 118006,
    "narrative": 19850,
}

# upgrade-block key -> Anno text-table labelId (src/anno-config.ts: upgrades, verbatim)
UPGRADES = {
    "ProductivityUpgrade": 118000,
    "MaintenanceUpgrade": 2320,
    "ReplaceInputs": 20081,
    "AttractivenessUpgrade": 145011,
    "AdditionalOutput": 20074,
    "ReplacingWorkforce": 12480,
    "WorkforceAmountUpgrade": 12337,
    "ModuleLimitPercent": 12075,
    "NeededAreaPercentUpgrade": 15319,
    "IncidentFireIncreaseUpgrade": 12225,
    "ProvideIndustrialization": 12485,
    "IncidentExplosionIncreaseUpgrade": 14292,
    "IncidentRiotIncreaseUpgrade": 14290,
    "PipeCapacityUpgrade": 127395,
    "RiotInfluenceUpgrade": 14513,
    "AdditionalHappiness": 12314,
    "ResolverUnitDecreaseUpgrade": 21508,
    "ResolverUnitMovementSpeedUpgrade": 12012,
    "ResolverUnitCountUpgrade": 3897,
    "AddedFertility": 23371,
    "AttractivenessPositive": 145011,
    "PublicServiceFullSatisfactionDistance": 2321,
    "InputBenefitModifier": 12690,
    "ResidentsUpgrade": 2322,
    "TaxModifierInPercent": 12677,
    "IncidentIllnessIncreaseUpgrade": 12226,
    "NeedProvideNeedUpgrade": 12315,
    "StressUpgrade": 2323,
    "GoodConsumptionUpgrade": 21386,
    "WorkforceModifierInPercent": 12676,
    "InputAmountUpgrade": 23509,
    "SpecialUnitHappinessThresholdUpgrade": 21593,
    "BlockHostileTakeover": 15801,
    "SpawnProbabilityFactor": 20084,
    "ConstructionCostInPercent": 12723,
    "AddAssemblyOptions": 21494,
    "BaseDamageUpgrade": 2334,
    "AttackSpeedUpgrade": 2336,
    "Hitpoints": 2333,
    "GenProbability": 12920,
    "GenPool": 12315,
    "BlockBuyShare": 15802,
    "HappinessIgnoresMorale": 15811,
    "MaxHitpointsUpgrade": 1154,
    "AttackRangeUpgrade": 12021,
    "HitpointDamage": 2334,
    "LineOfSightRangeUpgrade": 15266,
    "SelfHealUpgrade": 15195,
    "SelfHealPausedTimeIfAttackedUpgrade": 15196,
    "HealRadiusUpgrade": 15264,
    "HealPerMinuteUpgrade": 15265,
    "HealBuildingsPerMinuteUpgrade": 15265,
    "AccuracyUpgrade": 12062,
    "PierSpeedUpgrade": 15197,
    "DamageReceiveFactor": 19136,
    "MoraleDamage": 9499,
    "IncidentArcticIllnessIncreaseUpgrade": 22982,
    "HeatRangeUpgrade": 2321,
    "ForwardSpeedUpgrade": 2339,
    "IgnoreDamageFactorUpgrade": 15262,
    "LoadingSpeedUpgrade": 15197,
    "IgnoreWeightFactorUpgrade": 15261,
    "MaintainanceUpgrade": 2320,
    "ActiveTradePriceInPercent": 15198,
}

IGNORED_UPDATES = {
    "PublicServiceNoSatisfactionDistance",
    "PublicServiceFullSatisfactionDistance",
    "OutputAmountFactorUpgrade",
}

# asset pool "GGJ Items" (test/dev data, confirmed via anno-toolkit's own AnnoItemFactory.ts)
IGNORED_ITEMS = {
    24012, 24014, 24016, 24018, 24019, 24023, 24033, 24034, 24036, 24043, 24044, 24054, 24048, 24061, 24064, 24065,
    24068, 24077, 24078, 24079, 24081, 24082, 24086, 24087, 24100, 24107, 24108, 24109, 24113, 24114, 24151, 24152,
    24153, 24154, 24155, 24159, 24160, 24162, 24163, 24164, 24179, 24191, 24192, 24195, 24196, 24197, 24201, 24199,
    24198, 24248, 24286, 24368, 24372, 24373, 24656, 24655, 24654,
}

RENDER_PERCENTAGE = {
    "ConstructionCostInPercent", "AttackSpeedUpgrade", "GenProbability",
    "TaxModifierInPercent", "WorkforceModifierInPercent", "ModuleLimitPercent",
}
RENDER_BOOLEAN = {"BlockHostileTakeover", "BlockBuyShare", "HappinessIgnoresMorale", "ProvideIndustrialization"}


# ----------------------------------------------------------------------------
# fetch / disk cache
# ----------------------------------------------------------------------------
def _download(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            if attempt == 2:
                raise
            time.sleep(2)
        except Exception:  # noqa: BLE001
            if attempt == 2:
                raise
            time.sleep(2)


def fetch_bytes(url_path, cache_path):
    if cache_path.exists():
        return cache_path.read_bytes()
    if OFFLINE:
        raise SystemExit(f"offline: {url_path} not cached at {cache_path}")
    data = _download(f"{TOOLKIT_BASE}/{url_path}")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(data)
    return data


def fetch_json(url_path, cache_path):
    return json.loads(fetch_bytes(url_path, cache_path).decode("utf-8"))


def fetch_asset(name):
    return fetch_json(f"data/anno/assets/{name}.json", TOOLKIT_DIR / "assets" / f"{name}.json")


def fetch_texts(lang):
    return fetch_json(f"data/anno/texts/texts_{lang}.json", TOOLKIT_DIR / "texts" / f"texts_{lang}.json")


def fetch_icon(icon_filename):
    """Download (and cache) the icon PNG, return its path relative to DATA_DIR.

    Tries the _0/_1/_2 pre-rendered variants in order (not every icon has a
    variant 0) and gives up gracefully (returns None) rather than aborting
    the whole run on a single missing/renamed icon.
    """
    if not icon_filename:
        return None
    base = icon_filename.replace("data/ui/2kimages/", "").replace(".png", "")
    for suffix in ("_0", "_1", "_2"):
        rel = f"{base}{suffix}.png"
        local_path = ICON_DIR / rel
        if local_path.exists():
            return f"icons_items/{rel}"
        if OFFLINE:
            continue
        try:
            data = _download(f"{TOOLKIT_BASE}/public/img/{rel}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            raise
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(data)
        return f"icons_items/{rel}"
    print(f"  warning: no icon found for {icon_filename}")
    return None


# ----------------------------------------------------------------------------
# text resolution
# ----------------------------------------------------------------------------
def clean_text(s):
    if not isinstance(s, str):
        return s
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"</?[a-zA-Z][^>]*>", "", s)
    return html.unescape(s).strip()


def text_of(guid, texts_de, texts_en):
    if guid is None:
        return None
    key = str(int(guid)) if isinstance(guid, (int, float)) else str(guid)
    return texts_de.get(key) or texts_en.get(key)


def resolve_name(values, texts_de, texts_en):
    guid = values["Standard"]["GUID"]
    raw_name = values["Standard"].get("Name")
    de = texts_de.get(str(guid))
    if de:
        return clean_text(de), "de"
    en = texts_en.get(str(guid))
    if en:
        return clean_text(en), "en"
    return raw_name, "raw"


def resolve_flavor(values, texts_de, texts_en):
    desc_id = values["Standard"].get("InfoDescription")
    if not desc_id:
        exp = values.get("ExpeditionAttribute")
        if isinstance(exp, dict):
            desc_id = exp.get("FluffText")
    if not desc_id:
        return None, None
    de = texts_de.get(str(desc_id))
    if de:
        return clean_text(de), "de"
    en = texts_en.get(str(desc_id))
    if en:
        return clean_text(en), "en"
    return None, None


def resolve_rarity(values, texts_de, texts_en):
    item = values.get("Item")
    raw = item.get("Rarity") if isinstance(item, dict) else None
    key = (raw or "common").lower()
    label_id = RARITIES.get(key)
    label = text_of(label_id, texts_de, texts_en) if label_id else None
    return key, (label or raw or "Gewöhnlich")


# ----------------------------------------------------------------------------
# effects
# ----------------------------------------------------------------------------
def translate_value(upgrade_key, value, texts_de, texts_en, rewardpools):
    if upgrade_key == "GenPool":
        pool = rewardpools.get(value)
        if not pool:
            return [value]
        items = pool["Values"]["RewardPool"]["ItemsPool"]["Item"]
        items = items if isinstance(items, list) else [items]
        return [text_of(it.get("ItemLink"), texts_de, texts_en) for it in items]

    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 1000:
        t = text_of(value, texts_de, texts_en)
        if t is not None:
            return clean_text(t)

    if isinstance(value, dict):
        value = dict(value)
        item = value.get("Item")
        if isinstance(item, dict):
            item = [item]
        if isinstance(item, list):
            new_items = []
            for it in item:
                if not isinstance(it, dict):
                    new_items.append(it)
                    continue
                it = dict(it)
                for prop, v in list(it.items()):
                    if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 100:
                        t = text_of(v, texts_de, texts_en)
                        if t is not None:
                            it[f"{prop}_label"] = clean_text(t)
                new_items.append(it)
            value["Item"] = new_items
    return value


def render_upgrade_item(key, item):
    if key == "ReplaceInputs":
        return f"{item.get('OldInput_label')} -> {item.get('NewInput_label')}"
    if key == "AdditionalOutput":
        return f"{item.get('Amount')}/{item.get('AdditionalOutputCycle')} {item.get('Product_label', '')}"
    if key == "InputAmountUpgrade":
        return f"{item.get('Amount')} {item.get('Product_label')}" if item.get("Amount", 0) < 0 else None
    if key == "AddAssemblyOptions":
        return item.get("NewOption_label")
    if key == "InputBenefitModifier":
        if item.get("AdditionalMoney"):
            return f"{item.get('Product_label')} +{item['AdditionalMoney']} Money"
        if item.get("AdditionalSupply"):
            return f"{item.get('Product_label')} +{item['AdditionalSupply']} Supply"
        return f"{item.get('Product_label')} +{item.get('AdditionalHappiness')} Happiness"
    if key == "NeedProvideNeedUpgrade":
        return f"{item.get('SubstituteNeed_label')} -> {item.get('ProvidedNeed_label')}"
    if key == "GoodConsumptionUpgrade":
        return f"{item.get('AmountInPercent')}% {item.get('ProvidedNeed_label')}"
    return json.dumps(item, ensure_ascii=False)


def render_upgrade(key, label, value):
    if isinstance(value, dict) and value.get("Value"):
        pct = "%" if value.get("Percental") == 1 else ""
        return f"{label}: {value['Value']}{pct}"
    if key in RENDER_BOOLEAN:
        return label
    if key in RENDER_PERCENTAGE:
        return f"{label}: {value}%"
    if key == "DamageReceiveFactor" and isinstance(value, dict) and value:
        first = next(iter(value.values()))
        factor = first.get("Factor", 1) if isinstance(first, dict) else 1
        return f"{label}: {round((1 - factor) * 100)}%"
    if key == "GenPool":
        if isinstance(value, list):
            return f"{label}: " + ", ".join(v for v in value if v)
        return f"{label}: {value}"
    if isinstance(value, (str, int, float)) and value != "":
        return f"{label}: {value}"
    if isinstance(value, dict) and isinstance(value.get("Item"), list):
        rendered = [render_upgrade_item(key, it) for it in value["Item"] if isinstance(it, dict)]
        rendered = [r for r in rendered if r is not None]
        return f"{label}: " + ", ".join(rendered) if rendered else None
    return None


def resolve_effects(values, texts_de, texts_en, rewardpools):
    effects = []
    for block_key, block_value in values.items():
        if "Upgrade" not in block_key or not isinstance(block_value, dict):
            continue
        for upgrade_key, raw_value in block_value.items():
            if upgrade_key in IGNORED_UPDATES or raw_value == "":
                continue
            label_id = UPGRADES.get(upgrade_key)
            if label_id is None:
                continue
            label = text_of(label_id, texts_de, texts_en) or upgrade_key
            value = translate_value(upgrade_key, raw_value, texts_de, texts_en, rewardpools)
            rendered = render_upgrade(upgrade_key, label, value)
            if rendered:
                effects.append(rendered)
    return effects


# ----------------------------------------------------------------------------
# effect targets
# ----------------------------------------------------------------------------
def resolve_targets(values, pools, texts_de, texts_en):
    item_effect = values.get("ItemEffect")
    if not isinstance(item_effect, dict):
        return None
    effect_targets = item_effect.get("EffectTargets")
    if not isinstance(effect_targets, dict):
        return None
    targets = effect_targets.get("Item")
    if targets is None:
        return None
    targets = targets if isinstance(targets, list) else [targets]

    pool_label = None
    member_names = []
    for t in targets:
        guid = t.get("GUID") if isinstance(t, dict) else t
        if guid is None:
            continue
        pool = pools.get(guid)
        if pool:
            label = text_of(guid, texts_de, texts_en)
            if not label:
                override = pool["Values"].get("Text", {}).get("TextOverride")
                label = text_of(override, texts_de, texts_en)
            if label and not pool_label:
                pool_label = clean_text(label)
            members = pool["Values"]["ItemEffectTargetPool"]["EffectTargetGUIDs"]["Item"]
            members = members if isinstance(members, list) else [members]
            for m in members:
                mg = m.get("GUID") if isinstance(m, dict) else m
                name = text_of(mg, texts_de, texts_en)
                if name:
                    member_names.append(clean_text(name))
        else:
            name = text_of(guid, texts_de, texts_en)
            if name:
                member_names.append(clean_text(name))

    if not member_names and not pool_label:
        return None
    return {"pool_label": pool_label, "targets": member_names}


def resolve_expedition_attributes(values):
    exp = values.get("ExpeditionAttribute")
    if not isinstance(exp, dict):
        return []
    attrs = exp.get("ExpeditionAttributes")
    items = attrs.get("Item") if isinstance(attrs, dict) else None
    if items is None:
        return []
    items = items if isinstance(items, list) else [items]
    out = []
    for it in items:
        if isinstance(it, dict) and it.get("Attribute"):
            out.append({"attribute": it["Attribute"].lower(), "amount": it.get("Amount", 1)})
    return out


def resolve_acquisition(values):
    item = values.get("Item")
    out = {}
    if isinstance(item, dict):
        if "TradePrice" in item:
            out["trade_price"] = item["TradePrice"]
        if "TradePriceOnlineCurrency" in item:
            out["trade_price_online_currency"] = item["TradePriceOnlineCurrency"]
    return out


# ----------------------------------------------------------------------------
# classification
# ----------------------------------------------------------------------------
def item_type_of(values, template):
    item = values.get("Item")
    allocation = item.get("Allocation") if isinstance(item, dict) else None
    return f"{allocation.lower()}item" if allocation else template.lower()


def is_active(values):
    action = values.get("ItemAction")
    if not isinstance(action, dict):
        return False
    return any(k in action for k in ("ActiveBuff", "ItemAction", "ActionTarget"))


# ----------------------------------------------------------------------------
# build one item
# ----------------------------------------------------------------------------
def build_item(asset, category_key, category_label, source_file, texts_de, texts_en, pools, rewardpools,
                download_icons):
    values = asset["Values"]
    guid = values["Standard"]["GUID"]
    if guid in IGNORED_ITEMS:
        return None

    name, name_source = resolve_name(values, texts_de, texts_en)
    rarity, rarity_label = resolve_rarity(values, texts_de, texts_en)
    flavor_text, _ = resolve_flavor(values, texts_de, texts_en)
    item = values.get("Item")
    item_type_raw = item.get("ItemType") if isinstance(item, dict) else None
    icon_filename = values["Standard"].get("IconFilename")
    icon_rel = fetch_icon(icon_filename) if download_icons else None

    return {
        "id": guid,
        "name": name,
        "name_source": name_source,
        "category": category_key,
        "category_label": category_label,
        "sub_type": "active" if is_active(values) else "passive",
        "item_type": item_type_raw,
        "rarity": rarity,
        "rarity_label": rarity_label,
        "effects": resolve_effects(values, texts_de, texts_en, rewardpools),
        "effect_targets": resolve_targets(values, pools, texts_de, texts_en),
        "expedition_attributes": resolve_expedition_attributes(values),
        "acquisition": resolve_acquisition(values),
        "flavor_text": flavor_text,
        "icon": icon_rel,
        "icon_source_url": f"{TOOLKIT_BASE}/public/img/"
        + icon_filename.replace("data/ui/2kimages/", "").replace(".png", "_0.png") if icon_filename else None,
        "filed_elsewhere": item_type_of(values, asset.get("Template", "")) != f"{source_file}".lower(),
        "source": {"file": f"{source_file}.json", "guid": guid},
    }


# ----------------------------------------------------------------------------
def load_context():
    texts_de = fetch_texts("german")
    texts_en = fetch_texts("english")
    pools = {p["Values"]["Standard"]["GUID"]: p for p in fetch_asset("itemeffecttargetpool")}
    rewardpools = {r["Values"]["Standard"]["GUID"]: r for r in fetch_asset("rewardpool")}
    return texts_de, texts_en, pools, rewardpools


def main():
    global OFFLINE
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--only", choices=[c[0] for c in CATEGORIES])
    ap.add_argument("--no-icons", action="store_true")
    args = ap.parse_args()
    OFFLINE = args.offline
    PARSED_DIR.mkdir(parents=True, exist_ok=True)

    texts_de, texts_en, pools, rewardpools = load_context()

    categories_out = {}
    items_out = []
    for key, source_file, label in CATEGORIES:
        if args.only and args.only != key:
            continue
        assets = fetch_asset(source_file)
        count = 0
        for asset in assets:
            try:
                item = build_item(asset, key, label, source_file, texts_de, texts_en, pools, rewardpools,
                                   download_icons=not args.no_icons)
            except Exception as e:  # noqa: BLE001
                guid = asset.get("Values", {}).get("Standard", {}).get("GUID")
                print(f"  warning: skipping {key} item {guid}: {e}")
                continue
            if item is None:
                continue
            items_out.append(item)
            count += 1
        categories_out[key] = {"label_de": label, "count": count}
        print(f"{key}: {count} items")

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "repo": "https://github.com/jansepke/anno-toolkit",
            "license": "MIT (code); game text/art © Ubisoft/Blue Byte, mirrored for reference only",
        },
        "categories": categories_out,
        "items": items_out,
    }

    out_path = PARSED_DIR / "items.json"
    if args.only:
        # merge into any existing file rather than clobbering the other categories
        if out_path.exists():
            existing = json.loads(out_path.read_text())
            existing["categories"].update(categories_out)
            existing["items"] = [i for i in existing["items"] if i["category"] != args.only] + items_out
            existing["generated_at"] = result["generated_at"]
            result = existing
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1))
    print(f"total: {len(result['items'])} items -> {out_path}")


if __name__ == "__main__":
    main()
