# LOCK

**A transparent key calculator. An Anonymous Art artifact.**

Status: outline, draft 0.13, 11 October 2026. No hardware is built. A complete program chip image exists and passes every test on a model of the Gigatron and of the plug-in module (section 7e). It has not run on a real board.

The keysmith cuts the key by hand; this machine derives the lock that the key fits.

---

## 1. What it is

A computer built only from simple logic chips, with no microprocessor, that does the one part of key cutting a person cannot do by hand.

- **In:** a seed made by hand (dice, switches).
- **Out:** the 12th (checksum) word, and the account public key (xpub) used to receive and to check a balance.

It does not sign transactions, read QR codes, connect to anything, or remember anything.

## 2. Why it exists

The btckeys ceremony makes the secret entirely by hand: dice for entropy, a hand-stamped steel plate. Two steps remain that need a machine:

| Step | By hand? |
|---|---|
| Checksum word | Possible but impractical (one SHA-256 pass) |
| xpub | No (about 4,100 hash passes, then elliptic-curve arithmetic) |

Today a SeedSigner does both. Its software is open, but the chip beneath it is not, and no one can inspect it. This artifact is a machine for the same two steps in which every part is small enough to understand and test.

It is the successor to **CHECKSUM** (the relay machine). CHECKSUM makes the checksum visible. This makes the lock-fitting visible.

## 3. Principles

1. **No hidden circuit.** Only simple logic chips, memory, switches and lights. Every chip can be tested completely on a bench before it is fitted.
2. **No hidden code.** The whole program is published, printable as a booklet, and can be read back out of the program chip and compared.
3. **Stateless by construction.** Working memory empties when power is cut. The board has no means of writing to its program chip.
4. **No way out.** No radio, no camera, no data port. Output is lights and a simple display, copied by hand.
5. **Generic parts.** Components sold in huge volumes for every purpose, bought from general distributors.
6. **Never trusted alone.** Its answers must match an independent calculation (section 8).

## 4. Scope

**In scope**

- Enter 11 words and 7 coin-flip bits on switches.
- Compute and show the 12th word.
- Compute the master fingerprint and the account xpub at `m/84'/0'/0'`.
- Show the xpub as a QR code, one row at a time, for copying by hand onto a printed grid.
- Show the progress of the calculation as it runs.

**Out of scope**

- Signing. Under the btckeys loop a key signs once, at the sweep, just before it is retired. An ordinary signer does that.
- QR scanning. The machine has no camera.
- Passphrases, multisig, other derivation paths. Possible later.

## 5. Where it sits in the ceremony

1. Dice give the entropy, including the seven final bits.
2. **LOCK takes the 11 words and 7 bits, and shows the 12th word and then the xpub QR code**, in one session of about two and a half minutes. It then holds nothing but those two results.
3. The keysmith hand-stamps the plate with all 12 words and checks it. The QR code is copied by hand onto a printed grid.
4. A second, independent machine confirms the 12th word and the xpub.
5. Plate sealed. xpub engraved on the outside.
6. Receive and circulate.
7. Break the seal, sweep to a freshly cut key, retire the old one.

## 6. The machine

**Input.** Eleven toggle switches, one word at a time, with a "store" button. Same left-to-right convention as CHECKSUM and BINARY. The machine shows each word as it is set, so the keysmith can confirm it.

**Compute.** A Gigatron-type board: an 8-bit processor made from about 35 74-series chips, one RAM chip, and one program chip (EPROM). Differences from a stock Gigatron:

- A LOCK program chip in place of the games ROM. No video or sound is generated.
- No keyboard adapter. The switches feed the input port directly.
- One plug-in module of simple chips for the switches and LEDs (section 6b).

**Output.**

- Eleven lights for the 12th word's switch pattern.
- The same eleven lights show the xpub QR code, one block of a row at a time, with four block lights (A to D), a row counter, and NEXT and BACK buttons. The code is 41 by 41 squares (the same size SeedSigner shows), so 41 rows are copied by hand onto a printed grid, as in the Slow Money game. No screen anywhere.
- Eight status lights: what the machine is doing, and a count (words entered, or the row number). There is no progress display during the calculation in this version.

**Housing.** Transparent, in keeping with CHECKSUM.

