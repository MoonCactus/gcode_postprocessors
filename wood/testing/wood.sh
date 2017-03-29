#!/bin/bash
set -e

input=${1-"wood_cylinder_source.gcode"}
f=$(echo $input| sed 's/_source//')

cp "$input" "$f"

python ../wood.py --file "$f"

