#!/bin/python3

import re
import sys
import os
from datetime import datetime, timedelta
import time
import psycopg2
from dotenv import load_dotenv


def extract_indoor_temperature_from_log(file_path, output_path):
    try:
        pattern = r"(\d{2}/\d{2}/\d{2} \d{2}:\d{2}:\d{2} [APM]{2})  Main Omnistat RC-2000: Indoor temp is (\d+), humidity is (\d+), HVAC Command: .*"

        with open(file_path, 'r') as log_file:
            lines = log_file.readlines()

        # Iterate from the end of the file to find the first matching line
        for line in reversed(lines):
            match = re.search(pattern, line)
            if match:
                timestamp_str = match.group(1)
                indoor_temp = float(match.group(2))
                indoor_humid = float(match.group(3))

                # Convert the timestamp to RFC 822 format with local UTC offset
                try:
                    timestamp          = datetime.strptime(timestamp_str, "%m/%d/%y %I:%M:%S %p")
                    local_utc_offset   = -time.timezone if time.localtime().tm_isdst == 0 else -time.altzone
                    utc_offset_hours   = local_utc_offset // 3600
                    utc_offset_minutes = (local_utc_offset % 3600) // 60
                    utc_offset_str     = f"{utc_offset_hours:+03d}{utc_offset_minutes:02d}"
                    rfc822_timestamp   = timestamp.strftime("%a, %d %b %Y %H:%M:%S ") + utc_offset_str
                    pg_timestamp       = timestamp.strftime("%d-%b-%Y %H:%M:%S") + f"{utc_offset_hours:+03d}"
                    with open(output_path, 'w') as output_file:
                        output_file.write(f"{indoor_temp}\t{rfc822_timestamp}\n")
                    return pg_timestamp, "Main", indoor_temp, indoor_humid
                except ValueError:
                    pass
    except Exception:
        pass

    return None


def insert_into_database(timestamp, location, temp, humidity):
    load_dotenv()

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
            SELECT COUNT(*) FROM indoor_measurements
            WHERE station_id = %s AND DATE_TRUNC('hour', recorded_at) = DATE_TRUNC('hour', %s::TIMESTAMP WITH TIME ZONE)
        """
        cursor.execute(check_query, (location,timestamp))
        # print(cursor.query)
        result = cursor.fetchone()
        
        if result[0] == 0:
            insert_query = """
                INSERT INTO indoor_measurements (recorded_at, station_id, temperature_f, humidity_percent)
                VALUES (%s, %s, %s, %s)
            """
            cursor.execute(insert_query, (timestamp, location, temp, humidity))
            connection.commit()
            # print(cursor.query)
        
        cursor.close()
        connection.close()
    except Exception as e:
        print(f"Database insertion failed: {e}")


# Example usage:
if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python extract_indoor_temp_log.py <file_path> <output_path>")
    else:
        file_path = sys.argv[1]
        output_path = sys.argv[2]
        (ts, loc, temp, humid) = extract_indoor_temperature_from_log(file_path, output_path)
        insert_into_database(ts, 0, temp, humid)
