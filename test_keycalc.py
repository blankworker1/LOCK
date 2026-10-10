#!/usr/bin/env python3
"""
Checks for keycalc.py. Four kinds of evidence:
  A. each routine against Python's built-in hashlib (a separate implementation)
  B. published test vectors from the BIP32, BIP39 and BIP84 documents
  C. random seeds against the embit library (what SeedSigner, Krux and
     Specter use), if it is installed
  D. the QR code against two other QR programs and a scanner
Run: python3 test_keycalc.py [number_of_random_seeds]
"""
import hashlib, os, sys
import keycalc as k

fails = 0
def check(name, got, want):
    global fails
    ok = got == want
    fails += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    if not ok:
        print(f"       got  {got}\n       want {want}")

print("A. routines against hashlib")
samples = [b"", b"abc", b"a" * 55, b"a" * 56, b"a" * 111, b"a" * 112,
           b"a" * 128, os.urandom(300), os.urandom(1000)]
check("SHA-256", [k.sha256(s) for s in samples], [hashlib.sha256(s).digest() for s in samples])
check("SHA-512", [k.sha512(s) for s in samples], [hashlib.sha512(s).digest() for s in samples])
check("RIPEMD-160", [k.ripemd160(s) for s in samples],
      [hashlib.new("ripemd160", s).digest() for s in samples])
import hmac
keys = [b"k", b"Bitcoin seed", os.urandom(128), os.urandom(200)]
check("HMAC-SHA512", [k.hmac_sha512(q, b"message") for q in keys],
      [hmac.new(q, b"message", hashlib.sha512).digest() for q in keys])
check("PBKDF2 (2048 rounds)", k.pbkdf2_sha512(b"password", b"mnemonicsalt", 2048),
      hashlib.pbkdf2_hmac("sha512", b"password", b"mnemonicsalt", 2048))

print("B. published vectors")
words = k.load_words()
check("word list is the canonical file",
      hashlib.sha256(open(os.path.join(os.path.dirname(os.path.abspath(k.__file__)),
                                       "bip39_english.txt"), "rb").read()).hexdigest(),
      "2f5eed53a4727b4bf8880d8f3f199efc90e58503646d9ff8eff3a2ed3b24dbda")
check("curve: 1*G", k.public_key(1).hex(),
      "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798")
check("curve: 2*G", k.public_key(2).hex(),
      "02c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5")
check("curve: (N-1)*G", k.public_key(k.N - 1).hex(),
      "0379be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798")

def idx(phrase):
    return [words.index(w) for w in phrase.split()]
# BIP39 document vectors (entropy -> last word)
for phrase in ["abandon " * 11 + "about",
               "legal winner thank year wave sausage worth useful legal winner thank yellow",
               "letter advice cage absurd amount doctor acoustic avoid letter advice cage above",
               "zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo wrong",
               "ozone drill grab fiber curtain grace pudding thank cruise elder eight picnic"]:
    i = idx(phrase)
    check(f"BIP39 final word: ...{phrase.split()[-1]}", k.final_word(i[:11], i[11] >> 4), i[11])
check("BIP39 seed ('TREZOR' passphrase)",
      k.pbkdf2_sha512(("abandon " * 11 + "about").encode(), b"mnemonicTREZOR", 2048).hex(),
      "c55257c360c07c72029aebc1b53c05ed0362ada38ead3e3e9efa3708e53495531f09a6987599d18264c1e1c92f2cf141630c7a3c4ab7c81b2f001698e7463b04")
# BIP32 document, test vector 1 (seed 000102...0f), chain m/0'
i = k.hmac_sha512(b"Bitcoin seed", bytes(range(16)))
key, chain = int.from_bytes(i[:32], "big"), i[32:]
m = bytes(9) + chain + k.public_key(key)   # depth 0, no parent, child 0
check("BIP32 vector 1: m", k.base58check(bytes.fromhex("0488B21E") + m),
      "xpub661MyMwAqRbcFtXgS5sYJABqqG9YLmC4Q1Rdap9gSE8NqtwybGhePY2gZ29ESFjqJoCu1Rupje8YtGqsefD265TMg7usUDFdp6W1EGMcet8")
