#!/bin/python3

import xml.etree.ElementTree as ET
import sys

def extract_temperature_from_xml(file_path, output_path):
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()

        # Find the temperature element (in Fahrenheit)
        temp_f_element = root.find('temp_f')
        observation_time_element = root.find('observation_time_rfc822')

        if temp_f_element is not None and observation_time_element is not None:
            temperature = float(temp_f_element.text)
            observation_time = observation_time_element.text
            with open(output_path, 'w') as output_file:
                output_file.write(f"{temperature}\t{observation_time}\n")
            return temperature, observation_time
    except Exception:
        pass

# Example usage:
if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python extract_temperature_xml.py <file_path> <output_path>")
    else:
        file_path = sys.argv[1]
        output_path = sys.argv[2]
        extract_temperature_from_xml(file_path, output_path)