### 6b. The plug-in module (decided 10 October 2026)

Switches and lights go on one module that plugs into the Gigatron's existing 9-pin game controller port, like a keyboard adapter. No other port is used.

| Port pin | Line | Direction | Use |
|---|---|---|---|
| 2 | Data | into the Gigatron | reading the switches |
| 3 | Latch | out | data for the lights; "load" for the switches |
| 4 | Pulse | out | the clock for both |

Pin numbers for the three lines are from the official Gigatron sources. Power is expected on pin 6 (+5 V) and pin 8 (0 V): that is how a contributed adapter board in the official repository wires the same controller socket. Confirm both with a meter on the kit before plugging anything in.

Diagrams: `docs/lock-system.svg` (the board as LOCK uses it) and `docs/lock-module.svg` (module wiring). The full wiring, pin by pin, is in `module/README.md`.

- Switches and buttons: two 74HC165 chips (16 inputs: 11 switches, STORE, NEXT, BACK).
- Lights: three 74HC595 chips driving 23 LEDs: 11 data lights above the 11 switches, 4 block lights (A to D), 6 for a count and 2 for the mode. Each chip holds its outputs until told to update.
- Decided 10 October 2026: 11 data lights, not a row of 41. A QR row is shown in four blocks: A = squares 1 to 11, B = 12 to 22, C = 23 to 33, D = 34 to 41. This roughly halves the module (5 chips, not 9) at the cost of 164 presses for the whole code, not 41. The front panel is drawn in `docs/lock-fascia.svg`.
- LEDs, not filament bulbs. The board's own fuse holds 0.2 A and the board itself draws about 0.1 A. With 23 high-efficiency LEDs at about 1 mA each the module takes roughly 25 mA with every light on, well inside that.
- The Gigatron's own four LEDs change whenever the Pulse line ticks and can serve as a progress display.

**How the program expects the module to be wired**

| Item | Detail |
|---|---|
| Inputs | 16, read as two bytes. A closed switch or pressed button reads as 0 at the chip (pull-up resistors), so an unplugged module reads as "everything off" |
| First byte in | word bits 7 to 0, bit 7 first |
| Second byte in | STORE, NEXT, BACK, two unused (tied high), then word bits 10, 9, 8 |
| Lights | 24 outputs in one chain, sent as: the 11 data lights left to right, block lights A B C D, 1 unused, then 8 status lights |
| Status lights | two for the mode (entering, busy, 12th word, QR row) and six for a count in binary |

**Using it**

1. Power on. The lamp test runs for about 11 seconds: each light on its own in turn, then all together, then dark. Set the 11 switches to a word's pattern; the 11 data lights follow the switches. Press STORE. The count goes up by one. BACK takes back the last entry.
2. Repeat for all 11 words. For the 12th entry, set the seven right-hand switches to the coin-flip bits and press STORE.
3. The lights go dark and the mode shows "busy" for about two and a half minutes.
4. The data lights show the 12th word's pattern. Press NEXT.
5. The data lights show block A of row 1, the block light A is lit, and the count shows the row number. Copy the block and press NEXT for B, C and D, then on to the next row. Block D has eight squares; the last three lights stay dark. After row 41 block D, NEXT returns to the 12th word, so everything can be checked a second time. BACK steps the other way.
6. Power off, or reset to start again. One key per power-up.

**Known limits of this module design**

- Reading the switches disturbs the light chain, so the program rewrites the lights straight after every read, about 40 times a second. For roughly 0.1 ms each time the lights can show a wrong pattern. That is about half a percent of the time and should not be visible; if it is, one more simple chip separating the two functions would remove it.
- The Gigatron's input register is a 74HC595 with both of its clocks on the Pulse line, so the value the program reads is one pulse behind. The official emulator leaves this out; two loader programs in the official repository allow for it. Since draft 0.10 the program sends one extra pulse before reading and the module model includes the delay. Still to be confirmed on a kit.
- Button presses are accepted when seen on two reads in a row, about 50 ms.
- The 12th entry starts the calculation at once, so BACK cannot take it back.

### 6a. Candidate boards (surveyed October 2026)

