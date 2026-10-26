"""Toll-plaza coverage survey (T-TOL-001). Pure stdlib, offline-testable.

Cross-checks ANTT plazas (open data CSV) against OSM toll nodes (Overpass JSON) and, for SP,
against an ARTESP plaza list. Never invents data: it only counts what the inputs contain.
"""

import csv
import json
import math
import unicodedata

DEFAULT_RADIUS_M = 1500.0
UNKNOWN_UF = "??"

ALIASES = {
    "name": ("praca", "praça", "nome", "nome_praca", "name", "praca_pedagio"),
    "uf": ("uf", "estado", "sigla_uf"),
    "highway": ("rodovia", "br", "highway", "via"),
    "km": ("km", "quilometro"),
    "lat": ("latitude", "lat"),
    "lon": ("longitude", "lon", "lng", "long"),
}


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return s.strip().lower().replace(" ", "_")


def _num(v):
    try:
        return float(str(v).strip().replace(",", "."))
    except ValueError:
        return None


def haversine_m(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(h))


def read_plazas_csv(path, delimiter=None):
    """Reads a plaza CSV with tolerant header names; rows without valid lat/lon are kept
    with lat/lon None (they count as 'ungeolocated', never matched)."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        sample = f.read(4096)
        f.seek(0)
        if delimiter is None:
            delimiter = ";" if sample.count(";") > sample.count(",") else ","
        reader = csv.DictReader(f, delimiter=delimiter)
        cols = {_norm(c): c for c in (reader.fieldnames or [])}
        pick = {k: next((cols[_norm(a)] for a in v if _norm(a) in cols), None) for k, v in ALIASES.items()}
        out = []
        for row in reader:
            g = lambda k: (row.get(pick[k]) or "").strip() if pick[k] else ""  # noqa: E731
            out.append({
                "name": g("name"), "uf": g("uf").upper() or UNKNOWN_UF, "highway": g("highway"),
                "km": g("km"), "lat": _num(g("lat")), "lon": _num(g("lon")),
            })
        return out


def read_osm_overpass(path):
    """Overpass JSON (out center) -> toll points. Keeps barrier=toll_booth and highway=toll_gantry."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        kind = "BOOTH" if tags.get("barrier") == "toll_booth" else (
            "FREE_FLOW" if tags.get("highway") == "toll_gantry" else None)
        if kind is None:
            continue
        lat = el.get("lat", (el.get("center") or {}).get("lat"))
        lon = el.get("lon", (el.get("center") or {}).get("lon"))
        uf = (tags.get("addr:state") or tags.get("is_in:state_code") or "").upper()
        out.append({"name": tags.get("name", ""), "uf": uf if len(uf) == 2 else UNKNOWN_UF,
                    "kind": kind, "lat": lat, "lon": lon, "osm_id": f'{el.get("type", "")}/{el.get("id", "")}'})
    return out


def _geo(items):
    return [i for i in items if i["lat"] is not None and i["lon"] is not None]


def match(refs, cands, radius_m=DEFAULT_RADIUS_M):
    """Greedy one-to-one nearest matching (closest pairs first). Returns list of (ref_idx, cand_idx, dist)."""
    pairs = []
    for i, r in enumerate(refs):
        if r["lat"] is None or r["lon"] is None:
            continue
        for j, c in enumerate(cands):
            if c["lat"] is None or c["lon"] is None:
                continue
            d = haversine_m((r["lat"], r["lon"]), (c["lat"], c["lon"]))
            if d <= radius_m:
                pairs.append((d, i, j))
    pairs.sort()
    used_r, used_c, out = set(), set(), []
    for d, i, j in pairs:
        if i in used_r or j in used_c:
            continue
        used_r.add(i)
        used_c.add(j)
        out.append((i, j, d))
    return out


def coverage_by_uf(antt, osm, radius_m=DEFAULT_RADIUS_M):
    """Per-UF counts. coverage_pct = matched / antt_total (None when the UF has no ANTT plaza)."""
    m = match(antt, osm, radius_m)
    matched_antt = {i for i, _, _ in m}
    matched_osm = {j for _, j, _ in m}
    rows = {}

    def row(uf):
        return rows.setdefault(uf, {"uf": uf, "antt": 0, "osm": 0, "matched": 0,
                                    "antt_only": 0, "osm_only": 0, "antt_ungeolocated": 0})
    for i, a in enumerate(antt):
        r = row(a["uf"])
        r["antt"] += 1
        if a["lat"] is None or a["lon"] is None:
            r["antt_ungeolocated"] += 1
        if i in matched_antt:
            r["matched"] += 1
        else:
            r["antt_only"] += 1
    for j, o in enumerate(osm):
        uf = o["uf"]
        if uf == UNKNOWN_UF:  # inherit the UF of the matched ANTT plaza, else stay unknown
            uf = next((antt[i]["uf"] for i, jj, _ in m if jj == j), UNKNOWN_UF)
        r = row(uf)
        r["osm"] += 1
        if j not in matched_osm:
            r["osm_only"] += 1
    for r in rows.values():
        r["coverage_pct"] = None if r["antt"] == 0 else round(100.0 * r["matched"] / r["antt"], 1)
    return [rows[k] for k in sorted(rows)]


def coverage_against_list(reference, antt, osm, radius_m=DEFAULT_RADIUS_M):
    """How many plazas of an official list (e.g. ARTESP) have an ANTT or OSM point nearby."""
    union = _geo(antt) + _geo(osm)
    m = match(reference, union, radius_m)
    hit = {i for i, _, _ in m}
    missing = [r["name"] or f"#{i}" for i, r in enumerate(reference) if i not in hit]
    n = len(reference)
    return {"reference": n, "covered": len(hit), "missing": missing,
            "coverage_pct": None if n == 0 else round(100.0 * len(hit) / n, 1)}


def render_markdown(rows, sp=None, meta=None):
    L = ["# Resultado do levantamento", ""]
    for k, v in (meta or {}).items():
        L.append(f"- {k}: {v}")
    L += ["", "| UF | ANTT | OSM | Cruzadas | Só ANTT | Só OSM | Sem coordenadas | Cobertura (cruzadas/ANTT) |",
          "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        pct = "n/d" if r["coverage_pct"] is None else f'{r["coverage_pct"]}%'
        L.append(f'| {r["uf"]} | {r["antt"]} | {r["osm"]} | {r["matched"]} | {r["antt_only"]} | '
                 f'{r["osm_only"]} | {r["antt_ungeolocated"]} | {pct} |')
    if sp is not None:
        pct = "n/d" if sp["coverage_pct"] is None else f'{sp["coverage_pct"]}%'
        L += ["", f'## SP contra a lista da ARTESP: {sp["covered"]}/{sp["reference"]} ({pct})', "",
              "Praças da ARTESP sem ponto na base:"]
        L += [f"- {n}" for n in sp["missing"]] or ["- (nenhuma)"]
    return "\n".join(L) + "\n"
