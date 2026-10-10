# LOCK

**A transparent key calculator. An Anonymous Art artifact.**

LOCK runs on a Gigatron, a computer built from plain logic chips with no microprocessor. You enter 11 seed words and 7 coin flips on a row of switches. It shows the 12th word and the account's public key record as a QR code, one row at a time on 41 lights, for copying by hand.

The full outline is in [PROJECT.md](PROJECT.md).

## Status

- A complete program chip image exists: `release/lock.rom`.
- It passes every test on a model of the Gigatron and of the plug-in module.
- **It has not run on a real board.** No module has been built.
- The code is new and unaudited. **Use published test phrases only.** Never type a real seed into `reference/keycalc.py`: that program is for a networked PC and exists only to check answers.
- Licence: not yet chosen. To be decided after the first run on real hardware. `rom/gtrun.c` contains the official Gigatron CPU model, which carries its own licence (`rom/LICENSE-gigatron-cpu-model`).

## Layout

| Folder | What is in it |
|---|---|
| `reference/` | The reference program in plain Python, its tests, and the standard word list |
| `c-port/` | The same calculation in C. Correct, but hours per key on a Gigatron; kept as a second implementation |
| `rom/` | The program chip: a small assembler, the generator for `lock.rom`, a simulator, and tests |
| `release/` | The chip image to burn, and its checksum |
| `module/` | The plug-in switch and light module: wiring and parts |
| `docs/` | Diagrams, the first-run guide, and the expected lights for the first test |

## Where to start

- **To build and try it:** [docs/first-run.md](docs/first-run.md), then [module/README.md](module/README.md).
- **To understand it:** [PROJECT.md](PROJECT.md) and the two diagrams in `docs/`.

## Checking the software

Needs Python 3 and a C compiler. The reference tests also use the Python packages `embit`, `qrcode`, `qrcodegen` and `zxing-cpp`.

```
python3 reference/test_keycalc.py     # the reference against published vectors
rom/build.sh                          # builds the simulator and lock.rom, compares with release/
python3 rom/test_lock_rom.py 8 4      # the chip image end to end (about 10 minutes)
```

`test_lock_rom.py N M` checks N phrases with inputs placed in memory and M phrases entered through the simulated switches.

To check the image file before burning:

```
cd release && sha256sum -c SHA256SUMS
```

## What the tests show

| Test | Result |
|---|---|
| Reference against BIP32, BIP39 and BIP84 vectors and a second library | Passes |
| Chip image, 12th word, fingerprint, key record, QR squares | Match the reference |
| Words entered on the simulated switches, results read from the simulated lights | Correct; an independent scanner reads the exact key record |
| Working memory when the result appears | Wiped |
| Time per key on the real clock speed | About two and a half minutes |

## Not yet proven

- Nothing here has run on real hardware.
- The port power pins (6 and 8) come from a contributed adapter board, not from the Gigatron schematic. Measure them first.
- The input register's one-pulse delay is allowed for in the program but unconfirmed on a kit.
