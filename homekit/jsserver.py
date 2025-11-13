#!/bin/python3

import time
import signal
import os
import logging
from datetime import datetime
from dotenv import load_dotenv

from pyhap.accessory import Accessory, Bridge
from pyhap.accessory_driver import AccessoryDriver
from pyhap.const import (CATEGORY_FAN,
                         CATEGORY_LIGHTBULB,
                         CATEGORY_HEATER,
                         CATEGORY_SENSOR)

# Load environment variables from .env file
load_dotenv('../.env')


# Where all input files are placed
output_file_path = os.getenv("OUTPUT_FILE_PATH")
hk_switch_file_path = f'{output_file_path}/{os.getenv("HK_SWITCH_OUTPUT_FILE")}'
mdw_output_file_path = f'{output_file_path}/{os.getenv("MDW_OUTPUT_FILE")}'
main_output_file_path = f'{output_file_path}/{os.getenv("MAIN_OUTPUT_FILE")}'
george_output_file_path = f'{output_file_path}/{os.getenv("GEORGE_OUTPUT_FILE")}'
mbr_output_file_path = f'{output_file_path}/{os.getenv("MBR_OUTPUT_FILE")}'
bb_heater_state_file_path = f'{output_file_path}/{os.getenv("HEATER_STATE_FILE")}'


logging.basicConfig(level=logging.INFO, format="[%(module)s] %(message)s")

class LightBulb(Accessory):
    """lightbulb to signal home/away to my stuff"""

    category = CATEGORY_LIGHTBULB

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        serv_light = self.add_preload_service('Lightbulb')
        self.char_on = serv_light.configure_char(
            'On', setter_callback=self.set_bulb)
        
        # Initial state is off
        self.set_bulb(False)

    def set_bulb(self, value):
        # logging.info("Bulb value: %s", value)
        write_state(value)


class TemperatureSensorMain(Accessory):
    """Temperature sensor - main living room"""

    category = CATEGORY_SENSOR

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        serv_temp = self.add_preload_service('TemperatureSensor')
        self.char_temp = serv_temp.configure_char('CurrentTemperature')

    @Accessory.run_at_interval(30)
    async def run(self):
        t = read_temperature_from_file(main_output_file_path)
        if t is not None:
            self.char_temp.set_value(t)

class TemperatureSensorMBR(Accessory):
    """Temperature sensor - MBR"""

    category = CATEGORY_SENSOR

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        serv_temp = self.add_preload_service('TemperatureSensor')
        self.char_temp = serv_temp.configure_char('CurrentTemperature')

    @Accessory.run_at_interval(30)
    async def run(self):
        t = read_temperature_from_file(mbr_output_file_path)
        if t is not None:
            self.char_temp.set_value(t)

class TemperatureSensorGeorge(Accessory):
    """Temperature sensor - George"""

    category = CATEGORY_SENSOR

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        serv_temp = self.add_preload_service('TemperatureSensor')
        self.char_temp = serv_temp.configure_char('CurrentTemperature')

    @Accessory.run_at_interval(30)
    async def run(self):
        t = read_temperature_from_file(george_output_file_path)
        if t is not None:
            self.char_temp.set_value(t)
    
class TemperatureSensorMDW(Accessory):
    """Sensor - Midway METAR"""

    category = CATEGORY_SENSOR

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        serv_temp = self.add_preload_service('TemperatureSensor',
                                             chars=['CurrentRelativeHumidity'])
        self.char_temp = serv_temp.configure_char('CurrentTemperature')
        self.char_humid = serv_temp.configure_char('CurrentRelativeHumidity')

    @Accessory.run_at_interval(30)
    async def run(self):
        t = read_temperature_from_file(mdw_output_file_path)
        if t is not None:
            self.char_temp.set_value(t)


class BBHeater(Accessory):
    """Main Baseboard Heater - for reporting status to HK only"""

    # https://developer.apple.com/documentation/homekit/hmservicetypeheatercooler/

    category = CATEGORY_HEATER

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add the defaults to service
        serv_bb = self.add_preload_service('HeaterCooler',
                                           chars=['HeatingThresholdTemperature'])
        
        self.char_target_state = serv_bb.configure_char('TargetHeaterCoolerState')
        self.char_heat_state = serv_bb.configure_char('CurrentHeaterCoolerState')
        self.char_active = serv_bb.configure_char('Active')
        self.char_temp = serv_bb.configure_char('CurrentTemperature')
        self.char_setpoint = serv_bb.configure_char('HeatingThresholdTemperature')

        # Always a heater only
        # "ValidValues": {
        # "Auto": 0,
        # "Cool": 2,
        # "Heat": 1
        self.char_target_state.set_value(1)

        self.char_target_state.override_properties(properties={'Permissions': ["pr","ev"]}) # read only
        # default self.char_heat_state.override_properties(properties={'Permissions': "pr"}) # read only
        self.char_active.override_properties(properties={'Permissions': ["pr","ev"]}) # read only
        # default self.char_temp.override_properties(properties={'Permissions': "pr"}) # read only
        self.char_setpoint.override_properties(properties={'Permissions': ["pr","ev"]}) # read only



    @Accessory.run_at_interval(10)
    async def run(self):

        # Always a heater
        self.char_target_state.set_value(1)

        # https://developer.apple.com/documentation/homekit/hmcharacteristicvaluecurrentheatercoolerstate
        # "ValidValues": {
        # "Cooling": 3,
        # "Heating": 2,
        # "Idle": 1,
        # "Inactive": 0

        t = read_bb_from_file(bb_heater_state_file_path)
        if t:

            # print(t)

            # If the daemon isn't running, set to inactive
            if t['daemon_status'].casefold() != 'running'.casefold():
                self.char_heat_state.set_value(0)
                self.char_active.set_value(0)
                # print(f'Set: HS: 0, Active: 0')
            
            else: # demon is running
                if t['heating_status'].casefold() == 'on'.casefold():
                    self.char_heat_state.set_value(2)
                    self.char_active.set_value(1)
                    # print(f'Set: HS: 2, Active: 1')
                else:
                    self.char_heat_state.set_value(1)
                    self.char_active.set_value(1)
                    # print(f'Set: HS: 1, Active: 1')

            self.char_temp.set_value(f_to_c(float(t['indoor_temp'])))
            self.char_setpoint.set_value(f_to_c(float(t['setpoint_temp'])))
            # print(f"Set: { f_to_c(float(t['indoor_temp'])) } and { f_to_c(float(t['setpoint_temp'])) }")
        
        else:
            print("Error updating BB ")


