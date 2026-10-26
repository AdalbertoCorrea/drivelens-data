import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sign_release  # noqa: E402


def gen_key():
    """Throwaway Ed25519 key, generated in memory for the test only (never committed)."""
    r = subprocess.run(["openssl", "genpkey", "-algorithm", "ed25519"], capture_output=True, check=True)
    return r.stdout


class SignReleaseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.dataset = self.dir / "tolls_br.bin.gz"
        self.dataset.write_bytes(b"dataset-bytes")
        self.key = gen_key()

    def tearDown(self):
        self.tmp.cleanup()

    def make_manifest(self):
        path = self.dir / "manifest.json"
        path.write_bytes(sign_release.manifest_bytes(sign_release.build_manifest(self.dataset, 7, "2026-10-01")))
        return path

    def test_manifest_has_version_date_size_and_sha256(self):
        m = json.loads(self.make_manifest().read_text())
        self.assertEqual(m["version"], 7)
        self.assertEqual(m["buildDate"], "2026-10-01")
        self.assertEqual(m["size"], 13)
        self.assertEqual(m["sha256"], hashlib.sha256(b"dataset-bytes").hexdigest())
        self.assertEqual(m["file"], "tolls_br.bin.gz")

    def test_manifest_is_deterministic(self):
        self.assertEqual(self.make_manifest().read_bytes(), self.make_manifest().read_bytes())

    def test_signature_is_64_raw_bytes_and_verifies(self):
        mf = self.make_manifest()
        sig = sign_release.sign(mf, self.key)
        pub = sign_release.public_key_raw(self.key)
        self.assertEqual(len(sig), 64)
        self.assertEqual(len(pub), 32)
        self.assertTrue(sign_release.verify(mf, sig, pub))

    def test_tampered_manifest_fails_verification(self):
        mf = self.make_manifest()
        sig = sign_release.sign(mf, self.key)
        pub = sign_release.public_key_raw(self.key)
        mf.write_bytes(mf.read_bytes().replace(b'"version":7', b'"version":8'))
        self.assertFalse(sign_release.verify(mf, sig, pub))

    def test_wrong_key_fails_verification(self):
        mf = self.make_manifest()
        sig = sign_release.sign(mf, self.key)
        self.assertFalse(sign_release.verify(mf, sig, sign_release.public_key_raw(gen_key())))

    def test_malformed_signature_or_key_is_rejected(self):
        mf = self.make_manifest()
        pub = sign_release.public_key_raw(self.key)
        self.assertFalse(sign_release.verify(mf, b"short", pub))
        self.assertFalse(sign_release.verify(mf, b"\0" * 64, b"short"))

    def test_cli_roundtrip_reads_private_key_from_env_only(self):
        mf = self.make_manifest()
        sig = self.dir / "manifest.sig"
        os.environ[sign_release.KEY_ENV] = self.key.decode()
        try:
            self.assertEqual(sign_release.main(["sign", "--file", str(mf), "--out", str(sig)]), 0)
            pub_b64 = base64.b64encode(sign_release.public_key_raw(self.key)).decode()
            self.assertEqual(sign_release.main(["verify", "--file", str(mf), "--sig", str(sig),
                                                "--pubkey", pub_b64]), 0)
        finally:
            del os.environ[sign_release.KEY_ENV]
        self.assertNotIn(b"PRIVATE KEY", sig.read_bytes())

    def test_sign_without_env_key_fails(self):
        os.environ.pop(sign_release.KEY_ENV, None)
        self.assertEqual(sign_release.main(["sign", "--file", str(self.make_manifest()),
                                            "--out", str(self.dir / "x.sig")]), 1)

    def test_non_ed25519_key_is_rejected(self):
        rsa = subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048"],
                             capture_output=True, check=True).stdout
        with self.assertRaises(RuntimeError):
            sign_release.public_key_raw(rsa)


if __name__ == "__main__":
    unittest.main()
