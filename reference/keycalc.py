#!/usr/bin/env python3
"""
keycalc.py - plain reference for the transparent key calculator.

Job: take a hand-made seed (11 words + 7 coin-flip bits, or 12 words) and
produce the two things a machine is needed for:
  1. the 12th (checksum) word
  2. the account public key (xpub/zpub) at m/84'/0'/0'
  3. that key as a QR code, 41 rows of 41 squares, for copying by hand

Everything is written out from first principles, with no imports beyond the
standard library's integer maths, so that each routine can be translated
one-for-one to a small 8-bit machine and checked against this file.

WARNING: this is a reference for TEST VECTORS ONLY. Never type a real seed
into a general-purpose, networked computer.
"""
import math
import sys
import unicodedata

# Counters: how many times each expensive building block ran.
COUNT = {"sha256": 0, "sha512": 0, "ripemd160": 0,
         "field_mul": 0, "field_sqr": 0, "curve_mult": 0}

# ---------------------------------------------------------------- constants
def _primes(n):
    out, c = [], 2
    while len(out) < n:
        if all(c % p for p in out):
            out.append(c)
        c += 1
    return out

def _icbrt(n):
    x = 1 << ((n.bit_length() + 2) // 3)
    while True:
        y = (2 * x + n // (x * x)) // 3
        if y >= x:
            return x
        x = y

# SHA constants are not magic numbers: they are the fractional parts of the
# square and cube roots of the first primes. Derived here, not typed in.
_P = _primes(80)
M32, M64 = (1 << 32) - 1, (1 << 64) - 1
H256 = [math.isqrt(p << 64) & M32 for p in _P[:8]]
K256 = [_icbrt(p << 96) & M32 for p in _P[:64]]
H512 = [math.isqrt(p << 128) & M64 for p in _P[:8]]
K512 = [_icbrt(p << 192) & M64 for p in _P[:80]]

# ------------------------------------------------------------------ SHA-2
def _rotr(x, n, bits):
    return ((x >> n) | (x << (bits - n))) & ((1 << bits) - 1)

def _compress(state, block, bits):
    """One SHA-256 (bits=32) or SHA-512 (bits=64) compression."""
    if bits == 32:
        COUNT["sha256"] += 1
        K, mask, wb, rounds = K256, M32, 4, 64
        r = (2, 13, 22, 6, 11, 25, 7, 18, 3, 17, 19, 10)
    else:
        COUNT["sha512"] += 1
        K, mask, wb, rounds = K512, M64, 8, 80
        r = (28, 34, 39, 14, 18, 41, 1, 8, 7, 19, 61, 6)
    w = [int.from_bytes(block[i * wb:(i + 1) * wb], "big") for i in range(16)]
    for i in range(16, rounds):
        s0 = _rotr(w[i-15], r[6], bits) ^ _rotr(w[i-15], r[7], bits) ^ (w[i-15] >> r[8])
        s1 = _rotr(w[i-2], r[9], bits) ^ _rotr(w[i-2], r[10], bits) ^ (w[i-2] >> r[11])
        w.append((w[i-16] + s0 + w[i-7] + s1) & mask)
    a, b, c, d, e, f, g, h = state
    for i in range(rounds):
        S1 = _rotr(e, r[3], bits) ^ _rotr(e, r[4], bits) ^ _rotr(e, r[5], bits)
        ch = (e & f) ^ (~e & mask & g)
        t1 = (h + S1 + ch + K[i] + w[i]) & mask
        S0 = _rotr(a, r[0], bits) ^ _rotr(a, r[1], bits) ^ _rotr(a, r[2], bits)
        maj = (a & b) ^ (a & c) ^ (b & c)
        t2 = (S0 + maj) & mask
        a, b, c, d, e, f, g, h = (t1 + t2) & mask, a, b, c, (d + t1) & mask, e, f, g
    return [(x + y) & mask for x, y in zip(state, (a, b, c, d, e, f, g, h))]

def _sha2(data, bits, state=None, prior_len=0):
    """Hash `data`, optionally continuing from a saved state (used by HMAC)."""
    wb = bits // 8
    blk = 16 * wb
    state = list(state or (H256 if bits == 32 else H512))
    total = (prior_len + len(data)) * 8
    data = data + b"\x80"
    data += b"\x00" * ((-len(data) - 2 * wb) % blk) + total.to_bytes(2 * wb, "big")
    for i in range(0, len(data), blk):
        state = _compress(state, data[i:i + blk], bits)
    return b"".join(x.to_bytes(wb, "big") for x in state)

def sha256(data):
    return _sha2(data, 32)

def sha512(data):
    return _sha2(data, 64)

# -------------------------------------------------------------- HMAC, PBKDF2
def _hmac512_pads(key):
    """The two pad states. Computed once per key, then reused."""
    if len(key) > 128:
        key = sha512(key)
    key = key + b"\x00" * (128 - len(key))
    inner = _compress(H512, bytes(k ^ 0x36 for k in key), 64)
    outer = _compress(H512, bytes(k ^ 0x5C for k in key), 64)
    return inner, outer

def _hmac512_with(pads, msg):
    inner, outer = pads
    return _sha2(_sha2(msg, 64, inner, 128), 64, outer, 128)

def hmac_sha512(key, msg):
    return _hmac512_with(_hmac512_pads(key), msg)

def pbkdf2_sha512(password, salt, rounds):
    """One 64-byte output block: all that BIP39 needs."""
    pads = _hmac512_pads(password)
    u = _hmac512_with(pads, salt + b"\x00\x00\x00\x01")
    out = int.from_bytes(u, "big")
    for _ in range(rounds - 1):
        u = _hmac512_with(pads, u)
        out ^= int.from_bytes(u, "big")
    return out.to_bytes(64, "big")

# -------------------------------------------------------------- RIPEMD-160
_RL = [list(range(16)),
       [7, 4, 13, 1, 10, 6, 15, 3, 12, 0, 9, 5, 2, 14, 11, 8],
       [3, 10, 14, 4, 9, 15, 8, 1, 2, 7, 0, 6, 13, 11, 5, 12],
       [1, 9, 11, 10, 0, 8, 12, 4, 13, 3, 7, 15, 14, 5, 6, 2],
       [4, 0, 5, 9, 7, 12, 2, 10, 14, 1, 3, 8, 11, 6, 15, 13]]
_RR = [[5, 14, 7, 0, 9, 2, 11, 4, 13, 6, 15, 8, 1, 10, 3, 12],
       [6, 11, 3, 7, 0, 13, 5, 10, 14, 15, 8, 12, 4, 9, 1, 2],
       [15, 5, 1, 3, 7, 14, 6, 9, 11, 8, 12, 2, 10, 0, 4, 13],
       [8, 6, 4, 1, 3, 11, 15, 0, 5, 12, 2, 13, 9, 7, 10, 14],
       [12, 15, 10, 4, 1, 5, 8, 7, 6, 2, 13, 14, 0, 3, 9, 11]]
_SL = [[11, 14, 15, 12, 5, 8, 7, 9, 11, 13, 14, 15, 6, 7, 9, 8],
       [7, 6, 8, 13, 11, 9, 7, 15, 7, 12, 15, 9, 11, 7, 13, 12],
       [11, 13, 6, 7, 14, 9, 13, 15, 14, 8, 13, 6, 5, 12, 7, 5],
       [11, 12, 14, 15, 14, 15, 9, 8, 9, 14, 5, 6, 8, 6, 5, 12],
       [9, 15, 5, 11, 6, 8, 13, 12, 5, 12, 13, 14, 11, 8, 5, 6]]
_SR = [[8, 9, 9, 11, 13, 15, 15, 5, 7, 7, 8, 11, 14, 14, 12, 6],
       [9, 13, 15, 7, 12, 8, 9, 11, 7, 7, 12, 7, 6, 15, 13, 11],
       [9, 7, 15, 11, 8, 6, 6, 14, 12, 13, 5, 14, 13, 13, 7, 5],
       [15, 5, 8, 11, 14, 14, 6, 14, 6, 9, 12, 9, 12, 5, 15, 8],
       [8, 5, 12, 9, 12, 5, 14, 6, 8, 13, 6, 5, 15, 13, 11, 11]]
_KL = [0x00000000, 0x5A827999, 0x6ED9EBA1, 0x8F1BBCDC, 0xA953FD4E]
_KR = [0x50A28BE6, 0x5C4DD124, 0x6D703EF3, 0x7A6D76E9, 0x00000000]

def _rmd_f(j, x, y, z):
    if j == 0: return x ^ y ^ z
    if j == 1: return (x & y) | (~x & M32 & z)
    if j == 2: return (x | (~y & M32)) ^ z
    if j == 3: return (x & z) | (y & (~z & M32))
    return x ^ (y | (~z & M32))

def _rotl32(x, n):
    return ((x << n) | (x >> (32 - n))) & M32

def ripemd160(data):
    h = [0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0]
    total = len(data) * 8
    data = data + b"\x80"
    data += b"\x00" * ((-len(data) - 8) % 64) + total.to_bytes(8, "little")
    for off in range(0, len(data), 64):
        COUNT["ripemd160"] += 1
        x = [int.from_bytes(data[off + 4*i: off + 4*i + 4], "little") for i in range(16)]
        al, bl, cl, dl, el = h
        ar, br, cr, dr, er = h
        for rnd in range(5):
            for i in range(16):
                t = (_rotl32((al + _rmd_f(rnd, bl, cl, dl) + x[_RL[rnd][i]] + _KL[rnd]) & M32,
                             _SL[rnd][i]) + el) & M32
                al, el, dl, cl, bl = el, dl, _rotl32(cl, 10), bl, t
                t = (_rotl32((ar + _rmd_f(4 - rnd, br, cr, dr) + x[_RR[rnd][i]] + _KR[rnd]) & M32,
                             _SR[rnd][i]) + er) & M32
                ar, er, dr, cr, br = er, dr, _rotl32(cr, 10), br, t
        t = (h[1] + cl + dr) & M32
        h = [t, (h[2] + dl + er) & M32, (h[3] + el + ar) & M32,
             (h[4] + al + br) & M32, (h[0] + bl + cr) & M32]
    return b"".join(v.to_bytes(4, "little") for v in h)

# ------------------------------------------------------- the curve secp256k1
P = 2**256 - 2**32 - 977
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
GX = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
GY = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8

def _mul(a, b):
    COUNT["field_mul"] += 1
    return a * b % P

def _sqr(a):
    COUNT["field_sqr"] += 1
    return a * a % P

def _inv(a):
    """1/a by Fermat: a^(P-2), plain square-and-multiply."""
    r = 1
    for bit in bin(P - 2)[2:]:
        r = _sqr(r)
        if bit == "1":
            r = _mul(r, a)
    return r

def _double(pt):
    x, y, z = pt
    a, b = _sqr(x), _sqr(y)
    c = _sqr(b)
    d = 2 * (_sqr(x + b) - a - c) % P
    e = 3 * a % P
    x3 = (_sqr(e) - 2 * d) % P
    return x3, (_mul(e, d - x3) - 8 * c) % P, 2 * _mul(y, z) % P

def _add_g(pt):
    """Add the fixed base point G to a point in projective form."""
    x1, y1, z1 = pt
    zz = _sqr(z1)
    h = (_mul(GX, zz) - x1) % P
    r = (_mul(GY, _mul(z1, zz)) - y1) % P
    if h == 0:                      # cannot occur for scalars below N
        raise ArithmeticError("degenerate addition")
    hh = _sqr(h)
    hhh, v = _mul(h, hh), _mul(x1, hh)
    x3 = (_sqr(r) - hhh - 2 * v) % P
    return x3, (_mul(r, v - x3) - _mul(y1, hhh)) % P, _mul(z1, h)

def public_key(k):
    """k * G, compressed to 33 bytes. Plain double-and-add."""
    assert 0 < k < N
    COUNT["curve_mult"] += 1
    pt = None
    for bit in bin(k)[2:]:
        if pt is not None:
            pt = _double(pt)
        if bit == "1":
            pt = (GX, GY, 1) if pt is None else _add_g(pt)
    x, y, z = pt
    zi = _inv(z)
    zi2 = _sqr(zi)
    x, y = _mul(x, zi2), _mul(y, _mul(zi, zi2))
    return bytes([2 + (y & 1)]) + x.to_bytes(32, "big")

# ------------------------------------------------------------ Base58Check
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def base58check(payload):
    data = payload + sha256(sha256(payload))[:4]
    n, out = int.from_bytes(data, "big"), ""
    while n:
        n, rem = divmod(n, 58)
        out = _B58[rem] + out
    return "1" * (len(data) - len(data.lstrip(b"\x00"))) + out

# ------------------------------------------------------------------ QR code
# One fixed size only: version 6 (41 x 41 squares), lowest error correction,
# byte mode. It holds up to 134 characters; the descriptor is always 131.
QR_SIZE = 41

def _gf_tables():
    """Arithmetic on bytes for the error-correction step (field 0x11D)."""
    exp, log, x = [0] * 510, [0] * 256, 1
    for i in range(255):
        exp[i], log[x] = x, i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    exp[255:510] = exp[0:255]
    return exp, log

_EXP, _LOG = _gf_tables()

def _rs_remainder(data, n):
    """The n error-correction bytes for one block of data."""
    gen = [1]                               # (x - 2^0)(x - 2^1)...(x - 2^(n-1))
    for i in range(n):
        gen = [(gen[j] if j < len(gen) else 0) ^
               (_EXP[_LOG[gen[j - 1]] + i] if j and gen[j - 1] else 0)
               for j in range(len(gen) + 1)]
    rem = [0] * n
    for byte in data:
        factor = byte ^ rem[0]
        rem = rem[1:] + [0]
        if factor:
            for j in range(n):
                rem[j] ^= _EXP[_LOG[gen[j + 1]] + _LOG[factor]]
    return rem

_MASKS = [lambda x, y: (x + y) % 2 == 0,
          lambda x, y: y % 2 == 0,
          lambda x, y: x % 3 == 0,
          lambda x, y: (x + y) % 3 == 0,
          lambda x, y: (x // 3 + y // 2) % 2 == 0,
          lambda x, y: x * y % 2 + x * y % 3 == 0,
          lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
          lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0]

def _qr_penalty(m):
    """The standard's score for how hard a pattern is to scan. Lower is better."""
    n, score = QR_SIZE, 0
    lines = [row[:] for row in m] + [[m[y][x] for y in range(n)] for x in range(n)]
    for line in lines:
        run = 1
        for i in range(1, n + 1):           # runs of five or more alike
            if i < n and line[i] == line[i - 1]:
                run += 1
            else:
                if run >= 5:
                    score += run - 2
                run = 1
        for i in range(n - 10):             # shapes that mimic a corner marker
            if line[i:i + 11] in ([1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0],
                                  [0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1]):
                score += 40
    for y in range(n - 1):                  # 2 x 2 blocks alike
        for x in range(n - 1):
            if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                score += 3
    dark = sum(map(sum, m))                 # balance of dark and light
    score += 10 * (abs(dark * 20 - n * n * 10) // (n * n))
    return score

def qr_rows(text, mask=None):
    """
    Text -> 41 rows of 41 squares (1 = dark = light ON). The mask is chosen
    by the standard's scoring unless one is given.
    """
    raw = text.encode()
    assert len(raw) <= 134
    # 1. the message as 136 bytes: type, length, text, end mark, padding
    bits = "0100" + format(len(raw), "08b") + "".join(format(b, "08b") for b in raw) + "0000"
    bits += "0" * (-len(bits) % 8)
    data = [int(bits[i:i + 8], 2) for i in range(0, len(bits), 8)]
    data += [0xEC, 0x11] * 68
    data = data[:136]
    # 2. two blocks of 68, each with 18 error-correction bytes, interleaved
    blocks = [data[:68], data[68:]]
    extra = [_rs_remainder(b, 18) for b in blocks]
    stream = [b[i] for i in range(68) for b in blocks] + [e[i] for i in range(18) for e in extra]
    # 3. the fixed furniture: three corner markers, timing lines, one small marker
    n = QR_SIZE
    m = [[0] * n for _ in range(n)]
    fixed = [[False] * n for _ in range(n)]
    def put(x, y, v):
        m[y][x], fixed[y][x] = int(v), True
    for i in range(n):
        put(6, i, i % 2 == 0)
        put(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                if 0 <= cx + dx < n and 0 <= cy + dy < n:
                    put(cx + dx, cy + dy, max(abs(dx), abs(dy)) not in (2, 4))
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            put(34 + dx, 34 + dy, max(abs(dx), abs(dy)) != 1)
    def put_format(k):
        v = (1 << 3 | k) << 10              # 01 = lowest error correction
        rem = v
        for i in range(14, 9, -1):
            if rem >> i & 1:
                rem ^= 0x537 << (i - 10)
        v = (v | rem) ^ 0x5412
        bit = lambda i: v >> i & 1
        for i in range(6):
            put(8, i, bit(i))
        put(8, 7, bit(6)); put(8, 8, bit(7)); put(7, 8, bit(8))
        for i in range(9, 15):
            put(14 - i, 8, bit(i))
        for i in range(8):
            put(n - 1 - i, 8, bit(i))
        for i in range(8, 15):
            put(8, n - 15 + i, bit(i))
        put(8, n - 8, 1)
    put_format(0)                           # reserves the squares
    # 4. the message, zig-zagging up and down in two-wide columns from the right
    i, right = 0, n - 1
    while right >= 1:
        if right == 6:
            right = 5
        for vert in range(n):
            for j in range(2):
                x = right - j
                y = n - 1 - vert if (right + 1) & 2 == 0 else vert
                if not fixed[y][x] and i < len(stream) * 8:
                    m[y][x] = stream[i >> 3] >> (7 - (i & 7)) & 1
                    i += 1
        right -= 2
    # 5. the mask: flip a regular pattern of squares so the result scans well
    best = None
    for k in ([mask] if mask is not None else range(8)):
        put_format(k)
        trial = [[m[y][x] ^ (not fixed[y][x] and _MASKS[k](x, y)) for x in range(n)]
                 for y in range(n)]
        score = _qr_penalty(trial)
        if best is None or score < best[0]:
            best = (score, trial)
    return best[1]

# --------------------------------------------------------------- word list
def load_words(path=None):
    import os
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "bip39_english.txt")
    words = open(path).read().split()
    assert len(words) == 2048
    return words

# ------------------------------------------------------- the two real jobs
def final_word(indexes11, bits7):
    """
    Job 1. 11 word numbers (0-2047) plus 7 coin-flip bits -> the 12th word
    number. The 7 bits are the top of the last word; the checksum is the
    4 bits below them.
    """
    entropy = 0
    for i in indexes11:
        entropy = (entropy << 11) | i
    entropy = (entropy << 7) | bits7
    checksum = sha256(entropy.to_bytes(16, "big"))[0] >> 4
    return (bits7 << 4) | checksum

def account_key(words12, passphrase="", path=(84, 0, 0)):
    """
    Job 2. 12 words -> master fingerprint and the account extended public
    key. All three path steps are hardened.
    """
    text = unicodedata.normalize("NFKD", " ".join(words12)).encode()
    salt = unicodedata.normalize("NFKD", "mnemonic" + passphrase).encode()
    seed = pbkdf2_sha512(text, salt, 2048)

    i = hmac_sha512(b"Bitcoin seed", seed)
    key, chain = int.from_bytes(i[:32], "big"), i[32:]
    master_fp = ripemd160(sha256(public_key(key)))[:4]

    parent_fp, number = b"\x00" * 4, 0
    for depth, step in enumerate(path, 1):
        number = step | 0x80000000
        if depth == len(path):
            parent_fp = ripemd160(sha256(public_key(key)))[:4]
        i = hmac_sha512(chain, b"\x00" + key.to_bytes(32, "big") + number.to_bytes(4, "big"))
        key, chain = (int.from_bytes(i[:32], "big") + key) % N, i[32:]

    body = (bytes([len(path)]) + parent_fp + number.to_bytes(4, "big")
            + chain + public_key(key))
    return {"fingerprint": master_fp.hex(),
            "xpub": base58check(bytes.fromhex("0488B21E") + body),
            "zpub": base58check(bytes.fromhex("04B24746") + body)}

# ------------------------------------------------------------ cost estimate
def estimate(count):
    """
    Rough instruction counts for an 8-bit accumulator machine. Assumptions:
      - one byte-wide step (load, operate, store) = 3 instructions
      - one 8x8 multiply by table lookup, accumulated = 18 instructions
    """
    step = 3
    # SHA-512: per compression, 760 additions, 1136 logic ops, 864 rotations
    # or shifts, all on 8-byte words. A rotation is 8 byte moves plus, on
    # average, 1.8 single-bit shifts across the 8 bytes.
    sha512_c = (760 * 8 + 1136 * 8 + 864 * (8 + 1.8 * 8)) * step
    small_c = sha512_c / 4          # SHA-256 / RIPEMD-160: 4-byte words, fewer rounds
    field = (32 * 32 + 32 * 5) * 18 + 64 * 2 * step     # multiply + reduce
    parts = {
        "2048 rounds + derivation (SHA-512)": count["sha512"] * sha512_c,
        "curve work (field multiplications)": (count["field_mul"] + count["field_sqr"]) * field,
        "everything else (SHA-256, RIPEMD-160)": (count["sha256"] + count["ripemd160"]) * small_c,
    }
    return parts

# --------------------------------------------------------------------- CLI
def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    words = load_words()
    if len(args) == 12 and set(args[11]) <= set("01") and len(args[11]) == 7:
        idx = [words.index(w) for w in args[:11]]
        last = final_word(idx, int(args[11], 2))
        print(f"12th word : {words[last]}   switches {last:011b}   (list line {last + 1})")
        args = args[:11] + [words[last]]
    elif len(args) == 12:
        idx = [words.index(w) for w in args]
        if final_word(idx[:11], idx[11] >> 4) != idx[11]:
            sys.exit("checksum does not match: not a valid 12-word phrase")
    else:
        sys.exit("usage: keycalc.py w1 ... w11 BBBBBBB   (7 coin-flip bits)\n"
                 "   or: keycalc.py w1 ... w12             [--count] [--qr]")
    out = account_key(args)
    print(f"fingerprint: {out['fingerprint']}")
    print(f"xpub       : {out['xpub']}")
    print(f"zpub       : {out['zpub']}")
    descriptor = f"[{out['fingerprint']}/84h/0h/0h]{out['zpub']}"
    print(f"descriptor : {descriptor}")
    if "--qr" in argv:
        print("\nQR code, as the row of 41 bulbs would show it (# = bulb lit)")
        for number, row in enumerate(qr_rows(descriptor), 1):
            print(f"  row {number:>2}  " + "".join("#" if v else "." for v in row))
    if "--count" in argv:
        print("\noperation counts")
        for k, v in COUNT.items():
            print(f"  {k:<12}{v:>8,}")
        parts = estimate(COUNT)
        total = sum(parts.values())
        print("\nestimated 8-bit instructions")
        for k, v in parts.items():
            print(f"  {k:<40}{v/1e6:>8.0f} M  {100*v/total:>4.0f}%")
        print(f"  {'total':<40}{total/1e6:>8.0f} M")
        for mips in (0.25, 1, 3):
            print(f"  at {mips:>4} million instructions/second: {total/mips/1e6/60:>6.1f} minutes")

if __name__ == "__main__":
    main(sys.argv[1:])