def get_bridge(driver):
    bridge = Bridge(driver, 'Bridge')
    bridge.add_accessory(LightBulb(driver, 'Lightbulb'))
    bridge.add_accessory(TemperatureSensorMain(driver, 'Temp Main'))
    bridge.add_accessory(TemperatureSensorMBR(driver, 'Temp MBR'))
    bridge.add_accessory(TemperatureSensorGeorge(driver, 'Temp George'))
    bridge.add_accessory(BBHeater(driver, 'Main BB Heater'))
    bridge.add_accessory(TemperatureSensorMDW(driver, 'Temp MDW'))
    return bridge

def quit_handler(signum, frame):
    logging.info(f"Signal {signum} received. Cleaning-up and exiting")
    driver.signal_handler(signum, frame)


def rfc822_timestring(ts):
    timestamp = datetime.strptime(ts, "%m/%d/%y %I:%M:%S %p")
    local_utc_offset = -time.timezone if time.localtime().tm_isdst == 0 else -time.altzone
    utc_offset_hours = local_utc_offset // 3600
    utc_offset_minutes = (local_utc_offset % 3600) // 60
    utc_offset_str = f"{utc_offset_hours:+03d}{utc_offset_minutes:02d}"
    rfc822_timestamp = timestamp.strftime("%a, %d %b %Y %H:%M:%S ") + utc_offset_str
    return rfc822_timestamp


def rfc822_timestring_now():
    return rfc822_timestring(datetime.now().strftime("%m/%d/%y %I:%M:%S %p"))

def write_state(value):
    tmpfile = f'{hk_switch_file_path}.tmp'
    try:
        os.remove(tmpfile)
    except:
        pass

    try:
        with open(tmpfile, 'w') as output_file:
            output_file.write(f'{rfc822_timestring_now()}\tHome: {value}\n')
        os.rename(tmpfile, hk_switch_file_path)
    except Exception as e:
        logging.error(f"Error writing state to {hk_switch_file_path}: {e}")
        return None

def f_to_c(fahrenheit):
    return (fahrenheit - 32) * 5.0/9.0

def read_temperature_from_file(file):
    try:
        with open(file, 'r') as file:
            line = file.readline()
            parts = line.split('\t')
            if len(parts) >= 2:
                # logging.info(f"Indoor Temp: {float(parts[1])}")
                return f_to_c(float(parts[1]))
            else:
                raise ValueError("Temperature not found in the file")
                return None
    except Exception as e:
        logging.error(f"Error reading temperature from {file}: {e}")
        return None

import re


def read_bb_from_file(file_path):
    try:
        with open(file_path, 'r') as file:
            line = file.readline()
            pattern = (r'(?P<timestamp>[\w, ]+ \d{2}:\d{2}:\d{2} -\d{4})\t'
                       r'Daemon is: (?P<daemon_status>\w+), '
                       r'Heating is: (?P<heating_status>\w+), '
                       r'Indoor temperature: (?P<indoor_temp>[\d.]+)°F, '
                       r'Outdoor temperature: (?P<outdoor_temp>[\d.]+)°F, '
                       r'Setpoint temperature: (?P<setpoint_temp>[\d.]+)°F')
            match = re.match(pattern, line)
            if match:
                return match.groupdict()
            else:
                raise ValueError("Line format is incorrect")
    except Exception as e:
        print(f"Error reading status from {file_path}: {e}")
        return None


### MAIN ###

## Signal handlers
signal.signal(signal.SIGINT, quit_handler)
signal.signal(signal.SIGQUIT, quit_handler)
signal.signal(signal.SIGTERM, quit_handler)

## Start the server
driver = AccessoryDriver(port=51826, persist_file='jsserver.state')
driver.add_accessory(accessory=get_bridge(driver))
driver.start()