| Board | Logic chips | Speed | Fits arithmetic? | Can it write its own program memory? | Software route | How to get one |
|---|---|---|---|---|---|---|
| Gigatron | about 35 | 6.25 MHz, most of it spent on video | Poorly: 17 instructions, no carry, no shifts | No (EPROM) | C compiler exists (GLCC) | Kits from small sellers; open design |
| Minimal 64x4 | 57 | 8 MHz, about 1.85 million instructions a second | Well: carry flag, word and long operations | Yes, as built (flash file store) | Assembler and emulator; no C compiler | Build from the published files; no official kit |
| Isetta | 51 | 12.5 MHz | Well: runs 6502 and Z80 code | Yes, as built (flash microcode, SD card) | Mature C compilers for 6502 and Z80 | Kit from its maker (Netherlands) |
| Novasaur | 34, plus one PAL | about 3.5 million native instructions a second | Via an 8080 interpreter | No (ROM) | CP/M tools | Kit uncertain |

None is usable unchanged, but the Gigatron needs the least done to it.

**Gigatron as the base (confirmed by the native hash measurement, section 7b).**

- Its program chip is an EPROM, written only in a separate programmer and erased only by ultraviolet light. Principle 3 is met as built.
- Its video and sound are produced by software, not by dedicated chips. A LOCK program that never draws a screen removes them with no change to the board, and gives the whole 6.25 MHz to arithmetic.
- Native code runs only from the program chip. For a general computer that is a limitation. For LOCK it is the intended design.
- It has the fewest chips, the most documentation, an emulator, and kits on sale.
- The cost: its instruction set is weak for this arithmetic, so the routines are hand-written in native code, with shifts done by table lookup and carries worked out from top bits. Measured for the heavy hash: 64 seconds per key (section 7b).
- Leave off the keyboard adapter, which contains a microcontroller. Switches go to the input port.
- Add the plug-in module for the switches and lights (section 6b).

**Minimal 64x4** was the alternative in case the Gigatron proved too slow. The native hash measurement (section 7b) shows it is not needed.

**Isetta** is the fallback if hand-written code proves too much. **Novasaur** is ruled out by its programmable logic chip.

**Buying.** A kit is right for the proof. For the artifact itself, use the open design files and source the chips from a general distributor, each tested on the bench.

**Program chip contents.** The program, the 2,048-word list (about 13K; the words are needed as text, not only as numbers), and any speed-up tables.

## 7. The program

A reference version exists: `keycalc.py`, about 500 lines, standard library only. Each routine is written plainly so it can be translated one-for-one.

| Routine | Used for | Times run per key |
|---|---|---|
| SHA-256 | checksum word; fingerprints; xpub text checksum | 9 passes |
| SHA-512 (keyed) | the 2,048 rounds; each derivation step | 4,114 passes |
| RIPEMD-160 | fingerprints | 2 passes |
| 256-bit multiply | curve arithmetic | about 11,000 |
| Curve multiplication | master, parent and account public keys | 3 |
| Base58 | writing the xpub as text | 1 |
| QR encoding | turning the text into the 41 by 41 pattern | 1 |

Counts are measured from the reference on the standard test phrase.

**Tested against** (`test_keycalc.py`, all passing):

- Python's own hash library, for every hash routine.
- The published vectors in the BIP32, BIP39 and BIP84 documents.
- 40 random seeds against the embit library (the one SeedSigner, Krux and Specter use).
- The QR pattern, square for square, against two other QR programs, and read back by a scanner.

**Copying slips.** In tests, a grid with 10 squares copied wrong still scanned correctly every time. With 20 wrong it mostly failed to scan. It never scanned as a different key, and the xpub carries its own checksum as a second guard.

**Estimated work on an 8-bit machine**

| Part | Instructions | Share |
|---|---|---|
| 2,048 rounds and derivation | about 430 million | 64% |
| Curve arithmetic | about 240 million | 36% |
| Everything else | under 1 million | |
| **Total** | **about 670 million** | |

| Machine speed | Time per key |
|---|---|
| 0.25 million instructions a second | about 45 minutes |
| 1 million | about 11 minutes |
| 3 million | about 4 minutes |

This is a model, not a measurement. It assumes three instructions per byte-wide step and a table-lookup multiply. Phase 1 replaces it with a real count.

