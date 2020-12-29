#Name: Wood
#Info: Vary the print temperature troughout the print to create wood rings with some printing material such as the LayWoo. The higher the temperature, the darker the print.
#Depend: GCode
#Type: postprocess
#Param: minTemp(float:180) Minimum print temperature (degree C)
#Param: maxTemp(float:230) Maximum print temperature (degree C)
#Param: grainSize(float:3.0) Average "wood grain" size (mm)
#Param: firstTemp(float:0) Starting temperature (degree C, zero to disable)
#Param: spikinessPower(float:1.0) Relative thickness of light bands (power, >1 to make dark bands sparser)
#Param: maxUpward(float:0) Instant temperature increase limit, as required by some firmwares (C)
#Param: maxDownward(float:0) Instant temperature decrease limit, as some firmwares halt on big drops (C)
#Param: zOffset(float:0) Vertical shift of the variations, as shown at the end of the gcode file (mm)
#Param: skipStartZ(float:0) Skip some Z at start of print, i.e. raft height (mm)
#Param: scanForZHop(int:5) G-code lines to scan ahead for Z-Hop. Max 5 (default), 0 to disable.
#Param: tempCommand(string: M104) In case you want to rely on M109 for example (pause until temperature settles down)

__copyright__ = "Copyright (C) 2012-2017 Jeremie@Francois.gmail.com"
__author__ = 'Jeremie Francois (jeremie.francois@gmail.com)'
__date__ = '$Date: 2017/25/04 14:34:12 $'
__license__ = 'GNU Affero General Public License http://www.gnu.org/licenses/agpl.html'

import re
import random
import math
import datetime
import inspect
import sys
import getopt


############ BEGIN CURA PLUGIN STAND-ALONIFICATION ############
# This part is an "adapter" to Daid's version of my original Cura/Skeinforge plugin that
# he upgraded to the latest & simpler Cura plugin system. It enables command-line
# postprocessing of a gcode file, so as to insert the temperature commands at each layer.
#
# Note that it should still be viewed by Cura as a regular plugin by the way!
# More info on http://www.tridimake.com/2013/02/how-tun-run-python-cura-plugin-without.html
#
# To run it you need Python, then simply run it like
#   wood_standalone.py --min minTemp --max maxTemp --grain grainSize --file gcodeFile
# It will "patch" your gcode file with the appropriate M104 temperature change.
#

# TODO: support  UTF8 for both python3 and 2, e.g. open(filename, "r", encoding="utf_8")

def plugin_standalone_usage(myName):
    print("Usage:")
    print("  " + myName
          + " --file gcodeFile (--min minTemp) (--max maxTemp) (--first-temp startTemp) (--grain grainSize)"
          + " (--max-upward deltaTemp) (--random-seed integer) (--spikiness-power exponentFactor) (--z-offset zOffset)")
    print("  " + myName
          + " -f gcodeFile (-i minTemp) (-a maxTemp) (-t startTemp) (-g grainSize) (-u deltaTemp) (-r randomSeed)"
          + " (-s spikinessFactor) (-z zOffset)")
    print("Licensed under CC-BY " + __date__[7:26] + " by jeremie.francois@gmail.com (www.tridimake.com)")
    sys.exit()


try:
    filename
