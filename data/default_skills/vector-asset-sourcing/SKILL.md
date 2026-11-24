---
name: vector-asset-sourcing
description: Build print designs (garment care labels, woven/printed brand labels, size labels, hang tags, packaging stickers, business cards, flyers) from REAL existing vector assets fetched via open APIs (Iconify, Openverse, Wikimedia Commons; IconStash is a UI over Iconify) instead of hand-drawing complex shapes. Use this whenever the user asks to design, recreate, redraw or "draw from a photo" any label, tag, sticker or print layout that contains icons, care symbols, certification marks (EAC, CE, recycling, Mobius, FSC-style), flags, decorative ornaments, flowers or other illustrations — in VectorCraft or as SVG — even if they don't mention icons or APIs. Also use when the user asks where to find a vector symbol, wants a reusable symbol library, or asks whether an icon is free to use commercially.
---

# Vector asset sourcing for print design

The point of this skill: **an AI drawing a care symbol, a mark or an ornament path-by-path is slow and
ends up close but not exact.** For anything that already exists as a standard or as a published icon, find
the real vector, check its licence, and place it. Hand-draw only what is simple (rules, boxes, dots,
die-lines) or what is unique to the client and can't be found (their own logo, when they have no file).

Text always stays **live text objects** (never outlined in the working file; outline only in the print
export), so the user can still edit sizes, dates and article numbers.

## Workflow

### 1. Inventory the design
From the brief or the reference photo, list every element and classify it:

| Class | Examples | How to produce |
|---|---|---|
| **Text** | brand name, size, composition, address, "Made in…" | live text object, choose a close font |
| **Standard symbol** | care symbols, EAC/CE, recycling, Mobius, ♀/♂, arrows, flags | **source** (step 2) |
| **Decorative art** | flowers, leaves, ornaments, frames, patterns | **source**; hand-draw only if nothing fits |
| **Brand artwork** | client logo, mascot | ask for the client's file; else redraw it, and say that you did |
| **Geometry** | rules, borders, hole punch, die-line, barcode box | draw directly (trivial shapes) |

Write the inventory down briefly before you search; it keeps the search focused and lets the user
correct a misread symbol early (photos of labels are often blurry. Say which symbols you were
unsure about).

### 2. Source each symbol / artwork
Use the bundled script (standard library Python, prints JSON):

```bash
S="<skill-dir>/scripts/assets.py"
python "$S" search "do not tumble dry" --source iconify --prefix ginetex   # care symbols: exact set
python "$S" search "EAC mark" --source commons                            # marks, flags, standards
python "$S" search "flower" --source iconify --limit 10                   # ornaments, illustrations
python "$S" search "laurel wreath" --source openverse                     # broader open-licence art
python "$S" sets floral                                                   # find whole icon sets by theme
python "$S" fetch iconify:ginetex:do-not-bleach --out <project>/assets --color "#e6007e"
python "$S" fetch "commons:File:EAC-black-on-white.svg" --out <project>/assets --name eac
```

- Check `references/symbol-map.md` first. It maps common label elements to known-good asset ids,
  so you can often fetch directly without searching.
- Source priority: a matching **dedicated set on Iconify** (consistent style, clean paths) →
  **Wikimedia Commons** (official-looking marks, flags) → **Openverse** (wider art). Details and raw
  API endpoints are in `references/sources.md` (for when the script isn't enough).
- **"Do not" symbols must have a solid, unbroken X.** Many icon sets (including ginetex) knock the
  symbol's lines out around the cross, which leaves gaps. That looks broken on a printed label. Fetch the plain
  symbol with `--cross` instead (`fetch iconify:ginetex:bleaching --cross --name do-not-bleach …`).
  `symbol-map.md` lists the base symbol for each "do not" case.
- Pick **one icon style per design**. Mixing outline and filled icons from different sets looks
  amateur. For a row of care symbols, take all of them from the same set.
- Look before you place: render the candidate (VectorCraft `file.place.info` with `thumbnail`, or
  open the `preview` URL) and confirm it is the right symbol. Search results are fuzzy ("washing" also
  returns car washes).

### 3. Check the licence (the script does the first pass)
`search` drops non-commercial and no-derivatives results; every result has a `license_class`:
- `ok`: CC0, public domain, MIT, Apache, ISC, OFL. Fine for printed products. The manifest keeps the notice.
- `attribute`: CC BY / BY-SA / GPL. Usable only if credit can be given somewhere (website, docs).
  A garment label can't carry credits, so prefer an `ok` alternative and tell the user if you didn't.
- `reject`: not offered unless `--all-licenses`; never place these in deliverables.

Separate from copyright, some symbols are **trademarks / regulated marks**. Read
`references/legal-notes.md` and flag these to the user rather than silently using them:
GINETEX care symbols (licensable trademark in many countries), EAC/CE (the product must actually be
certified), FSC/OEKO-TEX/GOTS (licence-holder only), and other brands' logos (never).

`fetch` writes the sanitised SVG plus a `manifest.json` entry (source, licence, author, URL, date).
Keep the manifest next to the design files and mention it in your summary.

### 4. Place and fit

**VectorCraft (preferred when its MCP is available):**
```
file.place {path, rect: [x, y, w, h]}   → fits inside the box, aspect kept, editable vector group
set_paint {ids: [groupId], fill: {c,m,y,k}}         → recolour to the design's CMYK colour
object.transform / transform                        → fine positioning
symbol.new {ids, name}                              → reuse the same icon many times (one master)
```
- Iconify icons have a 24-unit canvas, often with built-in padding. The visible glyph is smaller than
  `rect`, so check the bounds after placing and align by the visible art, not the box.
- Placed SVGs arrive in RGB. In a CMYK document, recolour them explicitly (K100 for black text and
  symbols, brand CMYK for colour) so print output doesn't get a 4-colour rich black.
- Outline-style icons are filled shapes (the stroke is already expanded), so recolour the *fill*.
- Icon sources come at their own stroke weight. At label sizes, keep visible lines ≥ 0.25 pt for printed
  and ≥ 0.5 pt for woven labels (see `references/print-specs.md`). Pick heavier icon variants if
  needed rather than scaling thin ones down.

**SVG/HTML output (no VectorCraft):** inline each fetched SVG's inner content in a `<g transform=…>`
or `<symbol>` + `<use>`, keep the original `viewBox`, and set `fill` on the group. Size the root
`<svg>` in real units (`width="30mm" height="70mm" viewBox="0 0 85.04 198.43"`).

### 5. Lay out, check, export
- Start from the format's spec in `references/print-specs.md` (sizes, safe margin, bleed, minimum
  type sizes, hang-tag hole, fold lines). Ask for the size if it isn't given and can't be inferred.
- Render a preview at ~5 px/pt (VectorCraft `export` png with `scale: 5`) and look at it: alignment,
  even spacing, nothing within the safe margin, symbols readable at actual size.
- Deliver: the editable file (live text) + print PDF with outlined text + SVG, plus the asset manifest.

### 6. Grow a reusable library
When the user will make many similar pieces, save each placed-and-recoloured asset once
(`<library>/care/…`, `<library>/marks/…`) with the manifest, or save a VectorCraft document whose
symbols are the assets. Next time, place from the library first and search only for what's new.

## What to tell the user
Briefly: what you sourced (and from where, with licence), what you drew by hand and why, anything
uncertain from the photo, any trademark / certification caveat, and the output paths.
