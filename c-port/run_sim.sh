#!/bin/bash
# usage: run_sim.sh NAME ROM VIDEOMODE "11 word numbers and bits"
GLCC=${GLCC:-$HOME/gigatron-lcc}; G=$GLCC/build; R=$GLCC/gigatron/roms   # set GLCC to your gigatron-lcc folder
cd "$(dirname "$0")"; mkdir -p runs
s=$(date +%s)
echo "$4" | stdbuf -oL $G/gtsim -rom $R/$2.rom -vmode=$3 lock_$2.gt1 > runs/$1.out 2> runs/$1.err
echo "EXIT $? REAL $(( $(date +%s) - s )) s" >> runs/$1.err
