"""Release manifest + Ed25519 signing for the DriveLens toll dataset. Python stdlib + the `openssl` CLI (>= 1.1.1).

Subcommands:
  manifest  --dataset F --out manifest.json --version N --build-date YYYY-MM-DD [--min-app-version N]
  sign      --file manifest.json --out manifest.sig        (private key PEM read from env DRIVELENS_DATA_SIGNING_KEY)
  verify    --file manifest.json --sig manifest.sig --pubkey PUB   (PUB = base64 of the raw 32-byte key, or a PEM path)
  pubkey    (private key from the same env var) prints the base64 raw 32-byte public key

Formats (see KEY-ROTATION.md): manifest.json is canonical JSON (sorted keys, no spaces, trailing newline, UTF-8);
manifest.sig is the RAW 64-byte Ed25519 signature over the exact bytes of manifest.json.
The private key is never written to disk: it is piped to openssl through /dev/stdin.
"""
import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

KEY_ENV = "DRIVELENS_DATA_SIGNING_KEY"
MANIFEST_FORMAT = 1
ED25519_SPKI_PREFIX = bytes.fromhex("302a300506032b6570032100")


def build_manifest(dataset_path, version, build_date, min_app_version=1, file_name="tolls_br.bin.gz"):
    data = Path(dataset_path).read_bytes()
    return {
        "manifestFormat": MANIFEST_FORMAT,
        "version": int(version),
        "buildDate": build_date,
        "file": file_name,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "minAppVersion": int(min_app_version),
    }


def manifest_bytes(manifest):
    return (json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _openssl(args, stdin=None):
    r = subprocess.run(["openssl", *args], input=stdin, capture_output=True, check=False)
    return r.returncode, r.stdout, r.stderr


def sign(message_path, private_pem):
    """Returns the raw 64-byte signature. private_pem: bytes (never touches disk)."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "sig"
        code, _, err = _openssl(["pkeyutl", "-sign", "-inkey", "/dev/stdin", "-rawin", "-in", str(message_path),
                                 "-out", str(out)], stdin=private_pem)
        if code != 0:
            raise RuntimeError("signing failed: " + err.decode(errors="replace").strip())
        sig = out.read_bytes()
    if len(sig) != 64:
        raise RuntimeError("unexpected signature length %d" % len(sig))
    return sig


def public_key_raw(private_pem):
    code, out, err = _openssl(["pkey", "-pubout", "-outform", "DER", "-inform", "PEM"], stdin=private_pem)
    if code != 0 or not out.startswith(ED25519_SPKI_PREFIX) or len(out) != 44:
        raise RuntimeError("not an Ed25519 private key: " + err.decode(errors="replace").strip())
    return out[len(ED25519_SPKI_PREFIX):]


def _pub_pem(raw):
    der = ED25519_SPKI_PREFIX + raw
    b64 = base64.b64encode(der).decode()
    return ("-----BEGIN PUBLIC KEY-----\n" + b64 + "\n-----END PUBLIC KEY-----\n").encode()


def verify(message_path, sig_bytes, pubkey_raw):
    if len(sig_bytes) != 64 or len(pubkey_raw) != 32:
        return False
    with tempfile.TemporaryDirectory() as d:
        sig_file, pub_file = Path(d) / "sig", Path(d) / "pub.pem"
        sig_file.write_bytes(sig_bytes)
        pub_file.write_bytes(_pub_pem(pubkey_raw))
        code, _, _ = _openssl(["pkeyutl", "-verify", "-pubin", "-inkey", str(pub_file), "-rawin", "-in",
                               str(message_path), "-sigfile", str(sig_file)])
    return code == 0


def _load_pubkey(arg):
    if os.path.exists(arg):
        code, out, err = _openssl(["pkey", "-pubin", "-in", arg, "-outform", "DER"])
        if code != 0 or len(out) != 44:
            raise RuntimeError("invalid public key file")
        return out[len(ED25519_SPKI_PREFIX):]
    raw = base64.b64decode(arg, validate=True)
    if len(raw) != 32:
        raise RuntimeError("public key must be 32 raw bytes (base64)")
    return raw


def _private_from_env():
    pem = os.environ.get(KEY_ENV, "")
    if not pem.strip():
        raise RuntimeError("env %s is empty or unset" % KEY_ENV)
    return pem.encode()


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("manifest")
    m.add_argument("--dataset", required=True)
    m.add_argument("--out", required=True)
    m.add_argument("--version", type=int, required=True)
    m.add_argument("--build-date", required=True)
    m.add_argument("--min-app-version", type=int, default=1)
    s = sub.add_parser("sign")
    s.add_argument("--file", required=True)
    s.add_argument("--out", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--file", required=True)
    v.add_argument("--sig", required=True)
    v.add_argument("--pubkey", required=True)
    sub.add_parser("pubkey")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "manifest":
            Path(a.out).write_bytes(manifest_bytes(
                build_manifest(a.dataset, a.version, a.build_date, a.min_app_version)))
        elif a.cmd == "sign":
            Path(a.out).write_bytes(sign(a.file, _private_from_env()))
        elif a.cmd == "verify":
            if not verify(a.file, Path(a.sig).read_bytes(), _load_pubkey(a.pubkey)):
                print("ERROR: invalid signature", file=sys.stderr)
                return 3
            print("OK: signature valid")
        else:
            print(base64.b64encode(public_key_raw(_private_from_env())).decode())
    except (RuntimeError, ValueError, OSError) as e:
        print("ERROR:", e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
