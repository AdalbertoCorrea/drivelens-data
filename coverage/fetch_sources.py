#!/usr/bin/env python3
"""Downloads the public toll sources into a NEW, EMPTY work directory (network step; run by a human).

Sources and licences (record the run date in docs/research/toll-coverage.md):
- ANTT open data, "Praças de pedágio" (federal concessions) - dados.gov.br / dados.antt.gov.br,
  open licence (CC-BY-style; confirm on the dataset page). Pass the CSV resource URL with --antt-url,
  because ANTT changes resource links; the dataset page is listed in README.md.
- OpenStreetMap via Overpass API (ODbL 1.0, (c) OpenStreetMap contributors).
- ARTESP list of SP plazas: no stable machine-readable URL is assumed. Save it by hand as
  artesp.csv (name,uf,lat,lon) in the work dir, or pass --artesp-url if you have one.
"""

import argparse
import urllib.parse
import urllib.request
from pathlib import Path

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_QUERY = """[out:json][timeout:600];
area["ISO3166-1"="BR"][admin_level=2]->.br;
(
  nwr["barrier"="toll_booth"](area.br);
  nwr["highway"="toll_gantry"](area.br);
);
out center tags;"""


def download(req, dest: Path) -> None:
    with urllib.request.urlopen(req, timeout=900) as resp:  # noqa: S310 - https URLs given by the operator
        dest.write_bytes(resp.read())
    print(f"{dest}: {dest.stat().st_size} bytes")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work-dir", type=Path, required=True, help="new, empty directory")
    ap.add_argument("--antt-url", required=True, help="ANTT 'Praças de pedágio' CSV resource URL")
    ap.add_argument("--artesp-url", help="optional URL of an ARTESP plaza CSV")
    args = ap.parse_args()
    args.work_dir.mkdir(parents=True, exist_ok=True)
    ua = {"User-Agent": "DriveLens-tools/1"}
    download(urllib.request.Request(args.antt_url, headers=ua), args.work_dir / "antt.csv")
    body = urllib.parse.urlencode({"data": OVERPASS_QUERY}).encode()
    download(urllib.request.Request(OVERPASS_URL, data=body, headers=ua), args.work_dir / "osm.json")
    if args.artesp_url:
        download(urllib.request.Request(args.artesp_url, headers=ua), args.work_dir / "artesp.csv")


if __name__ == "__main__":
    main()
