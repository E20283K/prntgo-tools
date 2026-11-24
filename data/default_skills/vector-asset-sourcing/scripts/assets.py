#!/usr/bin/env python3
"""Find, vet and download real vector assets (SVG) from open sources.

Sources
  iconify   api.iconify.design  - 200k+ icons in 150+ sets, per-set licence (IconStash is a UI on this API)
  openverse api.openverse.org   - openly licensed images incl. SVG (aggregates Wikimedia, Flickr, ...)
  commons   commons.wikimedia.org - marks, flags, symbols, logos of public standards

Usage
  python assets.py search "do not bleach" [--source iconify|openverse|commons|all]
                    [--limit 8] [--prefix ginetex] [--all-licenses]
  python assets.py fetch <candidate-id> --out <dir> [--name file-stem] [--color "#000000"] [--cross]
                    (--cross: plain symbol + one solid X; use for every "do not ..." care symbol)
  python assets.py sets "care"            # list Iconify icon sets matching a word, with licences

Candidate ids are printed by `search`:  iconify:<prefix>:<name>  |  commons:<File title>  |  openverse:<uuid>
`fetch` writes <dir>/<name>.svg (sanitised) and appends provenance to <dir>/manifest.json.
Standard library only. Prints JSON to stdout.
"""
import argparse, json, re, sys, urllib.parse, urllib.request, os, datetime, html

UA = "vector-asset-sourcing/1.0 (print design helper; python-urllib)"
TIMEOUT = 25

# ---------- licence policy ----------------------------------------------------
# ok        : commercial use, no attribution needed on the product
# attribute : commercial use allowed but credit is required somewhere (keep manifest, tell the user)
# reject    : non-commercial / no-derivatives / unknown
def classify_license(lic: str) -> str:
    l = (lic or "").lower().replace("_", "-").strip()
    if not l:
        return "reject"
    if any(k in l for k in ("-nc", "nc-", "noncommercial", "non-commercial", "-nd", "nd-", "noderiv")):
        return "reject"
    if any(k in l for k in ("cc0", "pdm", "public domain", "publicdomain", "pd-", "pd ", "no restrictions")) or l == "pd":
        return "ok"
    if re.search(r"\b(mit|isc|apache|bsd|ofl|sil open font|unlicense|0bsd)\b", l):
        return "ok"   # permissive: keep the notice in the manifest; nothing printed on the product
    if "by-sa" in l or "by sa" in l or "share" in l:
        return "attribute"  # also share-alike: derivative artwork must carry the same licence
    if "cc by" in l or "cc-by" in l or l.startswith("by") or "attribution" in l:
        return "attribute"
    if "gpl" in l:
        return "attribute"
    return "reject"


