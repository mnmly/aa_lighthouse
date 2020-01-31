#!/usr/bin/env python3

# lighting sequence for the "A Love Letter to the Lighthouse in the expanded field" performance
# using the Xicato XIM LED modules
# 2020-01-31 francesco.anselmo@gmail.com, i.am@mnmly.com

###
### ## Device ID and Groups
### The array of LEDs consists of 8 units numbered as ID of [1 - 8].
### 
### They are assigned to the following groups:
### 
### - `LIGHT_ALL`     (GROUP_ID: 10, all LEDs)
### - `LIGHT_PAIR_01` (GROUP_ID: 1 containing LED of 1 and 5)
### - `LIGHT_PAIR_02` (GROUP_ID: 2 containing LED of 2 and 6)
### - `LIGHT_PAIR_03` (GROUP_ID: 3 containing LED of 3 and 7)
### - `LIGHT_PAIR_04` (GROUP_ID: 4 containing LED of 4 and 8)

DEFAULT_GROUP = 10
DEFAULT_FADE_TIME = 2000 # in milliseconds
OSC_PORT = 5005

import signal
import cfg
import sys
import re
import platform
from collections import OrderedDict
from OSC import OSCServer,OSCClient, OSCMessage

system = platform.system()
dimming = None
server = None

# set up cfg
if system == "Darwin":
    cfg.MACOS = True
    cfg.WINDOWS = False
    cfg.LINUX = False
elif system == "Windows":
    cfg.WINDOWS = True
    cfg.MACOS = False
    cfg.LINUX = False
elif system == "Linux":
    cfg.LINUX = True
    cfg.WINDOWS = False
    cfg.MACOS = False
else:
    print('Sorry, this operating system is not supported by this program.')
    sys.exit(0)

from pyfiglet import Figlet
import ble_xim_pkg as ble_xim
import ble_xim_pkg.bxdevice as ble_device
import time
from threading import Thread, Lock

def sortFn(item):
    return item.deviceId

### Dimming  thread class
class XIMDimming(Thread):
    def __init__(self, xim, deviceList, fade_time=DEFAULT_FADE_TIME, parent=None, interval=0.150, group=DEFAULT_GROUP):
        Thread.__init__(self)
        self._keep_alive = True
        self._parent = parent
        self._interval = interval
        self.xim = xim
        self.fade_time = fade_time
        self.lock = Lock()
        self.ximNumber = len(deviceList)
        self.allOn = False
        self.deviceList = deviceList
        self.group = group
        self.pairedGroups = [
            1,      # 1, 5,
            2,      # 2, 6,
            3,      # 3, 7,
            4       # 4, 8
        ]

        # States
        self.rotating = False
        self.breathing = False
        self.breathFading = False

    def updateDeviceList(self):
        self.deviceList = self.xim.get_device_list()
        self.orderedDeviceList = OrderedDict()
        keys = sorted(self.deviceList.keys(), key = lambda x: x.deviceId)
        self.groupedDeviceList = [[], [], [], []]
        count = 0
        for key in keys:
            self.orderedDeviceList[key] = self.deviceList[key]
            self.groupedDeviceList[count % 4].append(key)
            # print(count % 4)
            count = count + 1
        self.ximNumber = len(self.deviceList)

    def run(self):
        if True:
            self.updateDeviceList()
            # print(d)
            while self._keep_alive:
                with self.lock:
                    ### State - Breathing: It should breath: 0 - 100 - 0 sequence for arbitary duration
                    if self.breathing:
                        action_set_group(True, self.fade_time, group = self.group)
                        time.sleep(self.fade_time/1000.0)
                        action_set_group(False, self.fade_time, group = self.group)
                        time.sleep(self.fade_time/1000.0)
                    ### State - Breath Fading: It should dim the max intensity to zero
                    ### i.e: 0 - 100 - 0 - 90 - 0 - 80 - 0 - 70 - 0 - ....
                    elif self.breathFading:
                        fading_values = [100,90,60,30,15,10,5,2,1,0]
                        for v in fading_values:
                            action_set_group(True, self.fade_time, maxIntensity=v, group = self.group)
                            time.sleep(self.fade_time/1000.0)
                            if v != 0:
                                action_set_group(False, self.fade_time, group = self.group)
                                time.sleep(self.fade_time/1000.0)
                        self.breathFading = False # This sequence should be terminated after completion
                    else:
                        ### State - Rotating: it should be paired in dimming: LED 1/5 LED 2/6 LED 3/7 LED 4/8
                        for pairGroup in self.pairedGroups:
                            if self.rotating:
                                print(pairGroup)
                                # put light to maximum brightness
                                print('dim on')
                                action_set_group(True, self.fade_time, group = pairGroup, keepRotation = True)
                                time.sleep(self.fade_time/1000 + 0.1)
                                # put light to minimum brightness
                                print('dim off')
                                action_set_group(False, self.fade_time, group = pairGroup, keepRotation = True)
                                time.sleep(self.fade_time/1000 + 0.1)
                        # sleep until next loop is due
                        if self.rotating:
                            self.rotating = False # This sequence should be terminated after the completion
                            print('Rotation Sequence ended')
                            action_set_group(False) # Need to force turn off all since it sometimes stuck turned on.
                    time.sleep(self._interval)

    def stop(self):
        with self.lock:
            # stop the loop in the run method
            self._keep_alive = False
