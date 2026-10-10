# First run: from a new kit to the first key

Use test phrases only. This guide ends with the standard "abandon ... about" phrase, whose answers are published.

## What you need

- A Gigatron kit, built or assembled, with its stock program chip.
- A 5 V USB supply and a mini-USB cable.
- A VGA monitor, for the stock test only. LOCK itself uses no monitor.
- A programmer that handles the 27C1024 chip, and at least one blank 27C1024. If the chips have a window they can be erased under a UV lamp and reused.
- A multimeter.
- The module from [../module/README.md](../module/README.md), on a breadboard.

Not confirmed: which programmer the kit seller's "ROM programming kit" contains, and whether a game controller comes with the kit.

## Steps

1. **Build the kit** from its manual. The program chip sits in socket U7 and the memory chip in U36.
2. **Test with the stock chip.** Power on. The four board LEDs should run a pattern, and the monitor should show the menu. Do not go on until this works.
3. **Measure the controller port.** With power on and nothing plugged in, measure between pin 8 (black probe) and pin 6 (red probe). Expect about +5 V. If not, stop: the module wiring must follow what you measure.
4. **Check the image file.** It must be 131,072 bytes. Run `sha256sum -c SHA256SUMS` in `release/`.
5. **Burn the chip.**
   - Put a blank chip in the programmer.
   - Select the 27C1024 type that matches the marking on the chip.
   - Load `release/lock.rom` as a plain binary file. No byte swapping. The file has the same layout as the official Gigatron ROM files.
   - Run a blank check, program, then verify.
   - If the chip has a window, cover it with an opaque sticker.
6. **Swap the chip.** Power off. Lever the stock chip out of U7 a little at each end, and keep it safe. Fit the LOCK chip with its notch the same way round.
7. **Plug in the module** and power on.
8. **Check entry.** The mode lights show "entering" (both off). Move the switches: the 11 data lights above them should follow. If they follow but shifted by one place, the input register is not behaving as modelled; note which way and stop.
9. **First key.** Put every switch off. Press STORE 12 times: eleven times for "abandon" (word number 0) and once for coin flips 0000000. The count goes up by one each time. If you press STORE by mistake, BACK takes back the last entry.
10. **Wait.** The mode shows "busy" for about two and a half minutes.
11. **Read the 12th word.** The data lights should show `00000000011`. That is word number 3, "about".
12. **Read the rows.** Each row comes in four blocks, A to D. Press NEXT for each block and compare with [first-run-rows.txt](first-run-rows.txt). The block light shows which block you are on and the count shows the row. Block D has eight squares; the last three lights stay dark. That is 164 presses for the whole code. BACK steps back one block. After row 41 block D, NEXT returns to the 12th word.
13. **Scan your copy.** A phone should read:

```
[73c5da0a/84h/0h/0h]zpub6rFR7y4Q2AijBEqTUquhVz398htDFrtymD9xYYfG1m4wAcvPhXNfE3EfH1r1ADqtfSdVCToUG868RvUUkgDKf31mGDtKsAYz2oz2AGutZYs
```

One key per power-up. Power off and on to start again.

## If it does not work

| What you see | Likely cause |
|---|---|
| No lights at all on the module | Power pins wrong or not connected; check step 3 |
| Lights on but they do not follow the switches | DATA, LATCH or PULSE swapped; check pins 2, 3, 4 |
| Lights follow, shifted by one place | Input register timing differs from the model |
| Entry works, the result is wrong | Compare the 12th word first, then rows; report which differs |
| Board resets or goes dark when the module is plugged in | A short or wrong power wiring on the module; unplug and check pins 6 and 8 |
