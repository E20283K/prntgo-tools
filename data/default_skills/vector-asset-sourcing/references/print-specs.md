# Print specs by format

Units: 1 mm = 2.8346 pt. VectorCraft coordinates are pt with y down. Create documents with
`file.new {width: "30 mm", height: "70 mm", units: "Millimeters", colorMode: "cmyk", rasterEffectsPpi: 300}`.
Use CMYK; black text and symbols as K100 (not rich black); brand colours as CMYK (ask for Pantone if they have it).

## Contents
1. Sewn-in labels (printed satin / woven)
2. Hang tags
3. Packaging stickers
4. Business cards and flyers
5. Minimums

## 1. Sewn-in labels
| Type | Common sizes (w × h) | Notes |
|---|---|---|
| Brand / size label (neck) | 30×70, 25×60, 40×60, 50×20 (size tab 15×15) mm | often folded: center-fold adds 2 × sewing allowance at top and bottom |
| Care / composition label | 30×70, 30×100, 35×80, 40×120 mm | may be multi-page (front/back); long labels are fine |
| Sewing allowance | 5–8 mm at the sewn edge(s) | keep text out of it; ask whether it's a flat, centre-fold or end-fold label |
- **Safe margin:** 2.5–3 mm from cut edges (satin edges fray; ultrasonic cut is cleaner).
- **Printed satin / nylon:** 1–2 spot colours usually; min text 5 pt; min line 0.25 pt.
- **Woven (damask/taffeta):** thread resolution, so min text ≈ 6 pt bold-ish, min line 0.5 pt, avoid hairline
  serifs and tiny counters, max ~8 thread colours, no gradients. Simplify icons (heavier variants).
- Usual content order (EAEU / Uzbekistan market): brand → product name → size → composition → certification mark →
  care symbols → manufacturer / address → date of manufacture → article number → country of origin. Russian/Uzbek text
  needs a font with full Cyrillic (incl. Ўў Ққ Ғғ Ҳҳ for Uzbek Cyrillic).

## 2. Hang tags
| Item | Typical |
|---|---|
| Sizes | 50×90, 55×85, 40×80, 60×100 mm; also 50×50 square, Ø 60 round |
| Hole | Ø 4–5 mm, centre 6–8 mm from the top edge (or a corner), with nothing printed within 3 mm of it |
| Bleed | 3 mm on every edge (art for background colour/images extends past the trim) |
| Safe margin | 3–4 mm inside trim |
| Sides | front (brand, mood) + back (price/size/barcode/composition/care/manufacturer) as two artboards |
| Barcode area | EAN-13 ≥ 29.8×20.7 mm incl. quiet zones, dark bars on light ground |
| Card stock | 300–400 gsm. Fine lines ≥ 0.25 pt, reversed (white) text ≥ 6 pt |
Draw the die-line (trim + hole) on its own layer named `Die-line` with a 100 % spot colour stroke, non-printing.

## 3. Packaging stickers
| Item | Typical |
|---|---|
| Sizes | Ø 30/40/50 mm round, 40×60, 50×30, 70×40, 100×70 mm |
| Bleed / safe | 2 mm bleed, 2 mm safe margin; die-cut shape on its own `Die-line` layer |
| Content | product, weight/size, composition, manufacturer, date, barcode, handling marks (recycling, tidyman) |

## 4. Business cards and flyers
| Item | Size | Bleed | Safe |
|---|---|---|---|
| Business card | 90×50 mm (CIS/EU), 85×55 mm (EU alt), 3.5×2 in (US) | 2–3 mm | 4 mm |
| Flyer | A6 105×148, A5 148×210, A4 210×297 mm | 3 mm | 5 mm |

## 5. Minimums (summary)
| | Offset / digital | Printed satin | Woven |
|---|---|---|---|
| Body text | 6 pt | 5 pt | 6–7 pt |
| Line weight | 0.25 pt | 0.25 pt | 0.5 pt |
| Care symbol height | 4 mm | 4 mm | 5 mm |
| EAC / CE height | ≥ 5 mm | ≥ 5 mm | ≥ 5 mm |
