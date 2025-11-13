#!/bin/python3

import re
import os
import shutil
import stat
from datetime import datetime, timedelta
import time
import psycopg2
from dotenv import load_dotenv
import xml.etree.ElementTree as ET

# Load environment variables from .env file
load_dotenv()

mdw_input_file_path = os.getenv("MDW_INPUT_FILE_PATH")
tstat_input_file_path = os.getenv("TSTAT_INPUT_FILE_PATH")

# Where all output files are placed
output_file_path = os.getenv("OUTPUT_FILE_PATH")
mdw_output_file_path = f'{output_file_path}/{os.getenv("MDW_OUTPUT_FILE")}'
main_output_file_path = f'{output_file_path}/{os.getenv("MAIN_OUTPUT_FILE")}'
george_output_file_path = f'{output_file_path}/{os.getenv("GEORGE_OUTPUT_FILE")}'
mbr_output_file_path = f'{output_file_path}/{os.getenv("MBR_OUTPUT_FILE")}'


def ensure_directory_exists(path):
    try:
        if not os.path.exists(path):
            os.makedirs(path)
            shutil.chown(path, user='root', group='root')
            os.chmod(path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
            print(f"Directory {path} created with owner root:root and permissions 755")
        else:
            # print(f"Directory {path} already exists")
            return
    except Exception as e:
        print(f"Error creating directory {path}: {e}")


# Gets temp from Midway XML, downloaded periodically by MisterHouse
# Writes to local file
def extract_temperature_from_xml():
    tmpfile = f'{mdw_output_file_path}.tmp'
    try:
        os.remove(tmpfile)
    except:
        pass

    try:
        tree = ET.parse(mdw_input_file_path)
        root = tree.getroot()

        # Find elements in the XML
        temp_f_element = root.find('temp_f')
        observation_time_element = root.find('observation_time_rfc822')
        humid_element = root.find('relative_humidity')
        press_element = root.find('pressure_in')

        if temp_f_element is not None and \
           observation_time_element is not None and \
           humid_element is not None and \
           press_element is not None:
            temperature = float(temp_f_element.text)
            humidity = float(humid_element.text)
            pressure = float(press_element.text)
            observation_time = observation_time_element.text
            with open(tmpfile, 'w') as output_file:
                output_file.write(f"{observation_time}\t{temperature}\tMDW\n")
            os.rename(tmpfile, mdw_output_file_path)
            return observation_time, "MDW", temperature, humidity, pressure
        else:
            print("Error: Missing required elements in XML.")
    except ET.ParseError as e:
        print(f"Error parsing XML file {mdw_input_file_path}: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

    return None


# Gets temp from Omnistat log in Misterhouse
# Writes to local file
def extract_indoor_temperature_from_log(stat):

    # Common temp file for all
    tmpfile = f'{output_file_path}/tstat.tmp'

    try:
        os.remove(tmpfile)
    except:
        pass

    try:
        if stat == "MAIN":
            pattern = r"(\d{2}/\d{2}/\d{2} \d{2}:\d{2}:\d{2} [APM]{2})  Main Omnistat RC-2000: Indoor temp is (\d+), humidity is (\d+), HVAC Command: .*"
            outfile = main_output_file_path
            with open(tstat_input_file_path, 'r') as log_file:
                lines = log_file.readlines()

        elif stat == "GEORGE":
            #                                     02/12/25 12:20:41 AM  George Omnistat RC-80: Indoor temp is 66, HVAC Command: off, heat to 70, cool to 82, mode: off
            pattern = r"(\d{2}/\d{2}/\d{2} \d{2}:\d{2}:\d{2} [APM]{2})  George Omnistat RC-80: Indoor temp is (\d+), HVAC Command: .*"
            outfile = george_output_file_path
            with open(tstat_input_file_path, 'r') as log_file:
                lines = log_file.readlines()
            
        elif stat == "MBR":
            #                                     02/12/25 12:20:21 AM  MBR Omnistat RC-80: Indoor temp is 65, HVAC Command: off, heat to 62, cool to 82, mode: off
            pattern = r"(\d{2}/\d{2}/\d{2} \d{2}:\d{2}:\d{2} [APM]{2})  MBR Omnistat RC-80: Indoor temp is (\d+), HVAC Command: .*"
            outfile = mbr_output_file_path
            with open(tstat_input_file_path, 'r') as log_file:
                lines = log_file.readlines()
        
        else: 
            print("Error: Invalid thermostat specified.")
            return None

        # Iterate from the end of the file to find the first matching line
        for line in reversed(lines):
            match = re.search(pattern, line)
            if match:
                timestamp_str = match.group(1)
                indoor_temp = float(match.group(2))

                if stat == "MAIN":
                    indoor_humid = float(match.group(3))
                else:
                    indoor_humid = None

                # Convert the timestamp to RFC 822 format with local UTC offset
                try:
                    timestamp = datetime.strptime(timestamp_str, "%m/%d/%y %I:%M:%S %p")
                    local_utc_offset = -time.timezone if time.localtime().tm_isdst == 0 else -time.altzone
                    utc_offset_hours = local_utc_offset // 3600
                    utc_offset_minutes = (local_utc_offset % 3600) // 60
                    utc_offset_str = f"{utc_offset_hours:+03d}{utc_offset_minutes:02d}"
                    rfc822_timestamp = timestamp.strftime("%a, %d %b %Y %H:%M:%S ") + utc_offset_str
                    pg_timestamp = timestamp.strftime("%d-%b-%Y %H:%M:%S") + f"{utc_offset_hours:+03d}"

                    # Write to /var/environment
                    with open(tmpfile, 'w') as output_file:
                        output_file.write(f"{rfc822_timestamp}\t{indoor_temp}\t{stat}\n")
                    os.rename(tmpfile, outfile)
                    
                    return pg_timestamp, stat, indoor_temp, indoor_humid
                except ValueError as e:
                    print(f"Error parsing timestamp {timestamp_str}: {e}")
    except FileNotFoundError as e:
        print(f"Error reading log file {tstat_input_file_path}: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

    return None


def insert_into_database(timestamp, location, temp, humidity, pressure):
    try:
        connection = psycopg2.connect(
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT")
        )
        cursor = connection.cursor()

        # Check if an entry exists for the current wallclock hour
        check_query = """
            SELECT COUNT(*) FROM measurements
            WHERE station_id = %s AND DATE_TRUNC('hour', recorded_at) = DATE_TRUNC('hour', %s::TIMESTAMP WITH TIME ZONE)
        """
        cursor.execute(check_query, (location, timestamp))
        #print(cursor.query)
        result = cursor.fetchone()

        if result[0] == 0:
            if humidity and pressure:
                insert_query = """
                    INSERT INTO measurements (recorded_at, station_id, temperature_f, humidity_percent, pressure_inhg)
                    VALUES (%s, %s, %s, %s, %s)
                """
                cursor.execute(insert_query, (timestamp, location, temp, humidity, pressure))
                connection.commit()
                #print(cursor.query)
            elif humidity and not pressure:
                insert_query = """
                    INSERT INTO measurements (recorded_at, station_id, temperature_f, humidity_percent)
                    VALUES (%s, %s, %s, %s)
                """
                cursor.execute(insert_query, (timestamp, location, temp, humidity))
                connection.commit()
                #print(cursor.query)
            elif not humidity and not pressure:
                insert_query = """
                    INSERT INTO measurements (recorded_at, station_id, temperature_f)
                    VALUES (%s, %s, %s)
                """
                cursor.execute(insert_query, (timestamp, location, temp))
                connection.commit()
                #print(cursor.query)

        cursor.close()
        connection.close()
    except psycopg2.DatabaseError as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


## MAIN ##
if __name__ == "__main__":
    ensure_directory_exists(output_file_path)

    # Main tstat
    result = extract_indoor_temperature_from_log("MAIN")
    if result:
        ts, loc, temp, humid = result
        insert_into_database(ts, 0, temp, humid, None)
    
    # George tstat
    result = extract_indoor_temperature_from_log("GEORGE")
    if result:
        ts, loc, temp, humid = result
        insert_into_database(ts, 1, temp, None, None)

    # MBR tstat
    result = extract_indoor_temperature_from_log("MBR")
    if result:
        ts, loc, temp, humid = result
        insert_into_database(ts, 2, temp, None, None)

    # Midway weather station
    result = extract_temperature_from_xml()
    if result:
        ts, loc, temp, humid, pressure = result
        insert_into_database(ts, 100, temp, humid, pressure)