### Dimming thread class


### BleXimThread class
class BleXimThread(Thread):
    def __init__(self, parent=None, interval=0.050):
        Thread.__init__(self)
        self._keep_alive = True
        self._parent = parent
        self._interval = interval
        self.lock = Lock()
        # ordinarily we would have a LogHandler to keep event/packet logs in case anything goes wrong
        # in this case, our example is so simple we don't need it
        ble_xim.initialize(None)


    def run(self):
        ble_xim.start()
        # print(ble_xim.getAllNetworkIds())
        while self._keep_alive:
            with self.lock:
                # run the stack
                try:
                    ble_xim.runHost()
                except:
                    pass
                    # print('runHost encountered an error (this is normal on exit)')
                # sleep until next loop is due
                time.sleep(self._interval)

    def stop(self):
        with self.lock:
            # stop the ble_xim stack
            ble_xim.stop()
            # stop the loop in the run method
            self._keep_alive = False

    def get_device_list(self):
        # gets device ids for devices that are XIMs or XIDs
        netDevIdList = ble_xim.getXimIdList()
        return {netDevId : ble_xim.getLightStatus(netDevId) for netDevId in netDevIdList}
### BleXimThread class

def exit_handler(sig, frame):
    sys.exit(0)

### Actions
def action_print_devices():
    print('action: print_devices')
    dimming.updateDeviceList()
    for item in dimming.orderedDeviceList:
        name = ble_xim.getDeviceName(item)
        intensity = dimming.deviceList[item].intensity
        print "{}({}): {}".format(item.deviceId, name, intensity)

def action_set_intensity_for(device_id = -1, intensity = 0):
    print('action: set_intensity_for: device_id: ' + str(device_id) + " with intensity: " + str(intensity))
    # dimming.updateDeviceList()
    devices = dimming.orderedDeviceList.items()
    if len(devices) >= device_id:
        device = dimming.orderedDeviceList.items()[device_id - 1] # orderedList is 0 based index, the LED ID is one based index.
        # we only want to deal with one device so if our filtered list has more than one member we don't proceed
        # now we create the values dictionary.
        # the names and acceptable values of each parameter can be found in the API documentation for each call
        values = {"light_level":intensity, "fade_time":0, "response_time":0, "override_time":0, "lock_light_control":False}
        # finally, actually issue the advertising command
        ble_xim.advLightControl(device[0], values)
        # time.sleep(0.15)
    else:
        print "Error: could not locate device with ID {}".format(device_id)

