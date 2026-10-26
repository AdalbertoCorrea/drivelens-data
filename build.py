"""Builds tolls_br.bin.gz from points.csv + tariffs.csv. Deterministic. Stdlib only.

Layout (big-endian), documented in FORMAT.md:
 header: magic 'DLTL', u16 formatVersion(1), u16 flags (bit0 = synthetic/not publishable),
         u32 datasetVersion, u32 buildDateDays, u32 pointCount, u32 tariffCount, u32 stringCount
 strings: stringCount x (u16 len, utf8)         [deduplicated, sorted]
 points:  pointCount x (u32 id, u32 plazaStr, u32 concStr, u32 hwyStr, u32 kmMeters, u32 ufStr,
                        u8 kind(0 BOOTH,1 FREE_FLOW), i32 latE7, i32 lonE7, u16 bearing(0xFFFF=both), u16 radiusM)
 tariffs: tariffCount x (u32 pointId, u8 category(1..9), u32 validFromDays, u32 cents)
"""
import argparse
import gzip
import struct
import sys
from datetime import date

import validate

MAGIC = b"DLTL"
FORMAT_VERSION = 1
FLAG_SYNTHETIC = 1
EPOCH = date(1970, 1, 1)


def days(iso):
    return (date.fromisoformat(iso) - EPOCH).days


def build(points, tariffs, version, build_date):
    """Returns (gz_bytes, flags). Raises ValueError on invalid input."""
    errors = validate.validate_points(points)
    ids = {p["point_id"] for p in points}
    t_err, synth = validate.validate_tariffs(tariffs, ids)
    errors += t_err
    if errors:
        raise ValueError("; ".join(errors))
    flags = FLAG_SYNTHETIC if synth > 0 or not tariffs else 0
    ordered = sorted(points, key=lambda p: p["point_id"])
    numeric = {p["point_id"]: i + 1 for i, p in enumerate(ordered)}
    strings = sorted({s for p in ordered for s in (p["plaza"], p["concessionaire"], p["highway"], p["uf"])})
    sidx = {s: i for i, s in enumerate(strings)}
    ts = sorted(tariffs, key=lambda t: (numeric[t["point_id"]], t["category"], t["valid_from"]))
    out = bytearray(MAGIC)
    out += struct.pack(">HHIIIII", FORMAT_VERSION, flags, version, days(build_date),
                       len(ordered), len(ts), len(strings))
    for s in strings:
        b = s.encode("utf-8")
        out += struct.pack(">H", len(b)) + b
    for p in ordered:
        bearing = int(p["bearing"]) if (p.get("bearing") or "").strip() else 0xFFFF
        out += struct.pack(">IIIIIIBiiHH", numeric[p["point_id"]], sidx[p["plaza"]], sidx[p["concessionaire"]],
                           sidx[p["highway"]], round(float(p["km"]) * 1000), sidx[p["uf"]],
                           0 if p["kind"] == "BOOTH" else 1, round(float(p["lat"]) * 1e7),
                           round(float(p["lon"]) * 1e7), bearing, int(p["radius_m"]))
    for t in ts:
        out += struct.pack(">IBII", numeric[t["point_id"]], int(t["category"][4:]),
                           days(t["valid_from"]), int(t["amount_cents"]))
    return gzip.compress(bytes(out), compresslevel=9, mtime=0), flags


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--points", default="points.csv")
    ap.add_argument("--tariffs", default="tariffs.csv")
    ap.add_argument("--out", default="tolls_br.bin.gz")
    ap.add_argument("--version", type=int, required=True)
    ap.add_argument("--build-date", required=True, help="YYYY-MM-DD (explicit, for reproducibility)")
    ap.add_argument("--require-publishable", action="store_true")
    a = ap.parse_args(argv)
    try:
        data, flags = build(validate.read_csv(a.points), validate.read_csv(a.tariffs), a.version, a.build_date)
    except ValueError as e:
        print("ERROR:", e, file=sys.stderr)
        return 1
    if flags & FLAG_SYNTHETIC:
        print("WARNING: synthetic/empty dataset, flagged NOT PUBLISHABLE", file=sys.stderr)
        if a.require_publishable:
            return 2
    with open(a.out, "wb") as f:
        f.write(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
