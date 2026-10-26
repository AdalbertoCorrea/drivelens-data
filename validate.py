"""Validates tariffs.csv (and points.csv) for the DriveLens toll dataset. Stdlib only."""
import argparse
import csv
import re
import sys
from datetime import date

CATEGORIES = {f"CAT_{i}" for i in range(1, 10)}
KINDS = {"BOOTH", "FREE_FLOW"}
OFFICIAL_URL = re.compile(r"^https://[^\s/]+\.[^\s/]+(/\S*)?$")
SYNTHETIC = "synthetic"
# Category multipliers from spec 007 section 3 (informational; the dataset stores per-category amounts).
MULTIPLIERS = {"CAT_1": 1, "CAT_2": 2, "CAT_3": 1.5, "CAT_4": 3, "CAT_5": 2,
               "CAT_6": 4, "CAT_7": 5, "CAT_8": 6, "CAT_9": 0.5}


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def validate_points(rows):
    errors, seen = [], set()
    for n, r in enumerate(rows, start=2):
        pid = (r.get("point_id") or "").strip()
        where = f"points line {n}"
        if not pid:
            errors.append(f"{where}: empty point_id")
        elif pid in seen:
            errors.append(f"{where}: duplicate point_id {pid}")
        seen.add(pid)
        if (r.get("kind") or "") not in KINDS:
            errors.append(f"{where}: invalid kind")
        try:
            lat, lon = float(r["lat"]), float(r["lon"])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                errors.append(f"{where}: coordinates out of range")
        except (ValueError, KeyError, TypeError):
            errors.append(f"{where}: invalid lat/lon")
        b = (r.get("bearing") or "").strip()
        if b:
            try:
                if not 0 <= int(b) < 360:
                    errors.append(f"{where}: bearing out of range")
            except ValueError:
                errors.append(f"{where}: invalid bearing")
        try:
            if not 1 <= int(r["radius_m"]) <= 200:
                errors.append(f"{where}: radius_m must be 1..200")
        except (ValueError, KeyError, TypeError):
            errors.append(f"{where}: invalid radius_m")
    return errors


def validate_tariffs(rows, point_ids=None):
    """Returns (errors, synthetic_count)."""
    errors, synthetic, keys = [], 0, set()
    for n, r in enumerate(rows, start=2):
        where = f"tariffs line {n}"
        pid = (r.get("point_id") or "").strip()
        if not pid:
            errors.append(f"{where}: empty point_id")
        elif point_ids is not None and pid not in point_ids:
            errors.append(f"{where}: unknown point_id {pid}")
        cat = (r.get("category") or "").strip()
        if cat not in CATEGORIES:
            errors.append(f"{where}: invalid category '{cat}'")
        try:
            date.fromisoformat((r.get("valid_from") or "").strip())
        except ValueError:
            errors.append(f"{where}: missing or invalid valid_from (YYYY-MM-DD)")
        try:
            if int(r.get("amount_cents") or "") <= 0:
                errors.append(f"{where}: amount_cents must be positive")
        except ValueError:
            errors.append(f"{where}: amount_cents is not an integer")
        source = (r.get("source") or "").strip()
        url = (r.get("source_url") or "").strip()
        if source == SYNTHETIC:
            synthetic += 1
        elif source == "official":
            if not OFFICIAL_URL.match(url):
                errors.append(f"{where}: official row needs an https source_url")
        else:
            errors.append(f"{where}: source must be 'official' or 'synthetic'")
        if source != SYNTHETIC and not url:
            errors.append(f"{where}: missing source_url")
        key = (pid, cat, (r.get("valid_from") or "").strip())
        if key in keys:
            errors.append(f"{where}: duplicate (point, category, valid_from)")
        keys.add(key)
    return errors, synthetic


def publishable(rows, synthetic_count):
    """A dataset is publishable only if it has rows and none is synthetic."""
    return bool(rows) and synthetic_count == 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tariffs", default="tariffs.csv")
    ap.add_argument("--points", default="points.csv")
    ap.add_argument("--require-publishable", action="store_true",
                    help="fail when the dataset has synthetic rows or no rows (use for real releases)")
    a = ap.parse_args(argv)
    points = read_csv(a.points)
    tariffs = read_csv(a.tariffs)
    errors = validate_points(points)
    t_err, synth = validate_tariffs(tariffs, {p["point_id"] for p in points})
    errors += t_err
    for e in errors:
        print("ERROR:", e, file=sys.stderr)
    if errors:
        return 1
    if not publishable(tariffs, synth):
        print("NOT PUBLISHABLE: synthetic or empty dataset (development only)", file=sys.stderr)
        if a.require_publishable:
            return 2
    else:
        print("OK: publishable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
