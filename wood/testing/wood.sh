#!/bin/bash
killall gnuplot > /dev/null 2>&1
set -e

input="wood_cylinder_source.gcode"
random=${1-2}
speed=${2-100}
mixCount=3

f=$(echo $input| sed 's/_source//')
cp "$input" "$f"

python ../wood.py --file $f
