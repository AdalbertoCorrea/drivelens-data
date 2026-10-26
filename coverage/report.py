#!/usr/bin/env python3
"""Cross ANTT x OSM (x ARTESP) and write the per-UF coverage report (Markdown)."""

import argparse
from pathlib import Path

import coverage_tool as t


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--antt", required=True)
    ap.add_argument("--osm", required=True)
    ap.add_argument("--artesp")
    ap.add_argument("--radius-m", type=float, default=t.DEFAULT_RADIUS_M)
    ap.add_argument("--run-date", required=True, help="yyyy-mm-dd of the download")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    antt, osm = t.read_plazas_csv(a.antt), t.read_osm_overpass(a.osm)
    rows = t.coverage_by_uf(antt, osm, a.radius_m)
    sp = None
    if a.artesp:
        sp = t.coverage_against_list(t.read_plazas_csv(a.artesp), antt, osm, a.radius_m)
    meta = {"Data da coleta": a.run_date, "Raio de cruzamento (m)": a.radius_m,
            "Praças ANTT lidas": len(antt), "Pontos OSM lidos": len(osm)}
    a.out.write_text(t.render_markdown(rows, sp, meta), encoding="utf-8")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
