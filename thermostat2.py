#!/bin/python3

import time
import signal
import sys
import os
import logging
from datetime import datetime
import RPi.GPIO as GPIO
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

DEBUG = True  # Enable or disable debug logs

BBPIN = 23

output_file_path = os.getenv("OUTPUT_FILE_PATH")
indoor_temp_file_path = f'{output_file_path}/{os.getenv("MAIN_OUTPUT_FILE")}'
outdoor_temp_file_path = f'{output_file_path}/{os.getenv("MDW_OUTPUT_FILE")}'
heater_state_file_path = f'{output_file_path}/{os.getenv("HEATER_STATE_FILE")}'
hk_home_away_file_path = f'{output_file_path}/{os.getenv("HK_SWITCH_OUTPUT_FILE")}'
logfile = os.getenv("HEATER_LOG_FILE")

LOOP_SLEEP_TIME = 60  # Sleep time in seconds between each loop
DATA_EXPIRATION_TIME = 60 * 60 * 3  # Data expiration time in seconds (3 hours)
OUTDOOR_TEMP_DISABLE_POINT = 45  # Disable heating if outdoor temperature is above this value in Fahrenheit
MIN_TEMP = -20  # Minimum valid temperature in Fahrenheit
MAX_TEMP = 110  # Maximum valid temperature in Fahrenheit

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename=logfile,
    filemode='a'
)


class Thermostat:
    def __init__(self, tstat, setpoint_temperature, start_hour, end_hour, hysteresis):
        logging.debug(
            f"Initializing Thermostat with setpoint_temperature={setpoint_temperature}°F, start_hour={start_hour}, end_hour={end_hour}, hysteresis={hysteresis}°F"
        )
        self.get_indoor_temperature()
        self.get_outdoor_temperature()
        self.setpoint_temperature = setpoint_temperature
        self.start_hour = start_hour
        self.end_hour = end_hour
        self.heating_on = False
        self.hysteresis = hysteresis
        self.tstat = tstat
        self.tstat.turnoff()
        time.sleep(5)

    def report_state(self):
        heating_status = "ON" if self.heating_on else "OFF"
        indoor_temp = (
            f"{self.indoor_temperature:.1f}°F"
            if self.indoor_temperature is not None
            else "N/A"
        )
        outdoor_temp = (
            f"{self.outdoor_temperature:.1f}°F"
            if self.outdoor_temperature is not None
            else "N/A"
        )
        s = f"STATE REPORT: Heating is: {heating_status}, Indoor temperature: {indoor_temp}, Outdoor temperature: {outdoor_temp}, Setpoint temperature: {self.setpoint_temperature}°F"
        if DEBUG:
            logging.info(s)
        return s[14:] # Remove "STATE REPORT: " prefix

    def update_temperature(self):
        self.get_indoor_temperature()
        self.get_outdoor_temperature()
        if (
            self.indoor_temperature is not None
            and self.outdoor_temperature is not None
        ):
            self.control_temperature()

    def control_temperature(self):
        if self.indoor_temperature is None or self.outdoor_temperature is None:
            logging.error("Temperature data is unavailable. Turning off heating.")
            self.turn_off_heating()
            return
        
        if not read_home_away():
            logging.info("Home status is not True. Turning off heating.")
            self.turn_off_heating()
            return

        current_hour = datetime.now().hour
        if self.start_hour <= current_hour < self.end_hour:
            if self.outdoor_temperature < OUTDOOR_TEMP_DISABLE_POINT:
                if self.indoor_temperature < (
                    self.setpoint_temperature - self.hysteresis
                ):
                    self.turn_on_heating()
                elif self.indoor_temperature > (
                    self.setpoint_temperature + self.hysteresis
                ):
                    self.turn_off_heating()
            else:
                self.turn_off_heating()
                if DEBUG:
                    logging.warning(
                        f"Heating is disabled due to high outdoor temperature: {self.outdoor_temperature:.1f}°F"
                    )
        else:
            self.turn_off_heating()
            if DEBUG:
                logging.warning(
                    "Heating is disabled due to being outside of operational hours."
                )

    def turn_on_heating(self):
        if not self.heating_on:
            if DEBUG:
                logging.info(
                    f"Heating is turned ON. Indoor temperature: {self.indoor_temperature:.1f}°F, Desired temperature: {self.setpoint_temperature:.1f}°F"
                )
            self.tstat.turnon()
            self.heating_on = True
            time.sleep(5)

    def turn_off_heating(self):
        if self.heating_on:
            if DEBUG:
                logging.info(
                    f"Heating is turned OFF. Indoor temperature: {self.indoor_temperature:.1f}°F, Desired temperature: {self.setpoint_temperature:.1f}°F"
                )
            self.tstat.turnoff()
            self.heating_on = False
            time.sleep(5)


    def read_temperature_from_file(self, file_path):
        try:
            with open(file_path, 'r') as file:
                line = file.readline()
                parts = line.split('\t')
                temperature = float(parts[1])
                timestamp_str = parts[0].strip()
                timestamp = datetime.strptime(
                    timestamp_str, "%a, %d %b %Y %H:%M:%S %z"
                )
                current_time = datetime.now()
                age = (
                    current_time - timestamp.replace(tzinfo=None)
                ).total_seconds()
                age_hours = age / 3600
                if DEBUG:
                    logging.debug(
                        f"Age of temperature data: {age} seconds ({age_hours:.2f} hours)"
                    )
                if age > DATA_EXPIRATION_TIME:
                    self.turn_off_heating()
                    raise ValueError(
                        f"Temperature data is too old: {timestamp_str}"
                    )
                if MIN_TEMP <= temperature <= MAX_TEMP:
                    return temperature
                else:
                    self.turn_off_heating()
                    raise ValueError(
                        f"Temperature out of valid range: {temperature}°F"
                    )
        except Exception as e:
            if DEBUG:
                logging.error(f"Error reading temperature from {file_path}: {e}")
            try:
                self.turn_off_heating()
            except:
                pass
            return None

    def get_outdoor_temperature(self):
        self.outdoor_temperature = self.read_temperature_from_file(outdoor_temp_file_path)

    def get_indoor_temperature(self):
        self.indoor_temperature = self.read_temperature_from_file(indoor_temp_file_path)


