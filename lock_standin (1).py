#!/usr/bin/env python3
"""
LOCK stand-in for the KEY paper dry run. PRACTICE KEYS ONLY.

Does on a computer what LOCK does with switches and lights, and speaks the
same language as the plate: numbers and dots in, numbers and dots out.
No words are typed and none are printed.

    python3 KEY/lock_standin.py  N1 N2 ... N11  BBBBBBB        (run from the LOCK folder)

    N1..N11   the first eleven rows of the seed plate, as the four-digit
              numbers (0000-2047) or as the eleven dots (1 = dot, 0 = blank)
    BBBBBBB   the seven dice bits of row 12 (2 orange, 5 white), no spaces

It prints row 12 (dots and number), the fingerprint, the text the xpub code
holds, and the 41 rows of the code in blocks A to D, in LOCK's fixed pattern.

It lives in the LOCK repository's KEY/ folder and uses reference/keycalc.py,
which does all the arithmetic. Never use it for a key that will hold money:
a networked computer has seen every bit of it.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for folder in (os.path.join(HERE, "..", "reference"), HERE, os.path.join(HERE, "reference"),
               os.path.join(os.getcwd(), "reference"), os.getcwd()):
    if os.path.exists(os.path.join(folder, "keycalc.py")):
        sys.path.insert(0, folder)
        break
else:
    sys.exit("keycalc.py not found. Run this from the LOCK folder: python3 KEY/lock_standin.py ...")
import keycalc as K

BLOCKS = ((0, 11), (11, 22), (22, 33), (33, 41))        # A, B, C, D


def row_value(token, position):
    """One plate row, given as a number 0-2047 or as eleven 0/1 dots."""
    if len(token) == 11 and set(token) <= set("01"):
        return int(token, 2)
    if token.isdigit() and int(token) <= 2047:
        return int(token)
    sys.exit(f"row {position}: '{token}' is not a number from 0000 to 2047, nor eleven 0/1 dots")


def dots(value):
    b = format(value, "011b")
    return f"{b[:2]} {b[2:7]} {b[7:]}"                  # 2 | 5 | 4, like the dice


def main(args):
    if len(args) != 12 or len(args[11]) != 7 or not set(args[11]) <= set("01"):
        sys.exit(__doc__)
    rows = [row_value(t, i + 1) for i, t in enumerate(args[:11])]
    last = K.final_word(rows, int(args[11], 2))
    words = K.load_words()
    out = K.account_key([words[i] for i in rows + [last]])
    text = f"[{out['fingerprint']}/84h/0h/0h]{out['zpub']}"

    print("\nPRACTICE ONLY. This key must never hold money.\n")
    print("What you entered (check against the plate)")
    for i, v in enumerate(rows, 1):
        print(f"  row {i:>2}   {dots(v)}   {v:04d}")
    print(f"\nRow 12        {dots(last)}   {last:04d}")
    print("              the first seven dots are your dice; mark the LAST FOUR in the shaded cells")
    print(f"\nFingerprint   {out['fingerprint']}")
    print(f"Code text     {text}")
    print("\nThe xpub code, as LOCK's lights show it.  # = fill the square, . = leave it")
    print("  row   A            B            C            D")
    for n, row in enumerate(K.qr_rows(text, mask=0), 1):   # mask 0 = LOCK's one fixed pattern
        line = "".join("#" if v else "." for v in row)
        print(f"  {n:>3}   " + "  ".join(line[a:b] for a, b in BLOCKS))
    print()


if __name__ == "__main__":
    main(sys.argv[1:])
