#!/usr/bin/env python3
"""sha512_rom.py - the heavy hash (one SHA-512 pass) as native Gigatron code.

Builds a ROM image holding:
  - start-up code that fills the lookup tables the hash needs
  - one routine, `compress`, that does one SHA-512 pass

Memory use (RAM pages are 256 bytes):
  page 0      working values: the 8 running words, 16 message words, temporaries
  page 1      0x00-0x3f the hash state (8 words), 0x40-0xbf the 128-byte block
  pages 2-6   the 80 round constants, 16 per page
  pages 9-15  "shift right by 1..7" tables
  pages 17-23 "shift left by 1..7" tables
All 64-bit words are stored lowest byte first.

Speed comes from two choices: shifts are table lookups (the CPU cannot
shift), and the 16 rounds of a cycle are written out one after another so
every memory address is fixed and nothing is computed at run time.
"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reference"))
import keycalc as k
from gtasm import Asm, imm, zp, IX, yd, YX, AC

# ---- page zero layout -------------------------------------------------
ZERO, ONE = 0x00, 0x80                  # must hold 0 and 1: used to turn a top bit into a carry
STATE = 0x01                            # 8 words: the running a..h (64 bytes)
SG, TA, TB, CT = 0x41, 0x49, 0x51, 0x59  # 8-byte temporaries
W15 = 0x61                              # message word 15 (the other 15 sit at 0x81..0xf8)
SUMTMP, LOOP, KPAGE, CNT, RETLO, RETHI = 0x69, 0x6A, 0x6B, 0x6C, 0x6D, 0x6E
PAGE_IO, H_OFF, BLOCK_OFF = 1, 0x00, 0x40
PAGE_K, PAGE_SHR, PAGE_SHL = 2, 8, 16   # table for shift k is at PAGE_SHx + k

def W(i): return W15 if i % 16 == 15 else 0x81 + 8 * (i % 16)
def word(base): return [zp(base + j) for j in range(8)]

a = Asm()

# ---- building blocks --------------------------------------------------
def add(dst, x, y):
    """dst = x + y for 8-byte words (lists of operands, lowest byte first).
    The carry out of each byte is found from the top bits of x, y and the sum:
    if the sum's top bit is 1 the carry is (x AND y), otherwise (x OR y)."""
    inplace = dst[0] == x[0]
    keep = a.y                          # the add never changes Y
    for j in range(8):
        if j == 0: a.ld(x[0])
        else: a.adda(x[j])              # AC holds the carry (0 or 1) on entry
        a.adda(y[j])
        if j == 7:
            a.st(dst[j]); break
        a.st(zp(SUMTMP) if inplace else dst[j])
        a.fit(6)
        neg, join = f"n{a.pc}", f"j{a.pc}"
        a.branch("blt", neg)
        a.ld(x[j])                      # (runs either way)
        a.branch("bra", join)
        a.ora(y[j])                     # sum's top bit 0: carry = x OR y
        a.label(neg); a.y = keep
        a.anda(y[j])                    # sum's top bit 1: carry = x AND y
        a.label(join); a.y = keep
        a.anda(imm(0x80), "X")          # X = 0x00 or 0x80
        if inplace:
            a.ld(zp(SUMTMP)); a.st(dst[j])
        a.ld(IX)                        # AC = memory[0x00] = 0 or memory[0x80] = 1

def sigma(dst, src, terms):
    """dst = XOR of rotations/shifts of the 8-byte word at src (page zero).
    terms: ("rot", n) or ("shr", n). Each output byte is the XOR of up to
    six table lookups: (byte >> k) from one input byte, (byte << 8-k) from the next."""
    for j in range(8):
        parts = []                      # (input byte index, table page or None)
        for kind, n in terms:
            q, s = divmod(n, 8)
            for m, page in ((j + q, PAGE_SHR + s if s else None), (j + q + 1, PAGE_SHL + 8 - s if s else "skip")):
                if page == "skip" or (kind == "shr" and m > 7):
                    continue
                parts.append((m % 8, page))
        parts.sort(key=lambda p: (p[1] is not None, p[1] or 0), reverse=bool(j & 1))
        first = True
        for m, page in parts:
            op = a.ld if first else a.xora
            if page is None:
                op(zp(src + m))
            else:
                a.ld(zp(src + m), "X"); a.page(page); op(YX)
            first = False
        a.st(zp(dst + j))

def round_(v):
    """Round v of a 16-round cycle. The 8 running words are not moved:
    their names rotate instead, so slot (j - v) mod 8 holds word j."""
    s = lambda j: STATE + 8 * ((j - v) % 8)
    A, B, C, D, E, F, G, H = (s(j) for j in range(8))
    sigma(SG, E, [("rot", 14), ("rot", 18), ("rot", 41)])
    add(word(TA), word(H), word(SG))
    for j in range(8):                  # ch = g xor (e and (f xor g))
        a.ld(zp(F + j)); a.xora(zp(G + j)); a.anda(zp(E + j)); a.xora(zp(G + j)); a.st(zp(CT + j))
    add(word(TB), word(TA), word(CT))
    a.ld(zp(KPAGE), "Y")
    add(word(TA), word(TB), [yd(8 * v + j) for j in range(8)])       # + round constant
    add(word(TB), word(TA), word(W(v)))                              # + message word: TB = t1
    sigma(SG, A, [("rot", 28), ("rot", 34), ("rot", 39)])
    for j in range(8):                  # maj = b xor ((a xor b) and (b xor c))
        a.ld(zp(B + j)); a.xora(zp(C + j)); a.st(zp(SUMTMP))
        a.ld(zp(A + j)); a.xora(zp(B + j)); a.anda(zp(SUMTMP)); a.xora(zp(B + j)); a.st(zp(CT + j))
    add(word(TA), word(SG), word(CT))   # TA = t2
    add(word(D), word(D), word(TB))     # d slot becomes the new e
    add(word(H), word(TB), word(TA))    # h slot becomes the new a