fp = k.ripemd160(k.sha256(k.public_key(key)))[:4]
n = 0x80000000
i = k.hmac_sha512(chain, b"\x00" + key.to_bytes(32, "big") + n.to_bytes(4, "big"))
key, chain = (int.from_bytes(i[:32], "big") + key) % k.N, i[32:]
check("BIP32 vector 1: m/0'",
      k.base58check(bytes.fromhex("0488B21E") + b"\x01" + fp + n.to_bytes(4, "big") + chain + k.public_key(key)),
      "xpub68Gmy5EdvgibQVfPdqkBBCHxA5htiqg55crXYuXoQRKfDBFA1WEjWgP6LHhwBZeNK1VTsfTFUHCdrfp1bgwQ9xv5ski8PX9rL2dZXvgGDnw")
# BIP84 document vector
out = k.account_key(("abandon " * 11 + "about").split())
check("BIP84 account 0 zpub", out["zpub"],
      "zpub6rFR7y4Q2AijBEqTUquhVz398htDFrtymD9xYYfG1m4wAcvPhXNfE3EfH1r1ADqtfSdVCToUG868RvUUkgDKf31mGDtKsAYz2oz2AGutZYs")

print("C. random seeds against embit")
try:
    from embit import bip39, bip32
    from embit.networks import NETWORKS
except ImportError:
    print("  skipped: embit not installed")
else:
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    bad = 0
    for _ in range(count):
        ent = os.urandom(16)
        phrase = bip39.mnemonic_from_bytes(ent).split()
        i = [words.index(w) for w in phrase]
        root = bip32.HDKey.from_seed(bip39.mnemonic_to_seed(" ".join(phrase)))
        acct = root.derive("m/84h/0h/0h").to_public()
        want = (i[11], root.my_fingerprint.hex(),
                acct.to_base58(), acct.to_base58(NETWORKS["main"]["zpub"]))
        got_w = k.final_word(i[:11], i[11] >> 4)
        o = k.account_key(phrase)
        bad += (got_w, o["fingerprint"], o["xpub"], o["zpub"]) != want
    check(f"{count} random seeds: final word, fingerprint, xpub, zpub", bad, 0)

print("D. QR code against two other QR programs and a scanner")
try:
    import qrcode, zxingcpp, numpy
    from qrcodegen import QrCode, QrSegment
except ImportError:
    print("  skipped: needs qrcode, qrcodegen, zxing-cpp, numpy")
else:
    def descriptor():
        fp = os.urandom(4).hex()
        return f"[{fp}/84h/0h/0h]" + k.base58check(bytes.fromhex("04B24746") + os.urandom(74))
    def scan(rows):
        img = numpy.full((49, 49), 255, numpy.uint8)
        img[4:45, 4:45] = (1 - numpy.array(rows, numpy.uint8)) * 255
        found = zxingcpp.read_barcodes(numpy.kron(img, numpy.ones((8, 8), numpy.uint8)))
        return found[0].text if found else None
    texts = ["[73c5da0a/84h/0h/0h]" + out["zpub"]] + [descriptor() for _ in range(30)]
    check("descriptor is always 131 characters", {len(x) for x in texts}, {131})
    same_a = same_b = scanned = 0
    for text in texts:
        segs = [QrSegment.make_bytes(text.encode())]
        for mask in range(8):
            mine = k.qr_rows(text, mask)
            q = qrcode.QRCode(version=6, error_correction=qrcode.constants.ERROR_CORRECT_L,
                              border=0, mask_pattern=mask)
            q.add_data(text, optimize=0); q.make(fit=False)
            same_a += [[int(v) for v in r] for r in q.get_matrix()] == mine
            n = QrCode.encode_segments(segs, QrCode.Ecc.LOW, 6, 6, mask, False)
            same_b += [[int(n.get_module(x, y)) for x in range(41)] for y in range(41)] == mine
        scanned += scan(k.qr_rows(text)) == text
    check("all 8 masks square-for-square identical to python-qrcode", same_a, 8 * len(texts))
    check("all 8 masks square-for-square identical to Nayuki's qrcodegen", same_b, 8 * len(texts))
    check("scanner reads back the exact text", scanned, len(texts))
    # copying slips: flip some squares at random and scan again
    import random
    rng = random.Random(1)
    for slips in (5, 10, 20, 30):
        good = wrong = 0
        for text in texts:
            rows = k.qr_rows(text)
            for _ in range(slips):
                x, y = rng.randrange(9, 41), rng.randrange(9, 32)
                rows[y][x] ^= 1
            got = scan(rows)
            good += got == text
            wrong += got not in (None, text)
        print(f"  info {slips:>2} squares copied wrong: {good}/{len(texts)} still read correctly, "
              f"{wrong} read as a different text")

print("\nALL PASSED" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
