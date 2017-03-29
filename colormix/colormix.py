#Name: Colormix
#Info: Randomly mixes colors (or switches tool) in a continuous way along the Z axis.
#Depend: GCode
#Type: postprocess
#Param: mixCount(float:3) Either number of materials to mix (usually 3)
#Param: toolCount(float:0) Or the number of switchable tools (0=off, up to 15)
#Param: mixSpeed(float:1.0) Rate of change (the bigger the faster)
#Param: randomSeed(float:2) Start value of the pseudo-random, repeatable texture.

import inspect
import sys
import getopt
import re
import math
import random

__author__ = 'Jeremie Francois (jeremie.francois@gmail.com)'
__date__ = '$Date: 2016/05/24 18:24:13 $'
__license__ = 'GNU Affero General Public License http://www.gnu.org/licenses/agpl.html'

# ########### BEGIN CURA PLUGIN STAND-ALONIFICATION ############
# More info on http://www.tridimake.com/2013/02/how-tun-run-python-cura-plugin-without.html
#
# To run it you need Python, then simply run it like
#   mixing.py --file gcodeFile
#   mixing.py --toolCount 15 --file gcodeFile
# It will "patch" your gcode file with the appropriate Tn tool changes (15 by default)
#
#   mixing.py --mix 3 --file gcodeFile
# Change the weights of 3 mixed materials (http://reprap.org/wiki/G-code#M163:_Set_weight_of_mixed_material)
#
# Use --random followed by an integer to change the shape of the generated random pattern
#
# Latest version: 20151001-191033
#

def plugin_standalone_usage(my_name):
    print("Usage:")
    print("  "+my_name+" --file stringGcodeFile --extruders integerToolCount --random 123 ")
    print("  "+my_name+" --file stringGcodeFile --mix integerNozzleCount --speed integerPercentage --random 123 )")
    print("Licensed under CC-BY-NC 2012-2015 by jeremie.francois@gmail.com (www.tridimake.com)")
    sys.exit()
try:
    # this variable is defined only when we are being called within Cura
    filename
    insertPlotData=1  # debug for gnuplot
except NameError:
    # Then, we are called from the command line (not from Cura)
    # trying len(inspect.stack()) > 2 would be less secure btw
    opts, extraparams = getopt.getopt(
        sys.argv[1:],
        'x:m:s:r:f:hd',
        ['extruders=', 'mix=', 'speed=', 'random=', 'file=', 'help', 'doc'])

    filename = ""

    toolCount = 0
    mixCount = 3
    mixSpeed = 1.0
    randomSeed = 2
    insertPlotData = 0

    for o, p in opts:
        if o in ['-f', '--file']:
            filename = p
        elif o in ['-x', '--extruders']:
            toolCount = int(p)
        elif o in ['-m', '--mix']:
            mixCount = int(p)
        elif o in ['-s', '--speed']:
            mixSpeed = float(p)/100
        elif o in ['-r', '--random']:
            toolCount = int(p)
        elif o in ['-d', '--doc']:
            insertPlotData = 1
    if not filename:
        plugin_standalone_usage(inspect.stack()[0][1])

#
# ########### END CURA PLUGIN STAND-ALONIFICATION ############

def get_value(line, key, default=None):
    if (key not in line) or (';' in line and line.find(key) > line.find(';')):
        return default
    sub_part = line[line.find(key) + 1:]
    m = re.search('^[0-9]+\.?[0-9]*', sub_part)
    if m is None:
        return default
    try:
        return float(m.group(0))
    except ValueError:
        return default

mixCount = int(mixCount)
toolCount = int(toolCount)

random.seed(randomSeed)

with open(filename, "r") as f:
    lines = f.readlines()

# Find the total height of the object
maxZ = 0
z = 0
for line in lines:
    gv= get_value(line, 'G', None)
    if gv is not None and (gv == 0 or gv == 1):
        z = get_value(line, 'Z', z)
        if maxZ < z:
            maxZ = z

#print("Max Z is %i" % maxZ)

lastExtruder = -1

#lastMixes = [-1] * mixCount
lastMixes = [-1 for _ in range(mixCount)]
speedRatio = [0.5 + random.randint(0,100)/100.0 for _ in range(mixCount)]
mixOffsetDegrees = [360*random.randint(0,100)/100.0 for _ in range(mixCount)]

# lines to remove from the source code
regexToRemove = '^\s*(;mixing|'
if toolCount > 0:
    regexToRemove += 't[0-9]*$'
else:
    regexToRemove += 'm163|m164'
regexToRemove += ')'


def mixCycle(normalizedIndex, speed, offsetDegree):
    "Returns a normalized cyclic value"
    angle = 2*math.pi * normalizedIndex
    offset = 2*math.pi * offsetDegree / 360
    amplitude = (1.0 + math.cos(angle * speed + offset))/2.0
    return int(math.floor(100 * amplitude))


fout = open(filename, "w")
with fout as f:
    f.write(";mixing : ")
    if mixCount == 0:
        f.write("switching among {0} tools, every {1:.2f}mm".format(toolCount, maxZ/toolCount))
    else:
        f.write("mixing {0} materials along Z axis".format(mixCount))
    f.write(" (total height is {0:.2f}mm)\n".format(maxZ));

    for line in lines:
        gv= get_value(line, 'G', None)
        if gv is not None and (gv == 0 or gv == 1):
            z = float(get_value(line,'Z',z))
            if mixCount == 0:
                # switches "tools", that need to be pre-configured for specific mixing levels
                # The change in tool index is continuous so you can pre-define shades.
                zn = z / maxZ  # we need a normalized value
                #print("Z={0}".format(zn))
                extruder = int(toolCount * zn)
                if extruder != lastExtruder:
                    lastExtruder = extruder
                    f.write("T%i\n" % extruder)
            else:
                # z is not divided by maxZ as stripes thickness should stay independent of the geometry!
                # compute all 3 offsets for this Z
                mf = [0.0] * mixCount
                t = 0.0
                for i in range(mixCount):
                    a = mixCycle(z * mixSpeed / 20, speedRatio[i], mixOffsetDegrees[i])
                    t += a
                    mf[i]= a
                if t:
                    fix = 0
                    didChange = 0;
                    for i in range(mixCount):
                        if i < mixCount - 1:
                            pc = round(100 * mf[i] / t)
                            fix += pc
                        else:
                            pc = 100 - fix
                        if pc != lastMixes[i]:
                            lastMixes[i] = pc
                            f.write("M163 S{0} {1}\n".format(i,pc))
                            didChange = 1
                    if didChange:
                        f.write("M164 S0\n");  # "store it" to virtual extruder 0 - Repetier hack?

                    if insertPlotData:
                        # helps to plot the curves (grep + gnuplot), e.g. with:
                        #
                        # grep ';mixing_plot' $f |awk '{print $2 "\t" $3 "\t" $4 "\t" $5}' |sed '0,/^0/d' > /tmp/mix.dat
                        # gnuplot -p -e 'set yrange [0 : 100]; plot
                        #           "/tmp/mix.dat" using 1:2 title "C" with lines,
                        #           "/tmp/mix.dat" using 1:3 title "Y" with lines,
                        #           "/tmp/mix.dat" using 1:4 title "M" with lines'

                        f.write(";mixing_plot\t{0}\t".format(z))
                        for i in range(mixCount):
                            f.write("{0}\t".format(lastMixes[i]))
                        f.write("\n")

            f.write(line)

        elif not re.search(regexToRemove, line, re.IGNORECASE):
            # discard any previous tool change
            f.write(line)
