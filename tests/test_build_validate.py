import gzip
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build  # noqa: E402
import validate  # noqa: E402

PTS = [
    {"point_id": "P2", "plaza": "Z2", "concessionaire": "C", "highway": "BR-1", "km": "5.5", "uf": "SP",
     "kind": "FREE_FLOW", "lat": "-10.5", "lon": "-50.25", "bearing": "90", "radius_m": "80"},
    {"point_id": "P1", "plaza": "Z1", "concessionaire": "C", "highway": "BR-1", "km": "1", "uf": "SP",
     "kind": "BOOTH", "lat": "-10", "lon": "-50", "bearing": "", "radius_m": "60"},
]


def row(**kw):
    r = {"point_id": "P1", "category": "CAT_1", "valid_from": "2026-01-01", "amount_cents": "1000",
         "source_url": "https://example.gov.br/tarifas", "source": "official"}
    r.update(kw)
    return r


class ValidateTest(unittest.TestCase):
    def errs(self, **kw):
        return validate.validate_tariffs([row(**kw)], {"P1"})[0]

    def test_accepts_valid_official_row(self):
        self.assertEqual(self.errs(), [])

    def test_rejects_missing_source_url(self):
        self.assertTrue(self.errs(source_url=""))

    def test_rejects_non_https_source(self):
        self.assertTrue(self.errs(source_url="http://x.gov.br"))

    def test_rejects_missing_validity(self):
        self.assertTrue(self.errs(valid_from=""))

    def test_rejects_bad_category(self):
        self.assertTrue(self.errs(category="CAT_10"))

    def test_rejects_non_positive_amount(self):
        self.assertTrue(self.errs(amount_cents="0"))
        self.assertTrue(self.errs(amount_cents="-5"))

    def test_rejects_unknown_point_and_duplicates(self):
        self.assertTrue(self.errs(point_id="X"))
        e, _ = validate.validate_tariffs([row(), row()], {"P1"})
        self.assertTrue(e)

    def test_synthetic_is_not_publishable(self):
        rows = [row(source="synthetic", source_url="synthetic:dev-only")]
        e, s = validate.validate_tariffs(rows, {"P1"})
        self.assertEqual(e, [])
        self.assertFalse(validate.publishable(rows, s))
        self.assertFalse(validate.publishable([], 0))
        self.assertTrue(validate.publishable([row()], 0))


class BuildTest(unittest.TestCase):
    def test_is_reproducible_and_flags_synthetic(self):
        t = [row(source="synthetic", source_url="synthetic:dev-only")]
        a, fa = build.build(PTS, t, 1, "2026-05-01")
        b, _ = build.build(list(reversed(PTS)), t, 1, "2026-05-01")
        self.assertEqual(a, b)
        self.assertTrue(fa & build.FLAG_SYNTHETIC)

    def test_layout_and_publishable_flag(self):
        t = [row(point_id="P2", category="CAT_9", amount_cents="250")]
        data, flags = build.build(PTS, t, 7, "1970-01-11")
        self.assertEqual(flags, 0)
        raw = gzip.decompress(data)
        self.assertEqual(raw[:4], b"DLTL")
        fmt, fl, ver, day, npts, ntar, nstr = struct.unpack(">HHIIIII", raw[4:28])
        self.assertEqual((fmt, fl, ver, day, npts, ntar), (1, 0, 7, 10, 2, 1))
        self.assertEqual(nstr, 5)
        cents = struct.unpack(">IBII", raw[-13:])
        self.assertEqual(cents[1:], (9, 20454, 250))
        self.assertEqual(cents[0], 2)

    def test_invalid_input_raises(self):
        with self.assertRaises(ValueError):
            build.build(PTS, [row(amount_cents="0")], 1, "2026-05-01")

    def test_cli_require_publishable_rejects_synthetic(self):
        with tempfile.TemporaryDirectory() as d:
            here = Path(__file__).resolve().parents[1]
            rc = build.main(["--points", str(here / "points.csv"), "--tariffs", str(here / "tariffs.csv"),
                             "--out", str(Path(d) / "o.gz"), "--version", "1", "--build-date", "2026-05-01",
                             "--require-publishable"])
            self.assertEqual(rc, 2)
            self.assertFalse((Path(d) / "o.gz").exists())
            rc = build.main(["--points", str(here / "points.csv"), "--tariffs", str(here / "tariffs.csv"),
                             "--out", str(Path(d) / "o.gz"), "--version", "1", "--build-date", "2026-05-01"])
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
