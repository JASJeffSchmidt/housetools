#!/bin/python3

import re
import sys
from datetime import datetime, timedelta
import time

def extract_indoor_temperature_from_log(file_path, output_path):
    try:
        pattern = r"(\d{2}/\d{2}/\d{2} \d{2}:\d{2}:\d{2} [APM]{2})  Main Omnistat RC-2000: Indoor temp is (\d+), humidity is \d+, HVAC Command: .*"

        with open(file_path, 'r') as log_file:
            lines = log_file.readlines()

        # Iterate from the end of the file to find the first matching line
        for line in reversed(lines):
            match = re.search(pattern, line)
            if match:
                timestamp_str = match.group(1)
                indoor_temp = float(match.group(2))

                # Convert the timestamp to RFC 822 format with local UTC offset
                try:
                    timestamp = datetime.strptime(timestamp_str, "%m/%d/%y %I:%M:%S %p")
                    local_utc_offset = -time.timezone if time.localtime().tm_isdst == 0 else -time.altzone
                    utc_offset_hours = local_utc_offset // 3600
                    utc_offset_minutes = (local_utc_offset % 3600) // 60
                    utc_offset_str = f"{utc_offset_hours:+03d}{utc_offset_minutes:02d}"
                    rfc822_timestamp = timestamp.strftime("%a, %d %b %Y %H:%M:%S ") + utc_offset_str
                    with open(output_path, 'w') as output_file:
                        output_file.write(f"{indoor_temp}\t{rfc822_timestamp}\n")
                    return indoor_temp, rfc822_timestamp
                except ValueError:
                    pass
    except Exception:
        pass

    return None

# Example usage:
if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python extract_indoor_temp_log.py <file_path> <output_path>")
    else:
        file_path = sys.argv[1]
        output_path = sys.argv[2]
        extract_indoor_temperature_from_log(file_path, output_path)




