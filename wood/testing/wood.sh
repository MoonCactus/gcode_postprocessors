#!/bin/bash
set -e

input=${1-"wood_cylinder_source.gcode"}
f=$(echo $input| sed 's/_source//')

cp "$input" "$f"

python ../wood.py --grain 5 --scan-for-z-hop 0 --z-offset 50 --file "$f" -w M109

