# The LOCK module

The switches, buttons and lights, on one unit that plugs into the Gigatron's 9-pin controller port. No other port is used.

Status: designed and modelled in the simulator. **Not built.** Build it on a breadboard first. A circuit board comes later, once the breadboard version has run on a kit.

Wiring diagram: [../docs/lock-module.svg](../docs/lock-module.svg). Front panel: [../docs/lock-fascia.svg](../docs/lock-fascia.svg).

## The front panel

![Front panel](../docs/lock-fascia.png)

- **11 switches** in a row, with **11 data lights** directly above them at the same spacing. Up is 1.
- **4 block lights**, A to D. A QR row has 41 squares and is shown a block at a time: A is squares 1 to 11, B is 12 to 22, C is 23 to 33, D is 34 to 41. In block D the last three data lights stay dark.
- **6 count lights**, read as a binary number: entries stored so far, or the QR row number.
- **2 mode lights.**
- **3 buttons:** STORE under the switches; BACK and NEXT on the right.

The drawing is a proposed layout at 250 by 124 mm with 15 mm between switches. Sizes are not final.

## The port

| Pin | Line | Direction | Use |
|---|---|---|---|
| 2 | DATA | into the Gigatron | reading switches and buttons |
| 3 | LATCH | out | data for the lights; "load" for the switches |
| 4 | PULSE | out | the clock for everything |
| 6 | +5 V | out | power for the module |
| 8 | 0 V | | ground |

Pins 2, 3 and 4 are from the official Gigatron sources. Pins 6 and 8 are from a contributed adapter board that takes the same controller. **Measure pins 6 and 8 on your board before connecting anything.**

## Parts

| Part | Quantity | Note |
|---|---|---|
| 74HC165 shift register | 2 | reads 16 inputs |
| 74HC595 shift register | 3 | drives 24 outputs, 23 used |
| LED, high efficiency | 23 | 11 data, 4 block, 6 count, 2 mode |
| Resistor, about 3.3 kΩ | 23 | one per LED, gives about 1 mA |
| Resistor, 10 kΩ | 14 | pull-ups for switches and buttons |
| Capacitor, 100 nF | 5 | one across the power pins of each chip |
| Toggle switch, on/off | 11 | the word |
| Push button | 3 | STORE, NEXT and BACK |
| 9-pin D plug and cable | 1 | to the controller port |

## Switches and buttons (two 74HC165)

Each switch or button connects its input to 0 V when closed or pressed. Each input also has a 10 kΩ resistor to +5 V. An unplugged module therefore reads as "everything off".

Chip A is the one whose output goes to the port.

| | Chip A | Chip B |
|---|---|---|
| Input H (pin 6) | word bit 7 | STORE |
| Input G (pin 5) | word bit 6 | NEXT |
| Input F (pin 4) | word bit 5 | BACK |
| Input E (pin 3) | word bit 4 | +5 V |
| Input D (pin 14) | word bit 3 | +5 V |
| Input C (pin 13) | word bit 2 | word bit 10 |
| Input B (pin 12) | word bit 1 | word bit 9 |
| Input A (pin 11) | word bit 0 | word bit 8 |
| SH/LD (pin 1) | LATCH | LATCH |
| CLK (pin 2) | PULSE | PULSE |
| CLK INH (pin 15) | 0 V | 0 V |
| SER (pin 10) | chip B's QH | +5 V |
| QH (pin 9) | port pin 2, DATA | chip A's SER |
| Power | pin 16 to +5 V, pin 8 to 0 V | same |

Word bit 10 is the leftmost switch and has the value 1024. Word bit 0 is the rightmost and has the value 1. For the coin-flip entry, the seven rightmost switches (bits 6 to 0) are used.

## Lights (three 74HC595 in a chain)

| Pin | Connect to |
|---|---|
| SER (pin 14) of chip #1 | LATCH |
| SER (pin 14) of chips #2 and #3 | QH' (pin 9) of the chip before |
| SRCLK (pin 11), every chip | PULSE |
| RCLK (pin 12), every chip | LATCH |
| OE (pin 13), every chip | 0 V |
| SRCLR (pin 10), every chip | +5 V |
| Power | pin 16 to +5 V, pin 8 to 0 V |

