import re
import random
import math
import datetime

# -- Required for the Cura wrapper --
from ..Script import Script     # Cura plugin support

from time import sleep
import threading

#  See https://github.com/Ultimaker/Uranium
from UM.Logger import Logger    # Write to Cura Log
from UM.Message import Message  # Progress bar
from PyQt6.QtCore import QCoreApplication   # Keep gui alive
from UM.Qt.QtApplication import QtApplication  # Check if cura has closed
# ------------------------------------


# Python 2.7 vs 3 compatibility
try:
    xrange
except NameError:
    xrange = range



# Main Class - Imported by Cura
# ==============================
class Woodgrain_Cura(Script):
    """
    This is a script that adds "texture" (thanks to temperature gradients), so as to get horizontal stripes that "look like wood".
    See: https://github.com/MoonCactus/gcode_postprocessors/tree/master/wood
    """        

    # Perlin noise: http://mrl.nyu.edu/~perlin/noise/
    #   - Used in generating wood texture
    # =================================================
    class Perlin:

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



    # Controls the settings available in the "Extensions > Post Processing > Modify G-Code" dialog
    # =============================
    def getSettingDataString(self):
        # Note that "version 2" does not refer to this code, but possibly the version of the cura plugin system(?) 
        return """{
            "name": "Woodgrain Effect",
            "key": "Woodgrain",
            "metadata": {},
            "version": 2,
            "settings":
            {
                "grainSize":
                {
                    "label": "Average wood grain size",
                    "description": "Make it larger for slower change in texture, 3 mm is a good value",
                    "type": "float",
                    "value": "3",
                    "minimum_value": "0",
                    "unit": "mm"
                },
                "minTemp":
                {
                    "label": "Mininum Temperature",
                    "description": "It depends on your filament, but Laywoo-D3 should be fine with 190. Clogging is more likely to happen with low values.",
                    "type": "int",
                    "value": "190",
                    "minimum_value": "0",
                    "minimum_value_warning": "180",
                    "maximum_value_warning": "250",
                    "unit": "C"
                },
                "maxTemp":
                {
                    "label": "Maximum Temperature",
                    "description": "It depends on your filament, but Laywoo-D3 withstands 240 well. Warning though, because when it is too hot or left to stay too long, it may clog the nozzle with solid carbon.",
                    "type": "int",
                    "value": "240",
                    "minimum_value": "0",
                    "minimum_value_warning": "180",
                    "maximum_value_warning": "250",
                    "unit": "C"
                },
                "firstTemp":
                {
                    "label": "First layer temperature",
                    "description": "The first layer temperature can be set manually so it sticks like you need it to the bed. Leave it to zero if you want it to be computed like the other layers.",
                    "type": "int",
                    "value": "200",
                    "minimum_value": "0",
                    "minimum_value_warning": "180",
                    "maximum_value_warning": "250",
                    "unit": "C"
                },
                "maxUpward":
                {
                    "label": "Maximum upward temperature variation",
                    "description": "Some printer firmwares like that of the BFB may pause to reach temperatures suddenly rised by more than 10°C. This setting caps the maximum positive increase between two changes; else set it at zero for most other firmwares like Marlin.",
                    "type": "int",
                    "value": "0",
                    "minimum_value": "0",
                    "unit": "C"
                },
                "maxDownward":
                {
                    "label": "Maximum downward temperature variation",
                    "description": "",
                    "type": "int",
                    "value": "0",
                    "minimum_value": "0",
                    "unit": "C"
                },
                "spikinessPower":
                {
                    "label": "Spikiness",
                    "description": "Default is a balanced set of dark and light (1.0). With higher values (eg 2 or 3), the dark stripes will be made sparser. You can get the opposite effect with value between 0 and 1 (eg. 0.5 will generate fatter dark bands, convenient for filament that get lighter with temperature)",
                    "type": "float",
                    "value": "1.0",
                    "minimum_value": "0.001",
                    "unit": ""
                },
                "zOffset":
                {
                    "label": "zOffset",
                    "description": "Vertical shift of the variations, as shown at the end of the gcode file.",
                    "type": "float",
                    "value": "0",
                    "unit": "mm"
                },
                "scanForZHop":
                {
                    "label": "scanForZHop",
                    "description": "Lines to scan ahead for Z-Hop. Max 5, 0 to disable.",
                    "type": "int",
                    "value": "5",
                    "minimum_value": "0",
                    "maximum_value": "5",
                    "unit": ""
                }
            }
        }"""



    # The .execute method in run by cura when the user saves the gcode file
    #   - this is our code entry point
    # =======================
    def execute(self, data):
        Logger.log("d", "[Woodgrain Effect] Begin processing")

        # Show the progress bar
        self.progress_bar = Message(title="Apply Woodgrain Effect", text="This may take several minutes, please be patient.\n\n",
                                    lifetime=0, dismissable=False, progress=-1)
        self.progress_bar.show()

        # Start the processing thread
        self._locks = {}
        self._locks["metadata"] = threading.Lock()
        self._locks["output"] = threading.Lock()

        self.progress = (-1,0)
        self.output_gcode=[]

        self.apply_woodgrain_thread = threading.Thread(target=self.apply_woodgrain, args=(data,))
        self.apply_woodgrain_thread.start()

        # Keep the GUI responsive while we wait, even though this script blocks the UI thread
        GUI_UPDATE_FREQUENCY = 50           # as used in cura source
        PROGRESS_CHECK_INTERVAL = 1000      # milliseconds

        update_period = 1 / GUI_UPDATE_FREQUENCY
        updates_per_check = int(GUI_UPDATE_FREQUENCY * (PROGRESS_CHECK_INTERVAL / 1000))
        
        # Wait until the processing thread is done
        while True:
            for i in range(0, updates_per_check):
                QCoreApplication.processEvents()  # Ensure that the GUI does not freeze.
                sleep(update_period)
            
            # Grab an update on the progress
            self._locks["metadata"].acquire()
            progress = self.progress
            self._locks["metadata"].release()

            # Update progress bar
            self.progress_bar.setProgress((progress[0] / progress[1]) * 100)    # float(100) means complete

            # Check if Cura is still open.. 
            # If it's not, this loop will just run forever
            main_window = QtApplication.getInstance().getMainWindow()  
            if main_window is None:
                return None     #close out the loop

            #Check if we're done
            if progress[0] >= progress[1]:
                self.apply_woodgrain_thread.join()
                break

        # Wrap things up and pass the modified gcode back to cura
        Logger.log("d", "[Woodgrain Effect] End processing. " + str(progress[1]) + " iterations performed")
        self.progress_bar.hide()
        return self.output_gcode



    # Gotta do the real work in a seperate thread, to keep the GUI from freezing up and the user from panicking
    # =======================
    def apply_woodgrain(self, data):
        lines = []

        # Get the appropriate eol character for unix / windows
        if "\r\n" in data[0]:
            eol = "\r\n"
        else:
            eol = "\n"

        # Deconstruct the gcode
        #   - One layer may have more than one command. To be safe we pull everything apart
        for layer in data:
            gcode_line = layer.split(eol)
            for line in gcode_line:
                lines.append(line)  #This is now our main source of data

        # Get the parameters from the "Extensions > Post Processing > Modify G-Code" dialog
        #   - Method is not defined here, but rather imported from Cura's "..Script" module.
        #==========================================
        minTemp = int(self.getSettingValueByKey("minTemp"))
        maxTemp = int(self.getSettingValueByKey("maxTemp"))
        firstTemp = int(self.getSettingValueByKey("firstTemp"))
        grainSize = float(self.getSettingValueByKey("grainSize"))
        maxUpward = int(self.getSettingValueByKey("maxUpward"))
        maxDownward = int(self.getSettingValueByKey("maxDownward"))
        zOffset = float(self.getSettingValueByKey("zOffset"))
        scanForZHop = int(self.getSettingValueByKey("scanForZHop"))
        spikinessPower = float(self.getSettingValueByKey("spikinessPower"))
        tempCommand = 'M104'
        skipStartZ = 0


        # (method for identifying gcode commands, not related to cura wrapper)
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

        # Limit the number of changes for helicoidal/Joris slicing method
        minimumChangeZ = 0.1

        # Find the total height of the object (minus optional additional Z-hops)
        maxZ = 0
        thisZ = 0

        # Note: data source is now lines array, instead of old f.readlines
        for line in lines:
            thisZ = get_z(line)
            if thisZ is not None:
                if maxZ < thisZ:
                    maxZ = thisZ

        #First pass generates the noise curve. We will normalize it as the user expects to reach the min & max temperatures
        perlin = self.Perlin()


        def perlin_to_normalized_wood(z):
            banding = 3
            octaves = 2
            persistence = 0.7
            noise = banding * perlin.fractal(octaves, persistence, 0, 0, (z + zOffset) / (grainSize * 2))
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


        # Drop-in replacement for old file writer
        #   - Stores data as a list of lines, terminated with eol
        # =============================================================
        class write_to_list:
            def __init__(self):
                self.content = ""
            def write(self, chars):
                self.content += (chars + eol)
            def get_data(self):
                list_output = []
                for line in self.content.split(eol):
                    list_output.append(line + eol)
                return list_output
        f = write_to_list()
        #==============================================================


        #
        # Now save the file with the patched M104 temperature settings
        #
        
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
        total_length = len(lines) - 1   #For cura wrapper progress
        for index, line in enumerate(lines):

            # Cura wrapper - send progress back to gui
            # Todo - decrease frequency of this snippet?
            self._locks["metadata"].acquire()
            self.progress = (index, total_length)
            self._locks["metadata"].release()

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

        # Fix incorrect values for first layer
        #   -   In testing, the script was not correctly setting the first layer temperatures for my prints
        #       As a bandaid, this snippet will manually hunt out the first M104 and fix it
        #       TODO: implement for temperature commands other than M104?
        self._locks["output"].acquire()
        first_layer_done = False
        for line in f.get_data():
            if not first_layer_done:
                if ";LAYER:0" in line:
                    first_layer_done = True
                elif "M104" in line and not ("M104 S" + str(firstTemp)) in line:
                    continue

            self.output_gcode.append(line)

        # Gcode now finalized, thread terminated
        # ============================================================
        self._locks["output"].release()