**Known ways to make it faster**

- A precomputed table for the curve's base point (about 64K of ROM) cuts the curve work by roughly two thirds.
- A shorter route for the final division (255 squarings and 15 multiplies, not 500).
- The hash rounds cannot be shortened. They are the floor: about 7 minutes at 1 million instructions a second.

### 7a. The whole program on a simulated Gigatron (10 October 2026)

The full calculation now exists in C (`c-port/lock.c`, about 700 lines), compiled with the Gigatron C compiler (GLCC) and run in its command-line simulator. The simulator executes the real Gigatron ROM image, so this is the Gigatron's own logic running the code.

**Result: four complete runs, every output line identical to `keycalc.py`**, from the 12th word to the last row of the QR code. The QR codes the simulated Gigatron produced were also read back by a scanner.

| Run | ROM | Test phrase | Simulated time |
|---|---|---|---|
| 1 | Stock (v5a) | abandon x11 | 8 h 55 min |
| 2 | Newer (dev7) | abandon x11 | 2 h 10 min |
| 3 | Newer (dev7) | legal winner thank year... | 2 h 12 min |
| 4 | Newer (dev7) | a random phrase | 2 h 11 min |

Where the time goes:

| Stage | Stock ROM | Newer ROM |
|---|---|---|
| 12th word | 1.4 s | 0.4 s |
| The 2,048 rounds | 5 h 29 min | 75 min |
| Three public keys and the derivation steps | 3 h 24 min | 54 min |
| xpub and zpub as text | 46 s | 14 s |
| QR code, all eight masks scored | 81 s | 40 s |

Times are with the screen mostly blanked (video mode 3).

Also checked: the same `lock.c` built for a PC matches `keycalc.py` line for line on 200 seeds, and runs clean under memory and arithmetic checkers.

**What this proves.** Every routine is correct on a 16-bit machine with the Gigatron's logic, end to end, including the QR code.

**What it does not prove.**

- Speed. Compiled C runs through the Gigatron's built-in interpreter while the machine also draws video. Hours per key is the cost of that route, not of the hardware.
- Fit on a real kit. As written the program needs the simulator's flat 64K memory layout. It does not fit a stock 32K Gigatron, nor (by a small margin) a 64K one with its screen memory reserved.
- The physical board, the switches, or the bulbs.

**What follows.** The artifact's program has to be native code in its own program chip, with no video and the word list in ROM. The C version is now the checked blueprint for that, and the same simulator can run a custom ROM image against the same test phrases.

### 7b. The heavy hash as native Gigatron code (10 October 2026)

One SHA-512 pass was written directly in the Gigatron's own 17 instructions (`rom/sha512_rom.py`) and run on the reference CPU model from the official Gigatron repository, where one step is one tick of the real machine's 6.25 MHz clock.

| Measure | Result |
|---|---|
| Published example, SHA-512("abc") | Correct |
| 300 random and extreme blocks | All match `keycalc.py` |
| A full 2,048-round seed (4,098 passes) | Matches the standard |
| One pass | about 97,000 ticks = 15.5 ms |
| All 4,114 passes of one key | **64 seconds** |
| Start-up (building the lookup tables) | 8 ms |
| Working memory used | 6K of the stock 32K |
| Program chip used | 24,274 of 65,536 words (37%) |

For comparison, the same 4,114 passes took 75 minutes as compiled C on the newer ROM and 5.5 hours on the stock ROM. The earlier paper estimate was 426 million instructions; the measured figure is 398 million ticks.

**Decision this settles.** The Gigatron is fast enough. It stays the base, and the Minimal 64x4 is not needed.

**How it gets its speed.** The CPU cannot shift or carry, so shifts are table lookups in RAM and carries are worked out from the top bits. The 16 rounds of each cycle are written out one after another, so every memory address is fixed in advance.

**Limits of this test.**

- Only the hash routine is native. The test script prepared each block and copied the results, standing in for glue code not yet written. That glue is small: a few seconds per key at most.
- Speed was bought with chip space. With the word list (about 13,000 words) the two together fill 57% of the program chip. If space runs short, the hash can be made roughly half the size by running slower.
- The curve arithmetic was measured next: see section 7c.
- It is a model of the CPU, not the physical board.