Each used output goes through its own resistor to an LED, and the LED's other leg to 0 V. Output pins: QA is pin 15, QB to QH are pins 1 to 7.

Which output drives which light:

| Chip | QA | QB | QC | QD | QE | QF | QG | QH |
|---|---|---|---|---|---|---|---|---|
| #1 | count 1 | count 2 | count 4 | count 8 | count 16 | count 32 | mode B | mode A |
| #2 | spare | block D | block C | block B | block A | data 11 | data 10 | data 9 |
| #3 | data 8 | data 7 | data 6 | data 5 | data 4 | data 3 | data 2 | data 1 |

Data light 1 is the leftmost, above the leftmost switch (word bit 10, value 1024). Data light 11 is above the rightmost switch (value 1).

### Status lights

| Mode A | Mode B | Meaning | The count shows |
|---|---|---|---|
| off | off | entering | entries stored so far |
| off | on | busy | nothing |
| on | off | 12th word | 12 |
| on | on | QR row | the row number, 1 to 41; a block light shows which quarter |

The count is six lights read as a binary number. On the front panel mode A is the left mode light and mode B the right.

## At power-on: the lamp test

Every time the machine is switched on it lights each of the 23 lights alone, slowly, in this order: data 1 to 11, blocks A to D, mode A, mode B, then count 32 down to 1. Each stays on for about 0.4 seconds. Then all 23 light together for about 1.6 seconds, and go dark. The whole test takes about 11 seconds, after which the machine is ready for the first word.

A light that does not come on in its turn, or two that come on together, means a wiring fault. Do not go on until the test runs clean.

The two timings are set by `LAMP_STEP` and `LAMP_ALL` in `rom/lock_rom.py`.

## The buttons

| Button | While entering | While showing results |
|---|---|---|
| STORE | stores the switch setting as the next entry | nothing |
| BACK | takes back the last stored entry | steps back one block |
| NEXT | nothing | steps on one block |

- Results run in a loop: 12th word, row 1 blocks A to D, row 2, and so on to row 41 block D, then the 12th word again. That is 164 presses of NEXT for the whole code.
- The 12th entry (the coin flips) starts the calculation at once, so it cannot be taken back. Check the switches before that last STORE.

## Power

The Gigatron's fuse holds 0.2 A and the board itself uses about 0.1 A. The module must stay well under 0.1 A.

- With 3.3 kΩ resistors each LED takes about 1 mA, so all 23 on is about 25 mA. Use high-efficiency LEDs so that 1 mA is bright enough.
- There is room for brighter lights: at 2 mA each the module still takes only about 50 mA.

## How the program drives it

- **Lights:** the program sets LATCH to each bit in turn and ticks PULSE, 24 times, then raises LATCH once more. That last rise copies all 24 bits to the outputs together.
- **Switches:** LATCH low loads the 16 inputs. LATCH high, then 17 ticks of PULSE, shifts them into the Gigatron: one extra tick first, because the Gigatron's input register shows its value one tick late.
- The program reads the switches and rewrites the lights about 40 times a second.
- A button counts as pressed when seen on two reads in a row, about 50 ms.

## Known limits

- Reading the switches also ticks the light chain, so the lights are rewritten straight after each read. They can show a wrong pattern for well under 0.1 ms in every 25 ms. This should not be visible. If it is, one more chip that separates the two functions would remove it.
- The one-tick delay of the input register is allowed for but not yet confirmed on a kit.
- The module model in `rom/gtrun.c` is my reading of the two chip types. The first breadboard run is the real test.

## Later: the circuit board

Not started. Open points for that stage:

- A plain two-layer board with through-hole parts, so every connection can be followed by eye.
- The board is also the face of the artifact, laid out as in the front panel drawing.
- Whether to add the extra chip that stops the brief wrong patterns.