def schedule(v):
    """Next message word: w[v] += s0(w[v+1]) + w[v+9] + s1(w[v+14])."""
    sigma(SG, W(v + 1), [("rot", 1), ("rot", 8), ("shr", 7)])
    add(word(TA), word(W(v)), word(SG))
    sigma(SG, W(v + 14), [("rot", 19), ("rot", 61), ("shr", 6)])
    add(word(TB), word(TA), word(W(v + 9)))
    add(word(W(v)), word(TB), word(SG))

def table_loop(body, count=256):
    """Run body() with CNT = 0..count-1."""
    a.ld(imm(0)); a.st(zp(CNT))
    a.fit(24)
    top = f"t{a.pc}"
    a.label(top)
    body()
    a.ld(zp(CNT)); a.adda(imm(1)); a.st(zp(CNT))
    if count != 256: a.xora(imm(count))
    a.branch("bne", top); a.nop()

# ---- start-up: constants and tables ------------------------------------
a.nop(); a.nop()
a.ld(imm(0)); a.st(zp(ZERO)); a.ld(imm(1)); a.st(zp(ONE))

def shl1():                             # table[x] = x + x
    a.ld(zp(CNT), "X"); a.ld(zp(CNT)); a.adda(AC); a.page(PAGE_SHL + 1); a.st(YX)
table_loop(shl1)
def shr1():                             # table[2i] = table[2i+1] = i
    a.ld(zp(CNT)); a.adda(AC); a.ld(AC, "X"); a.page(PAGE_SHR + 1); a.ld(zp(CNT)); a.st(YX)
    a.ld(zp(CNT)); a.adda(AC); a.adda(imm(1)); a.ld(AC, "X"); a.ld(zp(CNT)); a.st(YX)
table_loop(shr1, 128)
for base in (PAGE_SHL, PAGE_SHR):       # shift by n = shift by n-1, then by 1
    for n in range(2, 8):
        def compose(base=base, n=n):
            a.ld(zp(CNT), "X"); a.ld(imm(base + n - 1), "Y"); a.ld(YX); a.ld(AC, "X")
            a.ld(imm(base + 1), "Y"); a.ld(YX)
            a.ld(zp(CNT), "X"); a.ld(imm(base + n), "Y"); a.st(YX)
        table_loop(compose)
for cyc in range(5):                    # the 80 round constants, lowest byte first
    a.ld(imm(PAGE_K + cyc), "Y"); a.ld(imm(0), "X")
    for v in range(16):
        for j in range(8):
            a.sti((k.K512[16 * cyc + v] >> (8 * j)) & 0xFF)
a.far("halt")

# ---- compress: one SHA-512 pass ----------------------------------------
a.label("compress")
a.page(PAGE_IO)
for i in range(8):                      # running words = hash state
    for j in range(8):
        a.ld(yd(H_OFF + 8 * i + j)); a.st(zp(STATE + 8 * i + j))
for i in range(16):                     # message words: block bytes are highest first
    for j in range(8):
        a.ld(yd(BLOCK_OFF + 8 * i + 7 - j)); a.st(zp(W(i) + j))
a.ld(imm(0)); a.st(zp(LOOP)); a.ld(imm(PAGE_K)); a.st(zp(KPAGE))
a.label("cycle")
for v in range(16):
    a.fit(7)
    a.ld(zp(LOOP))
    a.branch("bne", f"sched{v}")        # the first 16 rounds use the block as it is
    a.nop()
    a.far(f"round{v}")
    a.label(f"sched{v}")
    schedule(v)
    a.label(f"round{v}")
    round_(v)
a.ld(zp(KPAGE)); a.adda(imm(1)); a.st(zp(KPAGE))
a.ld(zp(LOOP)); a.adda(imm(1)); a.st(zp(LOOP))
a.fit(7)
a.xora(imm(5))
a.branch("beq", "finish"); a.nop()
a.far("cycle")
a.label("finish")
a.page(PAGE_IO)
for i in range(8):                      # hash state += running words
    hw = [yd(H_OFF + 8 * i + j) for j in range(8)]
    add(hw, hw, word(STATE + 8 * i))
a.jump_via(RETHI, RETLO)

a.nop(); a.nop()
a.label("halt")
a.branch("bra", "halt"); a.nop()

if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    open(os.path.join(here, "sha512.rom"), "wb").write(a.image())
    json.dump({"labels": {n: v for n, v in a.labels.items() if not n[0] in "njt" or n in ("halt",)},
               "words": a.pc, "RETLO": RETLO, "RETHI": RETHI,
               "H": PAGE_IO * 256 + H_OFF, "BLOCK": PAGE_IO * 256 + BLOCK_OFF},
              open(os.path.join(here, "sha512.json"), "w"), indent=1)
    print(f"ROM words used: {a.pc} of 65536 ({100 * a.pc / 65536:.0f}%)")
