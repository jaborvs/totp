"""Tests for totp. No FIDO2 key needed: the end-to-end tests encrypt to a plain age X25519 key.

Run: python3 -m unittest discover -s tests
"""
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
import urllib.parse
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "totp"


def load_totp():
    loader = importlib.machinery.SourceFileLoader("totp_mod", str(SCRIPT))
    spec = importlib.util.spec_from_loader("totp_mod", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


totp = load_totp()

# RFC 6238 appendix B: the seed is the ASCII string repeated to the hash's key length.
SEEDS = {
    "SHA1": b"12345678901234567890",
    "SHA256": b"12345678901234567890123456789012",
    "SHA512": b"1234567890123456789012345678901234567890123456789012345678901234",
}
RFC_VECTORS = [  # (time, SHA1, SHA256, SHA512), 8 digits, 30 s period
    (59, "94287082", "46119246", "90693936"),
    (1111111109, "07081804", "68084774", "25091201"),
    (1111111111, "14050471", "67062674", "99943326"),
    (1234567890, "89005924", "91819424", "93441116"),
    (2000000000, "69279037", "90698825", "38618901"),
    (20000000000, "65353130", "77737706", "47863826"),
]


def b32(raw):
    import base64
    return base64.b32encode(raw).decode().rstrip("=")


class TestRFC6238(unittest.TestCase):
    def test_reference_vectors(self):
        for t, *codes in RFC_VECTORS:
            for alg, want in zip(("SHA1", "SHA256", "SHA512"), codes):
                p = {"secret": b32(SEEDS[alg]), "digits": 8, "period": 30, "algorithm": alg}
                with self.subTest(t=t, alg=alg):
                    self.assertEqual(totp.totp(p, now=t), want)

    def test_six_digits_keep_leading_zeros(self):
        p = {"secret": b32(SEEDS["SHA1"]), "digits": 6, "period": 30, "algorithm": "SHA1"}
        self.assertEqual(totp.totp(p, now=1111111109), "081804")


class TestParseUri(unittest.TestCase):
    def test_uri_parameters(self):
        uri = f"otpauth://totp/Ex:alice?secret={b32(SEEDS['SHA256'])}&algorithm=sha256&digits=8&period=60"
        _, p = totp.parse_uri(uri)
        self.assertEqual((p["algorithm"], p["digits"], p["period"]), ("SHA256", 8, 60))

    def test_bare_secret_with_spaces_and_lowercase(self):
        uri, p = totp.parse_uri("gezd gnbv-gy3t qojq")
        self.assertEqual(p["secret"], "GEZDGNBVGY3TQOJQ")
        self.assertTrue(uri.startswith("otpauth://totp/"))
        self.assertEqual((p["digits"], p["period"], p["algorithm"]), (6, 30, "SHA1"))

    def test_rejects(self):
        for bad in ("otpauth://hotp/x?secret=GEZDGNBV&counter=0",
                    "otpauth://totp/x?secret=GEZDGNBV&algorithm=MD5",
                    "not-base32-!!!",
                    ""):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                totp.parse_uri(bad)


class TestSafeName(unittest.TestCase):
    def test_slugs(self):
        cases = {
            "Ubuntu One": "ubuntu-one",
            "  GitHub  ": "github",
            "Example:alice@example.com": "example:alice@example.com",
            "a / b": "a-b",
            "Foo : Bar": "foo:bar",
            "../../etc/passwd": "etc-passwd",
        }
        for raw, want in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(totp.safe_name(raw), want)

    def test_path_cannot_escape_store(self):
        self.assertEqual(totp.path_for("../../x").parent, totp.STORE)

    def test_empty(self):
        with self.assertRaises(ValueError):
            totp.safe_name(" / ")


def migration_uri():
    """Google Authenticator export with one TOTP (RFC seed, issuer Example) and one HOTP entry."""
    import base64

    def varint(n):
        out = b""
        while True:
            b, n = n & 0x7F, n >> 7
            if not n:
                return out + bytes([b])
            out += bytes([b | 0x80])

    ld = lambda num, data: varint(num << 3 | 2) + varint(len(data)) + data
    vi = lambda num, v: varint(num << 3) + varint(v)
    otp = ld(1, SEEDS["SHA1"]) + ld(2, b"Example:alice@example.com") + ld(3, b"Example") + vi(4, 1) + vi(5, 1) + vi(6, 2)
    hotp = ld(1, b"\x01\x02") + ld(2, b"hotp") + vi(6, 1)
    data = base64.b64encode(ld(1, otp) + ld(1, hotp) + vi(2, 1)).decode()
    return "otpauth-migration://offline?data=" + urllib.parse.quote(data)


class TestGoogleMigration(unittest.TestCase):
    def test_totp_entry_kept_hotp_skipped(self):
        out = totp.parse_migration(migration_uri())
        self.assertEqual(len(out), 1)
        issuer, account, uri = out[0]
        self.assertEqual((issuer, account), ("Example", "alice@example.com"))
        _, p = totp.parse_uri(uri)
        self.assertEqual(totp.totp(p, now=59), "287082")  # RFC SHA1 vector, 6 digits


@unittest.skipUnless(shutil.which("age") and shutil.which("age-keygen"), "age not installed")
class TestEndToEnd(unittest.TestCase):
    """Real CLI with isolated XDG dirs; the recipient is an age X25519 key instead of the FIDO2 one."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.env = {**os.environ, "XDG_CONFIG_HOME": str(self.tmp / "config"),
                    "XDG_DATA_HOME": str(self.tmp / "data"), "XDG_RUNTIME_DIR": str(self.tmp / "run")}
        (self.tmp / "run").mkdir()
        conf = self.tmp / "config/totp"
        conf.mkdir(parents=True)
        key = self.tmp / "key.txt"
        subprocess.run(["age-keygen", "-o", str(key)], capture_output=True, check=True)
        pub = subprocess.run(["age-keygen", "-y", str(key)], capture_output=True, text=True, check=True).stdout
        (conf / "recipient").write_text(pub)
        (conf / "identity").write_text(key.read_text())  # decrypt uses -i identity when it exists

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_totp(self, *args, stdin=""):
        return subprocess.run([str(SCRIPT), *args], input=stdin, capture_output=True, text=True, env=self.env)

    def test_add_list_code_rm(self):
        secret = b32(SEEDS["SHA1"])
        r = self.run_totp("add", "My Bank", secret)
        self.assertEqual(r.returncode, 0, r.stderr)
        stored = self.tmp / "data/totp/my-bank.age"
        self.assertTrue(stored.exists())
        self.assertNotIn(secret.encode(), stored.read_bytes())
        self.assertEqual(stored.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.run_totp("list").stdout.split(), ["my-bank"])

        code = self.run_totp("code", "my-bank")
        self.assertEqual(code.returncode, 0, code.stderr)
        _, p = totp.parse_uri(secret)
        self.assertIn(code.stdout.strip(), {totp.totp(p), totp.totp(p, now=__import__("time").time() - 30)})

        self.assertNotEqual(self.run_totp("add", "my-bank", secret).returncode, 0)  # no silent overwrite
        self.assertEqual(self.run_totp("add", "my-bank", secret, "--force").returncode, 0)

        self.assertEqual(self.run_totp("rm", "my-bank").returncode, 0)
        self.assertEqual(self.run_totp("list").stdout.strip(), "")

    def test_add_from_stdin(self):
        r = self.run_totp("add", "piped", stdin=f"otpauth://totp/x?secret={b32(SEEDS['SHA1'])}\n")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_errors(self):
        self.assertIn("no such account", self.run_totp("code", "missing").stderr)
        self.assertNotEqual(self.run_totp("add", "bad", "otpauth://hotp/x?secret=GEZDGNBV").returncode, 0)
        (self.tmp / "config/totp/recipient").unlink()
        self.assertIn("totp init", self.run_totp("add", "x", b32(SEEDS["SHA1"])).stderr)


if __name__ == "__main__":
    unittest.main()