except NameError:
    # Then we are called from the command line (not from cura)
    # trying len(inspect.stack()) > 2 would be less secure btw
    opts, extraparams = getopt.getopt(sys.argv[1:], 'i:a:t:g:u:d:r:s:z:k:c:f:w:h',
                                      ['min=', 'max=', 'first-temp=', 'grain=', 'max-upward=', 'max-downward=', 'random-seed=',
                                       'spikiness-power=', 'z-offset=', 'skip-start-z=', 'scan-for-z-hop=', 'temp-command', 'file=', 'help'])
    minTemp = 190
    maxTemp = 240
    firstTemp = 0
    grainSize = 3
    maxUpward = 0
    maxDownward = 0
    skipStartZ = 0
    zOffset = 0
    scanForZHop = 5
    spikinessPower = 1.0
    tempCommand = 'M104'
    waitTemp = False
    filename = ""
    for o, p in opts:
        if o in ['-f', '--file']:
            filename = p
        elif o in ['-i', '--min']:
            minTemp = float(p)
        elif o in ['-a', '--max']:
            maxTemp = float(p)
        elif o in ['-t', '--first-temp']:
            firstTemp = float(p)
        elif o in ['-g', '--grain']:
            grainSize = float(p)
        elif o in ['-u', '--max-upward']:
            maxUpward = float(p)
        elif o in ['-d', '--max-downward']:
            maxDownward = float(p)
        elif o in ['-k', '--skip-start-z']:
            skipStartZ = float(p)
        elif o in ['-z', '--z-offset']:
            random.seed(0)
            zOffset = float(p)
        elif o in ['-c', '--scan-for-z-hop']:
            scanForZHop = int(p)
        elif o in ['-r', '--random-seed']:
            if p != 0:
                random.seed(p)
        elif o in ['-s', '--spikiness-power']:
            spikinessPower = float(p)
            if spikinessPower <= 0:
                spikinessPower = 1.0
        elif o in ['-w', '--temp-command']:
            tempCommand = p  # e.g. M109 in place of default M104, see https://www.simplify3d.com/support/articles/3d-printing-gcode-tutorial/#M104-M109
    if not filename:
        plugin_standalone_usage(inspect.stack()[0][1])


#
############ END CURA PLUGIN STAND-ALONIFICATION ############


def get_value(gcode_line, key, default=None):
    if not key in gcode_line or (';' in gcode_line and gcode_line.find(key) > gcode_line.find(';')):
        return default
    sub_part = gcode_line[gcode_line.find(key) + 1:]
    m = re.search('^[0-9]+\.?[0-9]*', sub_part)
    if m is None:
        return default
    try:
        return float(m.group(0))
    except:
        return default


def get_z(line, default=None):
    # Support G0 and G1 "move" commands
    if line.startswith(";WoodGraph:"):
        return default
    if get_value(line, 'G') == 0 or get_value(line, 'G') == 1:
        return get_value(line, 'Z', default)
    else:
        return default


try:
    xrange  # python 2.7 vs 3 compatibility
except NameError:
    xrange = range


class Perlin:
    # Perlin noise: http://mrl.nyu.edu/~perlin/noise/

    def __init__(self, tile_dimension=256):
        self.tile_dimension = tile_dimension
        self.perm = [None] * 2 * tile_dimension

        permutation = []
        for value in xrange(tile_dimension): permutation.append(value)
        random.shuffle(permutation)

        for i in xrange(tile_dimension):
            self.perm[i] = permutation[i]
            self.perm[tile_dimension + i] = self.perm[i]

    @staticmethod
    def fade(t):
        return t * t * t * (t * (t * 6 - 15) + 10)

    @staticmethod
    def lerp(t, a, b):
        return a + t * (b - a)

    @staticmethod
    def grad(hash_code, x, y, z):
        # CONVERT LO 4 BITS OF HASH CODE INTO 12 GRADIENT DIRECTIONS.
        h = hash_code & 15
        if h < 8:
            u = x
        else:
            u = y
        if h < 4:
            v = y
        else:
            if h == 12 or h == 14:
                v = x
            else:
                v = z
        if h & 1 == 0:
            first = u
        else:
            first = -u
        if h & 2 == 0:
            second = v
        else:
            second = -v
        return first + second

    def noise(self, x, y, z):
        # FIND UNIT CUBE THAT CONTAINS POINT.
        X = int(x) & (self.tile_dimension - 1)
        Y = int(y) & (self.tile_dimension - 1)
        Z = int(z) & (self.tile_dimension - 1)
        # FIND RELATIVE X,Y,Z OF POINT IN CUBE.
        x -= int(x)
        y -= int(y)
        z -= int(z)
        # COMPUTE FADE CURVES FOR EACH OF X,Y,Z.
        u = self.fade(x)
        v = self.fade(y)
        w = self.fade(z)
        # HASH COORDINATES OF THE 8 CUBE CORNERS
        A = self.perm[X] + Y
        AA = self.perm[A] + Z
        AB = self.perm[A + 1] + Z
        B = self.perm[X + 1] + Y
        BA = self.perm[B] + Z
        BB = self.perm[B + 1] + Z
        # AND ADD BLENDED RESULTS FROM 8 CORNERS OF CUBE
        return self.lerp(w, self.lerp(v,
            self.lerp(u, self.grad(self.perm[AA], x, y, z), self.grad(self.perm[BA], x - 1, y, z)),
            self.lerp(u, self.grad(self.perm[AB], x, y - 1, z), self.grad(self.perm[BB], x - 1, y - 1, z))),
            self.lerp(v,
                self.lerp(u, self.grad(self.perm[AA + 1], x, y, z - 1), self.grad(self.perm[BA + 1], x - 1, y, z - 1)),
                self.lerp(u, self.grad(self.perm[AB + 1], x, y - 1, z - 1), self.grad(self.perm[BB + 1], x - 1, y - 1, z - 1))))

    def fractal(self, octaves, persistence, x, y, z, frequency=1):
        value = 0.0
        amplitude = 1.0
        total_amplitude = 0.0
        for octave in xrange(octaves):
            n = self.noise(x * frequency, y * frequency, z * frequency)
            value += amplitude * n
            total_amplitude += amplitude
            amplitude *= persistence
            frequency *= 2
        return value / total_amplitude