### 7c. The curve arithmetic as native Gigatron code (10 October 2026)

The step from private key to public key was written in native code (`rom/curve_rom.py`) and run on the same reference CPU model.

| Measure | Result |
|---|---|
| 256-bit multiply, 250 cases including extremes | All correct, about 44,000 ticks = 7 ms each |
| Add, subtract, copy, 250 cases each | All correct, 0.4 ms or less |
| Whole public keys: 1, 2, 3, the largest valid key, and 40 random keys | All 45 match `keycalc.py` |
| One public key from a random private key | 25 to 28 seconds, average 26.8 |
| The three public keys one LOCK calculation needs | **about 80 seconds** |
| Start-up (building the multiplication tables) | 48 ms |
| Working memory used | 20K of the stock 32K |
| Program chip used | 4,861 words (7.4%) |

In compiled C the same three keys took 54 minutes on the newer ROM and 3 hours 24 minutes on the stock ROM.

**How it works.** Byte times byte is four table lookups, with the multiplier split into two nibbles. The multiply goes one byte at a time and, after each, adds the multiple of the prime that clears the lowest byte, so the running value never exceeds 33 bytes (Montgomery's method). The point formulas are stored as short lists of multiply, add and subtract steps and run by a tiny interpreter, so they read the same as in `keycalc.py` and `lock.c`.

**Where a whole key now stands**

| Part | Time | Program chip |
|---|---|---|
| The 2,048 rounds and derivation hashing (measured) | 64 s | 37% |
| Three public keys (measured) | 80 s | 7% |
| Word list (planned) | | about 20% |
| Small hashes, text, QR, glue, switches and bulbs (not yet written) | a few seconds, estimated | from the remaining 36% |
| **Whole key** | **about two and a half minutes** | |

**Limits of this test.** The routine is complete from private key to public key, but the test script supplied the key and read the answer. Known savings not yet taken: a shorter route for the final division would cut roughly 10 seconds. It is a model of the CPU, not the physical board.

### 7d. Block A: all the cryptography in one chip image (10 October 2026)

`rom/lock_rom.py` builds a single program chip image that goes from 11 word numbers and 7 coin-flip bits to the account public key, entirely in native code:

12th word, the words as text, the 2,048 rounds, master key, three derivation steps, both fingerprints, and the account public key.

| Measure | Result |
|---|---|
| Whole calculation, 10 phrases (2 standard, 8 random) | All match `keycalc.py`: 12th word, master fingerprint, and the 74-byte key record |
| Time per key | **145 to 149 seconds (about 2.4 minutes)** |
| SHA-256 on its own, 10 message lengths | All correct, 16 ms at most |
| RIPEMD-160 on its own, 20 inputs | All correct, 9 ms |
| Start-up | 11 ms |
| Program chip used | 48,452 of 65,536 words (74%) |

New in this block: SHA-256 and RIPEMD-160 (written small and slow on purpose, since they run only a handful of times), the keyed-hash and 2,048-round loops, the derivation arithmetic, the word list, and the joining of the earlier hash and curve code into one image.

Inputs and results still sit in RAM, read and written by the test script. The word list is unpacked into RAM at the start and its space is reused by the multiplication tables once the words have been turned into text.

### 7e. Block B: the complete chip image (10 October 2026)

`rom/lock_rom.py` now builds the whole machine: word entry on the switches, the calculation, the key as text, the QR code, and the display on the lights. The runner (`rom/gtrun.c`) gained a model of the plug-in module so the image can be driven exactly as a person would drive it.

| Test | Result |
|---|---|
| Calculation with inputs and results in memory, 8 phrases | All match `keycalc.py`: 12th word, fingerprint, key record, the 111-character zpub, the descriptor, and all 1,681 squares of the QR code |
| The whole machine through the module model, 3 phrases (11-light module) | Words entered on the switches; the 12th word and all 164 blocks read back from the lights; BACK takes back an entry and steps back through the blocks; all correct |
| Independent scan of the code read from the lights | Reads back the exact descriptor, all 3 times |
| Working memory after the result is shown | Wiped: the pages that held words, seed and keys read as zero |
| Time from the last STORE to the 12th word appearing | 145 to 150 seconds |
| Text and QR code, of that | 0.14 seconds |
| Program chip used | 52,814 of 65,536 words (81%) |
| Working memory | fits the stock 32K |

The QR code uses fixed mask 0, so the comparison is against `keycalc.py` with that mask chosen.

**What has and has not been shown.** The program is complete and correct on a faithful model of the Gigatron's CPU. The module model follows my reading of the port and of the two chip types. No real chip has been burned, no module built, and the points in section 6b need checking on real hardware.

## 8. Verification and trust statement

The machine's outputs have exactly one right answer each, so they can be checked from outside.

| Layer | How it is assured |
|---|---|
| Program logic | Published; tested against vectors; matches the reference |
| Program chip contents | Read back and compared with the published listing |
| Logic chips | Each tested fully on a bench |
| Memory chips | Tested by pattern; denser than logic, so assumed honest beyond that |
| Each result | Must match an independent machine (SeedSigner or offline Bitcoin Core) |

What this does not claim: that no trust remains. It claims that nothing has to be taken on faith by a single party.

## 9. Phases

| Phase | Work | Output | Decision it informs |
|---|---|---|---|
| 0 | Reference program and tests | Done | Is the job well defined? Yes |
| 1a | The program in C, run on a simulated Gigatron | Done: correct end to end, hours per key | Is the logic right on this machine? Yes |
| 1b | The heavy hash as native Gigatron code | Done: 64 seconds per key for the hash | Is the Gigatron fast enough? Yes |
| 1c | The curve arithmetic as native Gigatron code | Done: 80 seconds for the three public keys | Is a whole key practical? Yes, about two and a half minutes |
| 1d | Block A: all the cryptography joined into one chip image | Done: 2.4 minutes per key, 74% of the chip | Does it fit and agree end to end? Yes |
| 1e | Block B: key text, QR code, and the switch and light module | Done: a complete chip image, correct end to end in simulation | Ready to try on a kit? Yes |
| 2 | Burn the image, build the module on a breadboard, run on a Gigatron kit | A working proof | Does it work on real logic chips? Do the input register and the port power pins behave as modelled? |
| 3 | Design the plug-in switch and LED module; source and test chips for the final build | Schematics, PCB files | Commit workshop time? |
| 4 | Build, test, housing, printed program | The artifact | |

Phases 1 and 2 cost little. Phase 3 is the commitment point.

## 10. Relation to other work

- **btckeys / Keysmith ceremony:** this is its long-term calculator. The pilot continues with SeedSigner.
- **CHECKSUM (ASRC):** same no-hidden-circuit rule, same switch and light conventions. CHECKSUM could remain the checksum machine, with LOCK doing only the xpub.
- **BINARY and the Slow Money game:** the same 11-switch word entry.
- **Repository:** its own repository, separate from the Anonymous Art repo (decided 10 October 2026).

## 11. Open questions

2. Program chip space: the fast hash uses 37% of the chip. Decide later whether to trade some speed for space.
3a. QR mask: decided. The chip uses one fixed pattern (mask 0) with no scoring. Its code scans to the same text as any other but will not match another program's picture square for square.
3. Is there a C compiler for the chosen design, or is the program hand-written?
4. Checking a hand-copied QR: 1,681 squares leave room for slips. A second read-through, or a scan by the watch-only wallet, before the plate is sealed.
5. Program chip type: one that can only be written in a separate programmer.
6. Does the machine also show the first receive address, as a second check?
7. Who reviews the program? It will be new, unaudited code.
8. Collaborator for digital design and low-level code.
9. Side channels (power draw, emissions) while the seed is in memory: in scope for the ceremony room rules, not the machine.

## 11a. Questions for the kit vendor (to send before ordering)

1. Board size, and the positions and diameter of its mounting holes. Needed before the module's front panel is redrawn to the same outline (235 by 160 mm is reported by one builder, unconfirmed).
2. Height of the tallest part on the assembled board, and the inside dimensions of the wooden case.
3. Which programmer is in the "ROM programming kit", and whether the spare chips have a window (erasable) or not.
4. Whether a game controller is included. It is needed for the stock test only.
5. The controller connector on the board: plug or socket, and confirmation that pin 6 is +5 V and pin 8 is 0 V.
6. The LEDs on the board: size, colour and part number, so the module's lights can match them.

## 11b. The module as a wired control panel (decisions of 10 and 11 October 2026)

This replaces the earlier plan of lights and switches soldered straight to the board.

Decided:

- One circuit board, about 2.4 mm thick, used as a control-panel face. Legends printed on the front. Panel-mount switches, buttons and lamps bolt through holes in it.
- Lamps: panel indicator LEDs in threaded bezels, with built-in resistor and ready-made wire tails. Not bright.
- Lamp-driver chips (ULN2803 type, one beside each 74HC595) carry the lamp current. The program is unchanged.
- All chips in sockets, on the back of the board. Sockets, terminal blocks and small parts soldered by the board assembler; chips bought, tested and fitted by hand.
- On copper: power, and all links between chip sockets, resistors and terminals.
- On wires: every switch, button and lamp. Each wire lands on a screw terminal on the back of the board. Terminals are numbered or lettered in print on the board.
- Wires are made up to length in chosen colours (two-colour wire where useful): a push-on connector at the switch or button end, a crimped sleeve at the screw-terminal end. Switches and buttons are therefore the type with push-on tabs.
- All wiring is on the back of the fascia, with a much larger gap between the two boards so that it is on show.
- Power from six rechargeable AA cells in a holder on the back of the board, charged outside the machine. A low-dropout 5 V regulator (with a small heatsink), a fuse and a power switch. A USB outlet (power pins only) feeds the Gigatron. The module takes its 5 V from the regulator, not from the controller port.
- Eight holes in the fascia: four matching the Gigatron's mounting holes, for the pillars, and four at the corners, for fixing to a transparent box. The whole unit hangs from the fascia; the box is a cover.
- A European board maker and assembler is preferred.
- A buffer chip (74HC14 type, in a socket) where the port cable lands, to clean up the PULSE and LATCH signals before they reach the five shift-register chips. Test points for PULSE, LATCH and DATA.
- A power switch on the front of the fascia. It is also the "start again" control, since the machine does one key per power-up.
- Protection against a cell fitted backwards: a diode beside the fuse.
- A few spare screw terminals, and the one spare lamp output brought out to a terminal.
- The transparent box has a lid and a padlock.
- Two more lamps on the fascia that the program does not control: POWER, and BATTERY LOW driven by a voltage comparator on the battery side of the regulator. That makes 25 lamps.
- A slow lamp test at power-on, as part of the look of the piece: each of the 23 program lamps alone for about 0.4 seconds, then all together for about 1.6 seconds. In the chip image since draft 0.12.

Proposed, not yet decided:

- Fascia about 300 by 185 mm; the battery holder under the left end, clear of the Gigatron.
- Gap between the boards about 70 mm, giving a unit about 100 mm tall. Pillars of threaded rod through tube spacers.
- Switch and lamp spacing: 15 mm, or about 19 mm for a more vintage look.
- Cable to the controller port: flat ribbon with a ribbon-type 9-pin connector at the Gigatron end; right-angle plug on the USB power lead.
- Battery change by lifting the unit out of the box (four thumbscrews), then turning it over.
- Terminal labels by group: S1 to S11 switches, B1 to B3 buttons, L1 to L11 data lamps, A to D block lamps, C1 to C6 count lamps, M1 and M2 mode lamps, P for power.

Rough counts: 25 lamps and 14 switches and buttons give about 80 wires and about 85 screw terminals.

To check on samples before buying in quantity: the current and brightness of the chosen lamp at 5 V through a driver; that the chosen switches and buttons have push-on tabs of a standard size.

Waiting for: the vendor's board size, hole positions and part heights (11a). Order of work: breadboard proof on the kit, then a wiring schedule, then schematic and layout in KiCad, then the board order.

Tools the kit needs besides a small screwdriver: a spanner for the lamp and switch nuts, and a crimp tool for the lamp tails unless the supplier fits sleeves.

## 11c. Trust points of the wired panel

- Sealed lamps. A panel lamp with a built-in resistor is the one part that cannot be seen into. The risk is judged very small, but it is a departure from "nothing hidden" and is stated here for that reason. A plain LED with a visible resistor would remove it.
- Easy to rewire. A panel wired with a screwdriver can be changed with one. The slow lamp test and the echo of the switches on the data lamps show a swapped or loose wire. They would not show something deliberately added. The padlocked box, with seals as in the ceremony rules, covers that.
- Switches hold the last entry. After the 12th STORE the switches still show the coin flips. Ceremony rule: return all switches to 0 once the calculation has started.
- The data lamps show each word as it is entered, to anyone who can see the panel. This is by design and is a matter for the room, not the machine.
- Chips are bought, tested and fitted by hand, in sockets, so the assembler never handles them.

## 11d. Known gaps (11 October 2026)

Not yet proven:

1. Nothing has run on real hardware. The port's power pins, the input timing and the lamps through their drivers are from documents and simulation. The breadboard proof on a kit comes before any board order.
2. Signal quality of PULSE and LATCH over the cable. The buffer chip and test points are the provision for it.
3. The battery supply: regulator choice, heat, the low-battery threshold and the running time are estimates.

Not yet decided:

4. Switch and lamp spacing (15 or about 19 mm).
5. The gap between the boards (about 70 mm proposed).
6. Fascia colour and legend colour, from what the board maker offers.
7. Which European maker. Open questions for them: a 2.4 mm board of this size, large panel holes, and soldering of sockets and terminal blocks.
8. Licence. Deferred until after the first run.

Not yet done:

9. Vendor questions sent (11a).
10. Samples tested: one lamp and one switch before buying in quantity.
11. Wiring schedule, schematic and board layout.
12. Fascia drawing redrawn for the panel-mount design, with the POWER and BATTERY LOW lamps and the power switch.
13. An independent review of the chip program.
14. The repository set to private.

Cost: panel lamps, tab switches, terminal blocks and made-up wires will cost more than board-mounted parts. A rough guess is 100 to 150 euros of parts per unit, unverified.

## 12. Files

| Folder or file | What it is |
|---|---|
| `README.md` | Overview, status, layout, how to run the tests |
| `PROJECT.md` | This outline |
| `reference/keycalc.py` | Reference program. Test vectors only: never enter a real seed on a networked computer |
| `reference/test_keycalc.py` | Tests for the reference |
| `reference/bip39_english.txt` | The standard word list (checked against its published hash) |
| `c-port/lock.c` | The whole calculation in C, for a PC or the Gigatron |
| `c-port/tables.h` | Constants and word list for `lock.c`, generated |
| `c-port/make_tables.py` | Generates `tables.h` from `keycalc.py`, so no constant is typed by hand |
| `c-port/check_c.py` | Compares a build of `lock.c` with `keycalc.py`, line for line |
| `c-port/run_sim.sh` | Runs one key calculation in the Gigatron simulator |
| `rom/gtasm.py` | A small assembler for the Gigatron's native instructions |
| `rom/lock_rom.py` | Builds the complete LOCK chip image (`lock.rom`) |
| `rom/test_lock_rom.py` | Checks the chip image end to end and reports its timing |
| `rom/gtrun.c` | Runs a ROM image on the official CPU model, with a model of the plug-in module, and counts clock ticks |
| `rom/build.sh` | Builds the simulator and the image and compares the image with `release/lock.rom` |
| `rom/sha512_rom.py`, `rom/test_sha512_rom.py` | The heavy hash on its own, with its test (stage 1b) |
| `rom/curve_rom.py`, `rom/test_curve_rom.py` | The curve arithmetic on its own, with its test (stage 1c) |
| `release/lock.rom`, `release/SHA256SUMS` | The chip image to burn, and its checksum |
| `module/README.md` | The plug-in module: wiring, parts, power |
| `docs/first-run.md` | From a new kit to the first key |
| `docs/first-run-rows.txt` | The expected lights for the first test |
| `docs/lock-system.svg`, `docs/lock-module.svg`, `docs/lock-fascia.svg` | The system, the module wiring and the module's front panel; `docs/make_diagrams.py` draws them |

To repeat the simulator runs of the C port: build GLCC from github.com/lb3361/gigatron-lcc, then in `c-port/` run `glcc -rom=dev7 -map=sim,allout lock.c -o lock_dev7.gt1` and feed 11 word numbers and the 7 bits (as a number 0 to 127) to `gtsim`.
