#!/usr/bin/env python3
"""
LOCK stand-in for the KEY paper dry run. PRACTICE KEYS ONLY.

Does on a computer what LOCK does with switches and lights, and speaks the
same language as the plates: numbers and dots in, numbers and dots out.
No words are typed and none are printed.

    python3 KEY/lock_standin.py  N1 N2 ... N11  BBBBBBB        (run from the LOCK folder)

    N1..N11   the first eleven rows of the seed plate, as the four-digit
              numbers (0000-2047) or as the eleven dots (1 = dot, 0 = blank)
    BBBBBBB   the seven dice bits of row 12 (2 orange, 5 white), no spaces

It prints row 12 (dots and number), then THE LOCK: the one address this key
will ever receive to, as the nineteen rows to punch on the lock plate.

    --xpub    also print the earlier output: the fingerprint, the account
              public key and its 41-row code (kept for comparison)

The address is the first native SegWit address of the key (m/84'/0'/0'/0/0).
It is "bc1q" followed by 38 characters, and each character is a number from
00 to 31. A lock-plate row holds two characters as 5 + 5 dots, and an
eleventh dot that makes the number of dots in the row even.

It lives in the LOCK repository's KEY/ folder and uses reference/keycalc.py,
which does all the arithmetic. Never use it for a key that will hold money:
a networked computer has seen every bit of it.
"""
import os
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
for folder in (os.path.join(HERE, "..", "reference"), HERE, os.path.join(HERE, "reference"),
               os.path.join(os.getcwd(), "reference"), os.getcwd()):
    if os.path.exists(os.path.join(folder, "keycalc.py")):
        sys.path.insert(0, folder)
        break
else:
    sys.exit("keycalc.py not found. Run this from the LOCK folder: python3 KEY/lock_standin.py ...")
import keycalc as K

BLOCKS = ((0, 11), (11, 22), (22, 33), (33, 41))        # A, B, C, D of the old 41-row code
ALPHABET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"            # the address alphabet: position = number 00-31


def row_value(token, position):
    """One seed-plate row, given as a number 0-2047 or as eleven 0/1 dots."""
    if len(token) == 11 and set(token) <= set("01"):
        return int(token, 2)
    if token.isdigit() and int(token) <= 2047:
        return int(token)
    sys.exit(f"row {position}: '{token}' is not a number from 0000 to 2047, nor eleven 0/1 dots")


def dots(value):
    b = format(value, "011b")
    return f"{b[:2]} {b[2:7]} {b[7:]}"                  # 2 | 5 | 4, like the dice


# ---------------------------------------------------------------- the lock
def first_key_hash(words12):
    """
    12 words -> the 20-byte hash of the first receiving public key,
    m/84'/0'/0'/0/0. Three hardened steps, then two ordinary ones.
    """
    text = unicodedata.normalize("NFKD", " ".join(words12)).encode()
    seed = K.pbkdf2_sha512(text, b"mnemonic", 2048)
    i = K.hmac_sha512(b"Bitcoin seed", seed)
    key, chain = int.from_bytes(i[:32], "big"), i[32:]
    for step, hardened in ((84, True), (0, True), (0, True), (0, False), (0, False)):
        if hardened:
            data = b"\x00" + key.to_bytes(32, "big") + (step | 0x80000000).to_bytes(4, "big")
        else:
            data = K.public_key(key) + step.to_bytes(4, "big")
        i = K.hmac_sha512(chain, data)
        key, chain = (int.from_bytes(i[:32], "big") + key) % K.N, i[32:]
    return K.ripemd160(K.sha256(K.public_key(key)))


def _polymod(values):
    """The address checksum sum (BIP173)."""
    chk = 1
    for v in values:
        top = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ v
        for i, g in enumerate((0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)):
            if top >> i & 1:
                chk ^= g
    return chk


def lock_values(key_hash):
    """
    20-byte hash -> the 38 numbers (00-31) that follow "bc1q":
    32 for the hash itself, regrouped in fives, and 6 of checksum.
    """
    bits = "".join(format(b, "08b") for b in key_hash)             # 160 bits
    data = [int(bits[i:i + 5], 2) for i in range(0, 160, 5)]       # 32 numbers
    hrp = [3, 3, 0, 2, 3]                                          # "bc", spread out as the standard says
    mod = _polymod(hrp + [0] + data + [0] * 6) ^ 1                 # the leading 0 is the "q"
    return data + [(mod >> 5 * (5 - i)) & 31 for i in range(6)]


def lock_rows(values):
    """38 numbers -> 19 rows of (first, second, parity dot, eleven-dot string)."""
    rows = []
    for i in range(0, 38, 2):
        a, b = values[i], values[i + 1]
        ten = format(a, "05b") + format(b, "05b")
        parity = ten.count("1") % 2                                # makes the row's dot count even
        rows.append((a, b, parity, ten + str(parity)))
    return rows


def address(values):
    return "bc1q" + "".join(ALPHABET[v] for v in values)


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 12 or len(args[11]) != 7 or not set(args[11]) <= set("01"):
        sys.exit(__doc__)
    rows = [row_value(t, i + 1) for i, t in enumerate(args[:11])]
    last = K.final_word(rows, int(args[11], 2))
    words = [K.load_words()[i] for i in rows + [last]]

    print("\nPRACTICE ONLY. This key must never hold money.\n")
    print("What you entered (check against the seed plate)")
    for i, v in enumerate(rows, 1):
        print(f"  row {i:>2}   {dots(v)}   {v:04d}")
    print(f"\nRow 12        {dots(last)}   {last:04d}")
    print("              the first seven dots are your dice; mark the LAST FOUR in the shaded cells")

    values = lock_values(first_key_hash(words))
    print("\nTHE LOCK, as LOCK's lights show it.  # = punch the cell, . = leave it")
    print("Every row has an even number of dots.\n")
    print("  row   16 8 4 2 1   16 8 4 2 1   =    numbers   letters")
    for n, (a, b, parity, bits) in enumerate(lock_rows(values), 1):
        show = lambda s: " ".join("#" if c == "1" else "." for c in s)
        print(f"  {n:>3}   {show(bits[:5])}    {show(bits[5:10])}   {show(bits[10])}     {a:02d} {b:02d}      {ALPHABET[a]} {ALPHABET[b]}")
    print(f"\nAddress       {address(values)}")
    print("              bc1q, then the 38 letters above, read row by row")

    if "--xpub" in argv:
        out = K.account_key(words)
        text = f"[{out['fingerprint']}/84h/0h/0h]{out['zpub']}"
        print(f"\nFingerprint   {out['fingerprint']}")
        print(f"Code text     {text}")
        print("\nThe xpub code, in LOCK's fixed pattern.  # = fill the square, . = leave it")
        print("  row   A            B            C            D")
        for n, row in enumerate(K.qr_rows(text, mask=0), 1):
            line = "".join("#" if v else "." for v in row)
            print(f"  {n:>3}   " + "  ".join(line[a:b] for a, b in BLOCKS))
    print()


if __name__ == "__main__":
    main(sys.argv[1:])