with open(filename, "r") as f:
    lines = f.readlines()


# Limit the number of changes for helicoidal/Joris slicing method
minimumChangeZ = 0.1

# Find the total height of the object (minus optional additional Z-hops)
maxZ = 0
thisZ = 0
eol = "#"
for line in lines:
    thisZ = get_z(line)
    if thisZ is not None:
        if maxZ < thisZ:
            maxZ = thisZ
    if eol == "#" and len(line) >= 2:  # detect existing EOL to stay consistent when we'll be adding our own lines
        if line[-2] == "\r":  # windows...
            eol = "\r\n"
if eol == "#":
    eol = "\n"  # uh oh empty file?

"First pass generates the noise curve. We will normalize it as the user expects to reach the min & max temperatures"
perlin = Perlin()


def perlin_to_normalized_wood(z):
    banding = 3
    octaves = 2
    persistence = 0.7
    noise = banding * perlin.fractal(octaves, persistence, 0, 0, (z + zOffset) / (grainSize * 2));
    noise = (noise - math.floor(noise))  # normalized to [0,1]
    noise = math.pow(noise, spikinessPower)
    return noise


# Generate normalized noises, and then temperatures (will be indexed by Z value)
noises = {}
# first value is hard encoded since some slicers do not write a Z0 at the first layer!
noises[0] = perlin_to_normalized_wood(0)
pendingNoise = None
formerZ = -1
for line in lines:
    thisZ = get_z(line, formerZ)

    if thisZ > 2 + formerZ:
        formerZ = thisZ
    # noises = {}  # some damn slicers include a big negative Z shift at the beginning, which impacts the min/max range
    elif abs(thisZ - formerZ) > minimumChangeZ and thisZ > skipStartZ:
        formerZ = thisZ
        noises[thisZ] = perlin_to_normalized_wood(thisZ)

# normalize built noises
noisesMax = noises[max(noises, key=noises.get)]
noisesMin = noises[min(noises, key=noises.get)]
for z, v in noises.items():
    noises[z] = (noises[z] - noisesMin) / (noisesMax - noisesMin)


def noise_to_temp(noise):
    return minTemp + noise * (maxTemp - minTemp)

scanForZHop = int(scanForZHop)  # fix unicode error when using in range
if scanForZHop > 5:
    scanForZHop = 5


def z_hop_scan_ahead(index, z):
    if scanForZHop == 0:
        return False  # Do not scan ahead
    for i in range(scanForZHop):
        checkZ = get_z(lines[index + i], z)
        if checkZ < z:
            return True  # Found z-hop
    return False  # Did not find z-hop


