#!/bin/bash
killall gnuplot > /dev/null 2>&1
set -e

input="colormix_cylinder_source.gcode"
random=${1-2}
speed=${2-100}
mixCount=3

function minmax
{
	sort -n | awk '
	BEGIN {
		c = 0;
		sum = 0;
	}
	$1 ~ /^[0-9]*(\.[0-9]*)?$/ {
		a[c++] = $1;
		sum += $1;
	}
	END {
		ave = sum / c;
		if( (c % 2) == 1 ) {
		median = a[ int(c/2) ];
		} else {
		median = ( a[c/2] + a[c/2-1] ) / 2;
		}
		OFS="\t";
		print "sum", sum, "count", c, "average", ave, "median", median, "min", a[0], "max", a[c-1];
	}
	'
}

if [[ ! -f $input ]]; then
	echo "You must provide the g-code source filename"
	exit
fi

f=$(echo $input| sed 's/_source//')
cp "$input" "$f"

python ../colormix.py --file $f --mix 3 --speed $speed --doc --random $random

for i in 0 1 2; do
	echo -n "M163 S$i: "
	grep "M163 S$i" $f | awk "{print \$3}" | minmax
done

grep ';mixing_plot' $f | awk '{print $2 "\t" $3 "\t" $4 "\t" $5}' | sed '0,/^0/d' > /tmp/mix.dat
gnuplot -p -e "
	set yrange [0 : 100];
	set xlabel 'Z height';
	set ylabel 'M163 weight';
	set termoption lw 2;
	set title 'Random $random, speed $speed';
	plot
		'/tmp/mix.dat' using 1:2 title 'C' with lines,
		'/tmp/mix.dat' using 1:3 title 'Y' with lines,
		'/tmp/mix.dat' using 1:4 title 'M' with lines;"
