import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import coverage_tool as t  # noqa: E402


def write(dirpath, name, text):
    p = Path(dirpath) / name
    p.write_text(text, encoding="utf-8")
    return str(p)


ANTT = ("Praça;UF;Rodovia;KM;Latitude;Longitude\n"
        "A1;SP;BR-116;10;-23,000;-46,000\n"
        "A2;SP;BR-116;50;-23,500;-46,500\n"
        "B1;MG;BR-381;5;-19,000;-44,000\n"
        "B2;MG;BR-381;9;;\n")


def overpass():
    return json.dumps({"elements": [
        {"type": "node", "id": 1, "lat": -23.0005, "lon": -46.0, "tags": {"barrier": "toll_booth"}},
        {"type": "way", "id": 2, "center": {"lat": -19.0, "lon": -44.0003}, "tags": {"highway": "toll_gantry", "addr:state": "mg"}},
        {"type": "node", "id": 3, "lat": -10.0, "lon": -50.0, "tags": {"barrier": "toll_booth"}},
        {"type": "node", "id": 4, "lat": -23.0, "lon": -46.0, "tags": {"barrier": "gate"}},
    ]})


class Tool(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def test_reads_semicolon_csv_with_accents_and_decimal_comma(self):
        rows = t.read_plazas_csv(write(self.d, "a.csv", ANTT))
        self.assertEqual(4, len(rows))
        self.assertEqual("A1", rows[0]["name"])
        self.assertAlmostEqual(-23.0, rows[0]["lat"])
        self.assertIsNone(rows[3]["lat"])

    def test_osm_keeps_only_toll_tags_and_kinds(self):
        pts = t.read_osm_overpass(write(self.d, "o.json", overpass()))
        self.assertEqual(["BOOTH", "FREE_FLOW", "BOOTH"], [p["kind"] for p in pts])
        self.assertEqual("MG", pts[1]["uf"])
        self.assertEqual(t.UNKNOWN_UF, pts[0]["uf"])

    def test_coverage_by_uf_counts_without_inventing(self):
        antt = t.read_plazas_csv(write(self.d, "a.csv", ANTT))
        osm = t.read_osm_overpass(write(self.d, "o.json", overpass()))
        rows = {r["uf"]: r for r in t.coverage_by_uf(antt, osm)}
        self.assertEqual((2, 1, 1), (rows["SP"]["antt"], rows["SP"]["matched"], rows["SP"]["antt_only"]))
        self.assertEqual(50.0, rows["SP"]["coverage_pct"])
        self.assertEqual(1, rows["MG"]["antt_ungeolocated"])
        self.assertEqual(1, rows["MG"]["matched"])
        self.assertEqual(1, rows[t.UNKNOWN_UF]["osm_only"])
        self.assertIsNone(rows[t.UNKNOWN_UF]["coverage_pct"])

    def test_matching_is_one_to_one(self):
        refs = [{"lat": 0.0, "lon": 0.0}, {"lat": 0.0001, "lon": 0.0}]
        cands = [{"lat": 0.0, "lon": 0.0}]
        self.assertEqual(1, len(t.match(refs, cands)))

    def test_radius_excludes_far_points(self):
        self.assertEqual([], t.match([{"lat": 0.0, "lon": 0.0}], [{"lat": 0.1, "lon": 0.0}], 1500))

    def test_artesp_list_reports_missing_plazas(self):
        antt = t.read_plazas_csv(write(self.d, "a.csv", ANTT))
        osm = t.read_osm_overpass(write(self.d, "o.json", overpass()))
        art = t.read_plazas_csv(write(self.d, "s.csv", "nome,uf,lat,lon\nP1,SP,-23.0,-46.0\nP2,SP,-22.0,-47.0\n"))
        r = t.coverage_against_list(art, antt, osm)
        self.assertEqual((2, 1, ["P2"], 50.0), (r["reference"], r["covered"], r["missing"], r["coverage_pct"]))

    def test_empty_reference_has_no_percentage(self):
        self.assertIsNone(t.coverage_against_list([], [], [])["coverage_pct"])

    def test_markdown_has_row_per_uf_and_nd_for_empty(self):
        md = t.render_markdown([{"uf": "XX", "antt": 0, "osm": 1, "matched": 0, "antt_only": 0,
                                 "osm_only": 1, "antt_ungeolocated": 0, "coverage_pct": None}])
        self.assertIn("| XX | 0 | 1 | 0 | 0 | 1 | 0 | n/d |", md)


if __name__ == "__main__":
    unittest.main()