def action_set_group(on = True, interval = 0.15, maxIntensity = 100, group = DEFAULT_GROUP, keepRotation = False):
    """
    Set a group of LEDs on, off or to a specific intensity.
    Note that the group numbers in the range 0 - 16535, but when advertising
    to a group, the address is 0xC000 (49152) plus the group number.
    """
    print('action: set group '+ str(group) +' to ' + ("on" if on else "off"))
    dimming.rotating = keepRotation
    device_group = ble_device.NetDeviceId([0, 0, 0, 0], [49152+group])
    intensity = maxIntensity if on else 0
    values = {"light_level":intensity, "fade_time":dimming.fade_time, "response_time":0, "override_time":0, "lock_light_control":False}
    ble_xim.advLightControl(device_group, values)

# dynamic dimming rotation
def action_dim_rotation(on = True):
    print('action: set dimming rotation:  ' + ("on" if on else "off"))
    # dimming.updateDeviceList()
    dimming.breathing = False
    dimming.breathFading = False
    if on:
        dimming.allOn = False
        dimming.rotating = True
    else:
        dimming.rotating = False

# 0 - 100 - 0 cycle breathing
def action_breath(on = True):
    print('action: set breath:  ' + ("on" if on else "off"))
    # dimming.updateDeviceList()
    dimming.rotating = False
    dimming.breathFading = False
    if on:
        dimming.breathing = True
    else:
        dimming.breathing = False

# 0 - 100 - 0 cycle breathing
def action_breath_fade(on = True):
    print('action: set breath fading:  ' + ("on" if on else "off"))
    # dimming.updateDeviceList()
    dimming.rotating = False
    dimming.breathing = False
    if on:
        dimming.breathFading = True
    else:
        dimming.breathFading = False

# OSC Handlers

### OSC Message Callbacks
def fader_callback(path, tags, args, source):
    num = map(int, re.findall('\d', path.split('/')[-1]))[0]
    prev_fading = dimming.fade_time
    dimming.fade_time = 0
    action_set_intensity_for(num, args[0] * 100)
    dimming.fade_time = prev_fading

def set_all_callback(path, tags, args, source):
    num = map(int, re.findall('\d', path.split('/')[-1]))[0]
    action_set_group(True if num == 1 else False)

def dim_rotation_callback(path, tags, args, source):
    num = map(int, re.findall('\d', path.split('/')[-1]))[0]
    action_dim_rotation(True if num == 3 else False)

def breath_callback(path, tags, args, source):
    num = map(int, re.findall('\d', path.split('/')[-1]))[0]
    action_breath(True if num == 5 else False)

def breath_fade_callback(path, tags, args, source):
    num = map(int, re.findall('\d', path.split('/')[-1]))[0]
    action_breath_fade(True if num == 7 else False)

def print_devices_callback(path, tags, args, source):
    action_print_devices()


