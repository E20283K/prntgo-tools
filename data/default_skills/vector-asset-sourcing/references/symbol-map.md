# Symbol map: common print elements → known-good asset ids

Fetch directly with `python scripts/assets.py fetch <id> --out <dir> [--color "#hex"]`.
The ids were checked against the live APIs on 2026-11-24. If a fetch 404s, run `search` with the plain-English name.

## Care symbols: Iconify set `ginetex` (MIT, 50 icons, one consistent style)
Use this set for every care symbol on a design, so the whole row matches. Note the trademark caveat in
`legal-notes.md`. `python scripts/assets.py search "<words>" --source iconify --prefix ginetex`

| Meaning | id |
|---|---|
| Washing, any (tub) | `iconify:ginetex:washing` |
| 30 °C normal / mild / very mild | `iconify:ginetex:30c-fine-wash` · `…:30c-mild-fine-wash` · `…:30c-very-mild-fine-wash` |
| 40 °C normal / mild / very mild | `iconify:ginetex:40c-coloured-wash` · `…:40c-mild-wash` · `…:40c-very-mild-wash` |
| 60 °C / 60 °C easy care | `iconify:ginetex:60c-coloured-wash` · `…:60c-coloured-wash-easy-care` |
| 70 °C / 95 °C | `iconify:ginetex:70c-boil-wash` · `…:95c-boil-wash` |
| Hand wash (40 °C / ambient) | `iconify:ginetex:hand-wash-at-40c` · `…:hand-wash-ambient-temperature` |
| Do not wash | `iconify:ginetex:washing` **+ `--cross`** (see "Do not" symbols below) |
| Any bleach / oxygen only | `iconify:ginetex:any-bleach-allowed` · `…:only-oxygen-bleach-allowed` |
| Do not bleach | `iconify:ginetex:bleaching` **+ `--cross`** |
| Tumble drying normal / low | `iconify:ginetex:normal-drying-process` · `…:mild-drying-processes` (also `tumble-drying`, `tumble-drying-1`). Check the dots visually: the names are not self-explanatory |
| Natural drying (square) | `iconify:ginetex:natural-drying` · `…:drying` |
| Line / drip-line / flat / drip-flat (± in shade) | `iconify:ginetex:line-drying` · `…:drip-line-drying` · `…:flat-drying` · `…:drip-flat-drying` · add `-in-the-shade` |
| Iron low / moderate / hot / low no steam | `iconify:ginetex:iron-at-low-temperature` · `…:iron-at-moderate-temperature` · `…:hot-iron` · `…:iron-at-low-temperature-without-steam` |
| Do not iron | `iconify:ginetex:ironing` **+ `--cross`** |
| Dry clean P / F | `iconify:ginetex:professional-dry-cleaning-in-perchloroethylene-hydrocarbons-heavy-benzines` (P) · `…:professional-dry-cleaning-in-hydrocarbons-heavy-benzines` (F); `-1` variants = mild process (bar underneath) |
| Do not dry clean | `iconify:ginetex:dry-cleaning` **+ `--cross`** |
| Do not tumble dry | `iconify:ginetex:tumble-drying` **+ `--cross`** |
| Wet cleaning W / mild / very mild | `iconify:ginetex:professional-wet-cleaning` · `…:mild-professional-wet-cleaning` · `…:very-mild-professional-wet-cleaning` |
| Do not wet clean | `iconify:ginetex:professional-wet-cleaning` **+ `--cross`** |

### "Do not" symbols: always plain symbol + `--cross`
The ginetex set draws every crossed-out symbol in a **knockout style**: the symbol's lines are cut away
around the X, leaving visible gaps. The user rejected these on printed labels.
**Never place** `ginetex:do-not-wash`, `do-not-bleach`, `tumble-drying-1`, `do-not-iron`,
`do-not-dry-clean`, `do-not-wet-clean`. Fetch the plain base symbol with `--cross` instead. That adds one
continuous solid X, at the set's own 1.6-unit line weight, as filled shapes so it scales with the art:
```bash
python scripts/assets.py fetch iconify:ginetex:tumble-drying --cross --name do-not-tumble-dry --out <dir>
```
Apply the same rule to any icon set: if a "do not" icon shows gaps where the X crosses the symbol, rebuild it
from the plain symbol plus a solid X. Several ginetex names are vague (`tumble-drying-1` is the crossed dryer),
so render each icon once before relying on its name.

## Conformity / regulatory marks: Wikimedia Commons
| Mark | id | Licence (copyright) | Note |
|---|---|---|---|
| EAC (Eurasian conformity), black | `commons:File:EAC-black-on-white.svg` | CC0 | product must hold EAEU certification |
| CE | `commons:File:Conformité Européenne (logo).svg` | Public domain, *trademarked* | strict proportions; product must comply |
| Recycling (three arrows) | `commons:File:Recycle001.svg` | Public domain | |
| Paper 20 PAP | `commons:File:Recycling Codes Paper 20 PAP.svg` | Public domain | other codes: search "Recycling code <n>" |
| Tidyman (dispose properly) | `commons:File:International tidyman.svg` | Public domain | |
| Fragile / glass, keep dry, this way up | search `"ISO 7000"` or `"IEC 60417"` + meaning | mostly Public domain | packaging handling marks |

## General icons: Iconify (permissive sets)
| Need | Good sets (prefix, licence) | Examples |
|---|---|---|
| UI-style line icons (web, cards) | `tabler` MIT, `lucide` ISC, `ph` MIT, `mdi` Apache-2.0, `material-symbols` Apache-2.0 | `tabler:leaf`, `mdi:hanger`, `mdi:needle`, `mdi:recycle` |
| Flags ("Made in …") | `flag` MIT (rectangular, `-4x3`/`-1x1`), `circle-flags` MIT | `iconify:flag:uz-4x3`, `iconify:circle-flags:uz` |
| Colour illustrations / emoji-style | `fluent-emoji-flat` MIT, `noto` Apache-2.0 | flowers, fruit, animals |
| Avoid for print (attribution needed) | `game-icons` CC-BY-3.0, `twemoji` CC-BY-4.0, `openmoji` CC-BY-SA-4.0, `emojione-monotone` CC-BY-4.0 | use only if the user accepts crediting |

## Decorative art (flowers, ornaments, frames)
1. Iconify, for single motifs in a consistent style: `search "flower" --source iconify --limit 12`, then try
   `ph:flower`, `ph:flower-lotus`, `tabler:flower`, `mdi:flower`, `fluent-emoji-flat:cherry-blossom`.
2. Openverse or Commons, for ornaments, borders and vintage frames:
   `search "floral ornament" --source openverse`, `search "decorative border" --source commons`.
3. Recolour each motif to the design palette after placing. Mixed sources then still look like one system.

## Barcodes / QR codes
Don't search for these. Generate them from the real data, because a barcode picture from the web would scan as somebody
else's product. If VectorCraft has no generator, leave a clearly marked placeholder box of the correct
size (EAN-13 nominal 37.29 × 25.93 mm, min 80 % = 29.83 × 20.74 mm) and tell the user.