def get(url, raw=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = r.read()
    return data if raw else json.loads(data.decode("utf-8"))


def strip_html(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()

# ---------- iconify -------------------------------------------------------------
_set_cache = {}

def iconify_sets(prefixes):
    need = [p for p in prefixes if p not in _set_cache]
    if need:
        info = get("https://api.iconify.design/collections?prefixes=" + ",".join(need))
        for p in need:
            _set_cache[p] = info.get(p, {})
    return {p: _set_cache.get(p, {}) for p in prefixes}


def search_iconify(q, limit, prefix=None):
    params = {"query": q, "limit": max(limit, 32)}
    if prefix:
        params["prefixes"] = prefix
    res = get("https://api.iconify.design/search?" + urllib.parse.urlencode(params))
    icons = res.get("icons", [])[: limit * 3]
    sets = iconify_sets(sorted({i.split(":")[0] for i in icons}))
    out = []
    for icon in icons:
        p, n = icon.split(":", 1)
        s = sets.get(p, {})
        lic = (s.get("license") or {}).get("spdx") or (s.get("license") or {}).get("title", "")
        out.append({
            "id": f"iconify:{p}:{n}",
            "title": n.replace("-", " "),
            "set": s.get("name", p),
            "svg_url": f"https://api.iconify.design/{p}/{n}.svg",
            "preview": f"https://api.iconify.design/{p}/{n}.svg?height=64",
            "license": lic,
            "author": (s.get("author") or {}).get("name", ""),
            "landing": f"https://icon-sets.iconify.design/{p}/{n}/",
            "palette": s.get("palette", False),  # True = multicolour icon
        })
    return out

# ---------- wikimedia commons ---------------------------------------------------

def commons_info(titles):
    params = {
        "action": "query", "format": "json", "prop": "imageinfo",
        "titles": "|".join(titles), "iiprop": "url|mime|size|extmetadata",
        "iiextmetadatafilter": "LicenseShortName|Artist|AttributionRequired|UsageTerms|ImageDescription|Restrictions",
    }
    return get("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params))


def _commons_rows(pages):
    out = []
    for p in pages.values():
        ii = (p.get("imageinfo") or [{}])[0]
        if ii.get("mime") != "image/svg+xml":
            continue
        md = ii.get("extmetadata", {})
        val = lambda k: strip_html((md.get(k) or {}).get("value", ""))
        out.append({
            "id": "commons:" + p["title"],
            "title": p["title"].removeprefix("File:"),
            "svg_url": ii.get("url", "").split("?")[0],
            "preview": ii.get("url", "").split("?")[0],
            "license": val("LicenseShortName"),
            "author": val("Artist")[:120],
            "landing": ii.get("descriptionurl", ""),
            "restrictions": val("Restrictions"),  # e.g. "trademarked", "insignia"
            "description": val("ImageDescription")[:200],
        })
    return out


def search_commons(q, limit):
    params = {
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
        "gsrsearch": f"{q} filetype:svg", "gsrlimit": limit,
        "prop": "imageinfo", "iiprop": "url|mime|size|extmetadata",
        "iiextmetadatafilter": "LicenseShortName|Artist|AttributionRequired|UsageTerms|ImageDescription|Restrictions",
    }
    res = get("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params))
    pages = (res.get("query") or {}).get("pages", {})
    rows = _commons_rows(pages)
    order = {p["title"]: p.get("index", 0) for p in pages.values()}
    rows.sort(key=lambda r: order.get("File:" + r["title"], 0))
    return rows

# ---------- openverse -----------------------------------------------------------

def search_openverse(q, limit, commercial=True):
    params = {"q": q, "extension": "svg", "page_size": min(limit, 20)}
    if commercial:
        params["license_type"] = "commercial"
    res = get("https://api.openverse.org/v1/images/?" + urllib.parse.urlencode(params))
    out = []
    for r in res.get("results", []):
        lic = f"CC {r.get('license','').upper()} {r.get('license_version') or ''}".strip()
        if r.get("license") in ("cc0", "pdm"):
            lic = r["license"].upper()
        out.append({
            "id": "openverse:" + r["id"],
            "title": r.get("title", ""),
            "svg_url": r.get("url", ""),
            "preview": r.get("thumbnail", ""),
            "license": lic,
            "author": r.get("creator") or "",
            "landing": r.get("foreign_landing_url", ""),
            "provider": r.get("provider", ""),
        })
    return out

# ---------- commands ------------------------------------------------------------

def cmd_search(a):
    sources = ["iconify", "commons", "openverse"] if a.source == "all" else [a.source]
    results, errors = [], {}
    for s in sources:
        try:
            if s == "iconify":
                rows = search_iconify(a.query, a.limit, a.prefix)
            elif s == "commons":
                rows = search_commons(a.query, a.limit)
            else:
                rows = search_openverse(a.query, a.limit, commercial=not a.all_licenses)
        except Exception as e:  # keep going with other sources
            errors[s] = str(e)[:200]
            continue
        for r in rows:
            r["source"] = s
            r["license_class"] = classify_license(r["license"])
            if not a.all_licenses and r["license_class"] == "reject":
                continue
            results.append(r)
            if sum(1 for x in results if x["source"] == s) >= a.limit:
                break
    print(json.dumps({"query": a.query, "results": results, "errors": errors}, ensure_ascii=False, indent=1))


def cmd_sets(a):
    data = get("https://api.iconify.design/collections")
    w = re.compile(r"\b" + re.escape(a.word.lower()))
    rows = []
    for p, s in data.items():
        hay = " ".join([p, s.get("name", ""), s.get("category", ""), " ".join(s.get("tags", []) or []),
                        " ".join(s.get("samples", []) or [])]).lower().replace("-", " ")
        if w.search(hay):
            lic = (s.get("license") or {}).get("spdx") or (s.get("license") or {}).get("title", "")
            rows.append({"prefix": p, "name": s.get("name"), "total": s.get("total"), "license": lic,
                         "license_class": classify_license(lic), "palette": s.get("palette", False),
                         "samples": s.get("samples", [])[:6]})
    print(json.dumps(rows, ensure_ascii=False, indent=1))


_BAD_TAGS = re.compile(r"<(script|foreignObject|iframe|object|embed)\b.*?</\1\s*>|<(script|foreignObject|iframe|object|embed)\b[^>]*/>", re.S | re.I)
_ON_ATTR = re.compile(r"\s+on[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*')", re.I)
_EXT_HREF = re.compile(r"\s+(xlink:)?href\s*=\s*(\"(?!#|data:)[^\"]*\"|'(?!#|data:)[^']*')", re.I)


def sanitize_svg(text):
    text = _BAD_TAGS.sub("", text)
    text = _ON_ATTR.sub("", text)
    text = _EXT_HREF.sub("", text)          # no external references: the file must be self-contained
    text = re.sub(r"<!DOCTYPE[^>]*(\[.*?\])?\s*>", "", text, flags=re.S)  # no entity tricks
    return text


# Visible bounds (x0, y0, x1, y1) of the plain ginetex base symbols on their 24x24 canvas.
# Used to draw a solid "do not" cross that matches the symbol exactly.
_CROSS_BOUNDS = {
    "washing": (0, 4, 24, 20), "hand-wash-at-40c": (0, 4, 24, 20), "hand-wash-ambient-temperature": (0, 4, 24, 20),
    "bleaching": (1.33, 2.67, 22.67, 21.33), "any-bleach-allowed": (1.33, 2.67, 22.67, 21.33),
    "tumble-drying": (1.33, 1.33, 22.67, 22.67), "natural-drying": (1.33, 1.33, 22.67, 22.67),
    "drying": (1.33, 1.33, 22.67, 22.67),
    "dry-cleaning": (3.36, 3.36, 20.69, 20.69), "wet-cleaning": (3.36, 3.36, 20.69, 20.69),
    "professional-wet-cleaning": (3.36, 3.36, 20.69, 20.69),
    "ironing": (2.1, 4.6, 22.4, 19.0),
}
CROSS_WEIGHT = 1.6  # same line weight as the ginetex set


def add_solid_cross(svg, bounds, color="#000000", weight=CROSS_WEIGHT, overshoot=0.6):
    """Append a solid, unbroken X (as two filled bars, so it scales with the art) over the symbol.

    Icon sets often draw "do not" symbols with the X knocked out of the symbol (gaps around the
    crossing lines). Print labels want the plain symbol with one continuous X on top.
    """
    import math
    x0, y0, x1, y1 = bounds
    # keep the X close to 45°: on wide symbols (tub, iron) a cross through the bare bounds looks flat
    cx, cy, w, h = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
    h, w = max(h, 0.85 * w), max(w, 0.85 * h)
    x0, x1, y0, y1 = cx - w / 2 - overshoot, cx + w / 2 + overshoot, cy - h / 2 - overshoot, cy + h / 2 + overshoot
    bars = []
    for (ax, ay, bx, by) in ((x0, y0, x1, y1), (x0, y1, x1, y0)):
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy); nx, ny = -dy / L * weight / 2, dx / L * weight / 2
        pts = [(ax + nx, ay + ny), (bx + nx, by + ny), (bx - nx, by - ny), (ax - nx, ay - ny)]
        bars.append("M" + " L".join(f"{x:.3f} {y:.3f}" for x, y in pts) + " Z")
    cross = f'<path fill="{color}" d="{" ".join(bars)}"/>'
    return re.sub(r"</svg>\s*$", cross + "</svg>", svg.strip())


def resolve(cid):
    src, rest = cid.split(":", 1)
    if src == "iconify":
        p, n = rest.split(":", 1)
        s = iconify_sets([p]).get(p, {})
        lic = (s.get("license") or {}).get("spdx") or (s.get("license") or {}).get("title", "")
        return {"source": src, "id": cid, "svg_url": f"https://api.iconify.design/{p}/{n}.svg", "license": lic,
                "author": (s.get("author") or {}).get("name", ""), "landing": f"https://icon-sets.iconify.design/{p}/{n}/",
                "title": n}
    if src == "commons":
        title = rest if rest.startswith("File:") else "File:" + rest
        rows = _commons_rows((commons_info([title]).get("query") or {}).get("pages", {}))
        if not rows:
            raise SystemExit(f"not an SVG on Commons or not found: {title}")
        r = rows[0]; r["source"] = src; return r
    if src == "openverse":
        r = get(f"https://api.openverse.org/v1/images/{rest}/")
        lic = "CC0" if r.get("license") == "cc0" else ("PDM" if r.get("license") == "pdm" else f"CC {r.get('license','').upper()} {r.get('license_version') or ''}".strip())
        return {"source": src, "id": cid, "svg_url": r.get("url"), "license": lic, "author": r.get("creator") or "",
                "landing": r.get("foreign_landing_url", ""), "title": r.get("title", "")}
    raise SystemExit("unknown source prefix: " + src)


def cmd_fetch(a):
    info = resolve(a.id)
    info["license_class"] = classify_license(info["license"])
    if info["license_class"] == "reject" and not a.force:
        raise SystemExit(json.dumps({"error": "licence not usable for commercial print", "license": info["license"], "id": a.id}))
    url = info["svg_url"]
    if info["source"] == "iconify":
        q = {}
        if a.color:
            q["color"] = a.color
        q["height"] = "none"  # keep the icon's own viewBox units
        url += "?" + urllib.parse.urlencode(q)
    raw = get(url, raw=True).decode("utf-8", "replace")
    if "<svg" not in raw[:5000].lower():
        raise SystemExit(json.dumps({"error": "download is not an SVG", "url": url}))
    svg = sanitize_svg(raw)
    modified = ""
    if a.cross:
        name = info["id"].split(":")[-1]
        if info["source"] != "iconify":
            raise SystemExit(json.dumps({"error": "--cross works on Iconify icons only"}))
        bounds = _CROSS_BOUNDS.get(name)
        if bounds is None:
            vb = [float(v) for v in re.search(r'viewBox="([^"]+)"', svg).group(1).split()]
            bounds = (vb[0] + vb[2] * 0.06, vb[1] + vb[3] * 0.06, vb[0] + vb[2] * 0.94, vb[1] + vb[3] * 0.94)
        svg = add_solid_cross(svg, bounds, a.color or "#000000")
        modified = "solid X added over the plain symbol"
    os.makedirs(a.out, exist_ok=True)
    stem = a.name or re.sub(r"[^a-z0-9]+", "-", info.get("title", "asset").lower()).strip("-")[:60] or "asset"
    path = os.path.join(a.out, stem + ".svg")
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    man_path = os.path.join(a.out, "manifest.json")
    try:
        manifest = json.load(open(man_path, encoding="utf-8"))
    except Exception:
        manifest = []
    entry = {"file": stem + ".svg", "id": info["id"], "source": info["source"], "license": info["license"],
             "license_class": info["license_class"], "author": info.get("author", ""), "landing": info.get("landing", ""),
             "restrictions": info.get("restrictions", ""), "modified": modified,
             "fetched": datetime.date.today().isoformat()}
    manifest = [m for m in manifest if m.get("file") != entry["file"]] + [entry]
    json.dump(manifest, open(man_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"path": os.path.abspath(path), **entry}, ensure_ascii=False, indent=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search"); s.add_argument("query"); s.add_argument("--source", default="all",
        choices=["all", "iconify", "commons", "openverse"]); s.add_argument("--limit", type=int, default=6)
    s.add_argument("--prefix", help="restrict Iconify to icon set(s), comma separated, e.g. ginetex")
    s.add_argument("--all-licenses", action="store_true", help="also show non-commercial / unknown licences")
    s.set_defaults(fn=cmd_search)
    f = sub.add_parser("fetch"); f.add_argument("id"); f.add_argument("--out", required=True)
    f.add_argument("--name"); f.add_argument("--color", help="Iconify only: recolour currentColor, e.g. '#e6007e'")
    f.add_argument("--cross", action="store_true",
                   help="draw a solid unbroken X over the plain symbol (use for every 'do not …' care symbol)")
    f.add_argument("--force", action="store_true", help="download even if the licence is rejected (reference only)")
    f.set_defaults(fn=cmd_fetch)
    t = sub.add_parser("sets"); t.add_argument("word"); t.set_defaults(fn=cmd_sets)
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    a.fn(a)


if __name__ == "__main__":
    main()