#
# Now save the file with the patched M104 temperature settings
#
with open(filename, "w") as f:
    # Prepare a transposed ASCII-art temperature graph for the end of the file

    f.write(";woodified gcode, see graph at the end - jeremie.francois@gmail.com - generated on " +
            datetime.datetime.now().strftime("%Y%m%d-%H%M") + eol)
    warmingTempCommands = "M230 S0" + eol  # enable wait for temp on the first change
    t = firstTemp
    if t == 0:
        t = noise_to_temp(0)
    warmingTempCommands += ("%s S%i" + eol) % (tempCommand, t)
    # The two following commands depends on the firmware:
    warmingTempCommands += "M230 S1" + eol  # now disable wait for temp on the first change
    warmingTempCommands += "M116" + eol  # wait for the temperature to reach the setting (M109 is obsolete)
    f.write(warmingTempCommands)

    graphStr = ";WoodGraph: Wood temperature graph (from " + str(minTemp) + "C to " + str(
        maxTemp) + "C, grain size " + str(grainSize) + "mm, z-offset " + str(zOffset) + ", scanForZHop " + str(scanForZHop) + ")"
    if skipStartZ:
        graphStr += ", skipped first " + str(skipStartZ) + "mm of print"
    if maxUpward:
        graphStr += ", temperature increases capped at " + str(maxUpward)
    if maxDownward:
        graphStr += ", temperature decreases capped at " + str(maxDownward)
    graphStr += ":"
    graphStr += eol

    thisZ = -1
    formerZ = -1
    warned = 0

    postponedTempDelta = 0  # only when maxUpward is used
    postponedTempLast = None  # only when maxUpward is used
    skip_lines = 0
    for index, line in enumerate(lines):
        if "; set extruder " in line.lower():  # special fix for BFB
            f.write(line)
            f.write(warmingTempCommands)
            warmingTempCommands = ""
        elif "; M104_M109" in line:
            f.write(line)  # don't lose this remark!
        elif skip_lines > 0:
            skip_lines -= 1
        elif ";woodified" in line.lower():
            skip_lines = 4  # skip 4 more lines after our comment
        elif not ";woodgraph" in line.lower():  # forget optional former temp graph lines in the file
            if thisZ == maxZ:
                f.write(line)  # no more patch, keep the important end scripts unchanged
            elif not "m104" in line.lower():  # forget any previous temp in the file
                thisZ = get_z(line, formerZ)
                if thisZ != formerZ and thisZ in noises and not z_hop_scan_ahead(index, thisZ):

                    if firstTemp != 0 and thisZ <= 0.5:  # if specified, keep the first temp for the first 0.5mm
                        temp = firstTemp
                    else:
                        temp = noise_to_temp(noises[thisZ])

                        # possibly cap temperature change upward
                        temp += postponedTempDelta
                        postponedTempDelta = 0
                        if (postponedTempLast is not None)\
                                and (maxUpward > 0)\
                                and (temp > postponedTempLast + maxUpward ):
                            postponedTempDelta = temp - (postponedTempLast + maxUpward)
                            temp = postponedTempLast + maxUpward
                        if (postponedTempLast is not None)\
                                and (maxDownward > 0)\
                                and (temp < postponedTempLast - maxDownward ):
                            postponedTempDelta = postponedTempLast - maxDownward - temp
                            temp = postponedTempLast - maxDownward
                        if temp > maxTemp:
                            postponedTempDelta = 0
                            temp = maxTemp
                        postponedTempLast = temp

                        f.write(("%s S%i" + eol) % (tempCommand, temp))

                    formerZ = thisZ

                    # Build the corresponding graph line
                    t = int(19 * (temp - minTemp) / (maxTemp - minTemp))
                    graphStr += ";WoodGraph: Z %03f " % thisZ
                    graphStr += "@%3iC | " % temp
                    graphStr += '#'*t + '.'*(20 - t)
                    graphStr += eol

                f.write(line)

    f.write(graphStr + eol)
