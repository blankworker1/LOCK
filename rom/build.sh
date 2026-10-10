#!/bin/bash
# Builds the simulator and the chip image, then compares the image with release/lock.rom.
set -e
cd "$(dirname "$0")"
cc -O2 -o gtrun gtrun.c
python3 lock_rom.py
if cmp -s lock.rom ../release/lock.rom; then echo "lock.rom matches release/lock.rom"
else echo "lock.rom DIFFERS from release/lock.rom"; exit 1; fi
