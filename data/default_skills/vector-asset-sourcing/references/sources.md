# Asset sources: raw API reference

`scripts/assets.py` wraps all of this. Read this only to do something the script doesn't.
Send a generic User-Agent (never the user's name or e-mail). All are free and need no API key for light use.

## Iconify: https://api.iconify.design
200k+ icons in 150+ open-source sets. Each **set** has one licence. Check it per set, not per icon.
IconStash (iconstash.com), icones.js.org and icon-sets.iconify.design are browsing UIs over this same API.

| Call | Purpose |
|---|---|
| `GET /search?query=<q>&limit=<32..999>[&prefixes=a,b][&palette=false]` | → `{"icons": ["prefix:name", …]}` |
| `GET /collections?prefixes=a,b` | set metadata: `name`, `license.spdx`, `author`, `palette`, `height` |
| `GET /collections` | every set (use for theme discovery) |
| `GET /collection?prefix=<p>` | all icon names in a set, grouped by `categories` |
| `GET /<prefix>/<name>.svg[?color=%23hex][&height=none][&rotate=90deg][&flip=horizontal]` | the SVG; `color` replaces `currentColor` (monochrome sets only) |

`palette: true` means multicolour (emoji-style), and `?color` won't recolour it.

## Wikimedia Commons: https://commons.wikimedia.org/w/api.php
Best for official-looking marks, flags, standard pictograms (ISO 7000, IEC 60417) and recycling codes.
Search SVG files:
```
action=query&format=json&generator=search&gsrnamespace=6&gsrsearch=<q> filetype:svg&gsrlimit=10
&prop=imageinfo&iiprop=url|mime|extmetadata
&iiextmetadatafilter=LicenseShortName|Artist|AttributionRequired|Restrictions|ImageDescription
```
- `extmetadata.LicenseShortName`: "CC0", "Public domain", "CC BY-SA 4.0" …
- `extmetadata.Restrictions`: e.g. `trademarked`, `insignia`, `personality`. **Surface this to the user.**
- File URL: `imageinfo[0].url` (upload.wikimedia.org). Strip the `?utm_…` query string.

## Openverse: https://api.openverse.org/v1/images/
Aggregates openly licensed media (Wikimedia, Flickr, museums …). Anonymous limit ≈ 100 requests/day, 5/hour burst.
```
GET /v1/images/?q=<q>&extension=svg&license_type=commercial&page_size=20
GET /v1/images/<uuid>/
```
Fields: `url` (file), `license` (`cc0`, `pdm`, `by`, `by-sa` …), `license_version`, `creator`,
`foreign_landing_url`, `attribution` (a ready-made credit line), `provider`.
`license_type=commercial` already removes NC licences. ND can still appear, and the script rejects it.

## Other places (manual, check licence on each)
- **SVG Repo** (svgrepo.com): large, mixed licences per icon. Read the licence line on each page.
- **Google Fonts** (fonts.google.com): OFL/Apache fonts for live text; Cyrillic subset filter.
- **The Noun Project / Flaticon**: attribution or paid licence. Don't use without the user's account and licence.