if __name__ == '__main__':

    if len(sys.argv) > 1 and sys.argv[1] == '-osc':
        server = OSCServer(("0.0.0.0", OSC_PORT))

    # display welcome message
    f1 = Figlet(font='script')
    print(f1.renderText('Lighthouse'))
    f2 = Figlet(font='small')
    print(f2.renderText('lighting control'))

    # if Ctrl-C is invoked call the function to exit the program
    signal.signal(signal.SIGINT, exit_handler)

    # start BLE XIM thread
    xim = BleXimThread()
    xim.start()
    # detect XIM LED devices
    deviceList = None
    print("Detecting XIM LEDs, please wait ...")
    for i in range(20):
        deviceList = xim.get_device_list()
        time.sleep(.25)

    # start dimming thread
    dimming = XIMDimming(xim, deviceList, DEFAULT_FADE_TIME)
    dimming.start()
    print("Number of XIM LEDs: " + str(dimming.ximNumber))

    # basic command prompt loop
    commands = 'Enter:\
        \n\td to detect and print devices\
        \n\tb to set individual LED brightness\
        \n\tf to set fading time\
        \n\tg to set the active group number\
        \n\ta to set all lights to maximum brightness\
        \n\to to switch off all lights\
        \n\ts to start the rotating dimming sequence\
        \n\te to end the rotating dimming sequence\
        \n\t0 to start the breathing sequence\
        \n\t1 to end the breathing sequence\
        \n\t2 to start the breathing fading sequence\
        \n\t3 to end the breathing fading sequence\
        \n\t? show commands\n\tq to quit'
    print(commands)

    if server != None:
        for i in range(1, 9):
            server.addMsgHandler( "/2/rotary" + str(i), fader_callback)

        server.addMsgHandler("/1/push1", set_all_callback) # On
        server.addMsgHandler("/1/push2", set_all_callback) # Off

        server.addMsgHandler("/1/push3", dim_rotation_callback) # On
        server.addMsgHandler("/1/push4", dim_rotation_callback) # Off

        server.addMsgHandler("/1/push5", breath_callback) # On
        server.addMsgHandler("/1/push6", breath_callback) # Off

        server.addMsgHandler("/1/push7", breath_fade_callback) # On
        server.addMsgHandler("/1/push8", breath_fade_callback) # Off

        server.addMsgHandler("/1/push99", print_devices_callback) # Off

    while True:
        if server != None:
            server.handle_request()
        else:
            choice = raw_input('> ')

            # print devices
            if choice == 'd':
                action_print_devices()
            # set fading time
            elif choice == 'f':
                fading_time = None
                while fading_time is None:
                    fading_time_raw = raw_input('fading time (ms): ')
                    try:
                        fading_time = int(fading_time_raw)
                        assert 1 <= fading_time <= 10000, "Fading time should be in the range of 0 - 10000"
                    except:
                        # catch the parsing error
                        print 'invalid fading time'
                        fading_time = None
                dimming.fade_time = fading_time

            # set group
            elif choice == 'g':
                group_number = None
                while group_number is None:
                    group_number_raw = raw_input('group id: ')
                    try:
                        group_number = int(group_number_raw)
                        assert 1 <= group_number <= 16535, "Group id should be in the range of 1 - 16535"
                    except:
                        # catch the parsing error
                        print 'invalid group id (this program only works with assigned IDs)'
                        group_number = None
                dimming.group = group_number

            # set individual XIM LED brightness
            elif choice == 'b':
                # first get a valid device id and intensity
                device_id = None
                intensity = None
                while device_id is None or intensity is None:
                    device_id_raw = raw_input('device id: ')
                    intensity_raw = raw_input('brightness: ')
                    try:
                        # the device id needs to be boxed into a list of integers
                        # in this case the list is 1 integer
                        # hypothetically we could also handle unassigned ids, which are lists of 3 bytes
                        # but it's simpler to only allow assigned ids
                        # it's also typically more predictable behavior
                        device_id = [int(device_id_raw)]
                        print(device_id[0])
                        assert 1 <= device_id[0] <= 49151, "Device id should be in the range of 1 - 49151"
                    except:
                        # catch the parsing error
                        print 'invalid device id (this program only works with assigned IDs)'
                        device_id = None
                    try:
                        # intensity needs to be a float between 0 and 100
                        intensity = float(intensity_raw)
                        assert 0 <= intensity <= 100, "Error: brightness out of range"
                    except:
                        # catch the parsing error
                        print 'invalid brightness'
                        intensity = None
                if intensity != None and device_id != None:
                    action_set_intensity_for(int(device_id_raw), intensity)
                else:
                    print "Error: could not locate device with ID {}".format(device_id)

            # dynamic dimming rotation
            elif choice == 's':
                action_dim_rotation(True)
            # stop dynamic dimming rotation
            elif choice == 'e':
                action_dim_rotation(False)
            # all lights on to maximum
            elif choice == 'a':
                action_set_group(True, group = dimming.group)
            # all lights off
            elif choice == 'o':
                action_set_group(False, group = dimming.group)
            elif choice == '?':
                f1 = Figlet(font='script')
                print(f1.renderText('Lighthouse'))
                f2 = Figlet(font='small')
                print(f2.renderText('lighting control'))
                print(commands)
            # quit
            elif choice == 'q':
                dimming.active = False
                print('goodbye')
                # stop all the threads before exiting
                xim.stop()
                dimming.stop()
                sys.exit(0)
            elif choice == '0':
                action_breath(True)
            elif choice == '1':
                action_breath(False)
            elif choice == '2':
                action_breath_fade(True)
            elif choice == '3':
                action_breath_fade(False)
            # default case
            else:
                print('I\'m sorry, what was that?')
