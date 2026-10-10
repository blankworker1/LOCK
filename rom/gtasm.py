"""gtasm.py - a very small assembler for the Gigatron's native instruction set.

The Gigatron CPU has 8 operations, 8 addressing modes and 4 bus sources,
packed into one byte, followed by one operand byte. Every ROM word is one
such pair. Encoding follows Docs/gtemu.c in the official gigatron-rom repo.

Things to know when reading code written with this:
  - Branches take effect one instruction late: the instruction after a
    branch always runs (the "delay slot").
  - Conditional branches can only land in the same 256-word page.
  - There is no carry flag. Carries are worked out from the top bits.
"""

# operands
def imm(v): return ("i", v)             # the number itself
def zp(a): return ("z", a)              # memory at address a in page zero
IX = ("x",)                             # memory at [X] in page zero
def yd(a): return ("yd", a)             # memory at page Y, offset a
YX = ("yx",)                            # memory at page Y, offset X
AC = ("ac",)                            # the accumulator
IN = ("in",)                            # the input port (the controller port's shift register)

_MODBUS = {("i", "AC"): (0, 0), ("i", "X"): (4, 0), ("i", "Y"): (5, 0), ("i", "OUT"): (6, 0),
           ("ac", "OUT"): (6, 2), ("in", "AC"): (0, 3),
           ("z", "AC"): (0, 1), ("z", "X"): (4, 1), ("z", "Y"): (5, 1),
           ("x", "AC"): (1, 1), ("yd", "AC"): (2, 1), ("yx", "AC"): (3, 1),
           ("ac", "AC"): (0, 2), ("ac", "X"): (4, 2), ("ac", "Y"): (5, 2)}
_STMOD = {"z": 0, "x": 1, "yd": 2, "yx": 3}
_COND = {"bgt": 1, "blt": 2, "bne": 3, "beq": 4, "bge": 5, "ble": 6, "bra": 7}


class Asm:
    def __init__(self):
        self.rom, self.labels, self.fixups, self.y = [], {}, [], None

    @property
    def pc(self):
        return len(self.rom)

    def _emit(self, ir, d=0):
        if not isinstance(d, int):
            self.fixups.append((self.pc, d))
            d = 0
        self.rom.append([ir, d & 0xFF])

    def label(self, name):
        assert name not in self.labels, name
        self.labels[name] = self.pc
        self.y = None                   # Y is not known after a jump target

    def fit(self, n):
        """Keep the next n instructions inside one page (pad with no-ops)."""
        while (self.pc & 0xFF) + n > 0x100:
            self.nop()

    def _alu(self, ins, op, dst="AC"):
        mod, bus = _MODBUS[(op[0], dst)]
        self._emit(ins << 5 | mod << 2 | bus, op[1] if len(op) > 1 else 0)
        if dst == "Y":
            self.y = op[1] if op[0] == "i" else None

    def ld(self, op, dst="AC"): self._alu(0, op, dst)
    def anda(self, op, dst="AC"): self._alu(1, op, dst)
    def ora(self, op, dst="AC"): self._alu(2, op, dst)
    def xora(self, op, dst="AC"): self._alu(3, op, dst)
    def adda(self, op, dst="AC"): self._alu(4, op, dst)
    def suba(self, op, dst="AC"): self._alu(5, op, dst)
    def nop(self): self._emit(0x02)     # ld ac

    def page(self, p):
        """Point Y at a page, skipping the instruction if it is already there."""
        if self.y != p:
            self.ld(imm(p), "Y")

    def st(self, op, also=None):
        """Store AC. `also` = "X" or "Y" copies AC there too (page-zero stores only)."""
        mod = _STMOD[op[0]]
        if also:
            assert op[0] == "z"
            mod = 4 if also == "X" else 5
            if also == "Y":
                self.y = None
        self._emit(6 << 5 | mod << 2 | 2, op[1] if len(op) > 1 else 0)

    def sti(self, v):
        """Store a constant at [Y,X] and add one to X."""
        self._emit(6 << 5 | 7 << 2 | 0, v)

    def branch(self, cond, label):
        self._emit(7 << 5 | _COND[cond] << 2 | 0, ("lo", label, "samepage"))

    def far(self, label, slot=None):
        """Jump anywhere: load the page into Y, jump, one more instruction runs."""
        self._emit(0 << 5 | 5 << 2 | 0, ("hi", label))
        self._emit(7 << 5 | 0 << 2 | 0, ("lo", label))
        self.nop() if slot is None else slot()
        self.y = None

    def jump_via(self, hi_addr, lo_addr):
        """Jump to the address held in two page-zero bytes (a subroutine return)."""
        self.ld(zp(hi_addr), "Y")
        self._emit(7 << 5 | 0 << 2 | 1, lo_addr)
        self.nop()
        self.y = None

    def image(self):
        for pc, fx in self.fixups:
            target = self.labels[fx[1]]
            if fx[0] == "hi":
                self.rom[pc][1] = target >> 8
            else:
                self.rom[pc][1] = target & 0xFF
                if len(fx) > 2:         # the branch lands in the page of the next word
                    assert (pc + 1) >> 8 == target >> 8, f"branch at {pc:#x} to {fx[1]} leaves its page"
        assert len(self.rom) <= 65536, "ROM full"
        out = bytearray()
        for ir, d in self.rom:
            out += bytes([ir, d])
        return bytes(out) + bytes([0x02, 0x00]) * (65536 - len(self.rom))