def read_home_away():
    try:
        with open(hk_home_away_file_path, 'r') as file:
            line = file.readline()
            parts = line.split('\t')
            if len(parts) >= 2:
                home_status = parts[1].strip()
                if home_status.startswith("Home: "):
                    home_status_value = home_status.split("Home: ")[1]
                    if home_status_value in ["True", "False"]:
                        if DEBUG:
                            logging.debug(f"Home Status: {home_status_value}")
                        return home_status_value == "True"
                    else:
                        raise ValueError(f"Invalid home status value in the file: {home_status_value}")
                        return None
                else:
                    raise ValueError("Home status not found in the file")
                    return None
            else:
                raise ValueError("Home status not found in the file")
                return None
    except Exception as e:
        logging.error(f"Error reading home status from {hk_home_away_file_path}: {e}")
        return None
    

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


def write_state(thermostat, daemon=0):
    tmpfile = f'{heater_state_file_path}.tmp'
    try:
        os.remove(tmpfile)
    except:
        pass

    try:
        if daemon == 0:
            with open(tmpfile, 'w') as output_file:
                output_file.write(f'{rfc822_timestring_now()}\tDaemon is: Running, {thermostat.report_state()}\n')
            os.rename(tmpfile, heater_state_file_path)
        else:
            with open(tmpfile, 'w') as output_file:
                output_file.write(f'{rfc822_timestring_now()}\tDaemon is: Stopped, {thermostat.report_state()}\n')
            os.rename(tmpfile, heater_state_file_path)
    except Exception as e:
        logging.error(f"Error writing state to {heater_state_file_path}: {e}")
        return None


## RPI GPIO Routines

def gpio_setup():
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(BBPIN, GPIO.OUT)
    GPIO.output(BBPIN, GPIO.HIGH)
    if DEBUG:
        logging.info("GPIO Initialized")


def gpio_cleanup():
    if DEBUG:
        logging.info("GPIO Cleanup")
    GPIO.cleanup()


class Heater:
    def __init__(self, pin=0):
        self.pin = pin
        self.status = False

    def turnon(self):
        GPIO.output(self.pin, GPIO.LOW)
        if DEBUG:
            logging.info("GPIO Front Heat On (Low)")
        self.status = True

    def turnoff(self):
        GPIO.output(self.pin, GPIO.HIGH)
        if DEBUG:
            logging.info("GPIO Front Heat Off (High)")
        self.status = False

def quit_handler(signum, frame):
    logging.info(f"Signal {signum} received. Cleaning-up and exiting")
    thermostat.turn_off_heating()
    write_state(thermostat,-1)
    gpio_cleanup()
    time.sleep(3)
    exit(0)

# Initialize
gpio_setup()
frontbb = Heater(BBPIN)

## Signal handlers
signal.signal(signal.SIGINT, quit_handler)
signal.signal(signal.SIGQUIT, quit_handler)
signal.signal(signal.SIGTERM, quit_handler)

# Parse setpoint_temperature from command line arguments
try:
    setpoint_temperature = float(sys.argv[1])
    if not (60 <= setpoint_temperature <= 75):
        raise ValueError("Setpoint temperature must be between 60 and 75°F.")
except (IndexError, ValueError) as e:
    if DEBUG:
        logging.error(f"Error: {e}")
        logging.info(
            "Usage: python3 thermostat_controller.py <setpoint_temperature>"
        )
    gpio_cleanup()
    time.sleep(3)
    sys.exit(1)

# Setup the thermostat
start_hour = 9
end_hour = 23
hysteresis = 1.0
thermostat = Thermostat(
    frontbb, setpoint_temperature, start_hour, end_hour, hysteresis
)

# Outer loop to control temperature
while True:
    thermostat.update_temperature()
    write_state(thermostat)
    time.sleep(LOOP_SLEEP_TIME)
