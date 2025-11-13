from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session

import iot_api_client as iot
from iot_api_client.rest import ApiException
from iot_api_client.configuration import Configuration
from iot_api_client.api import ThingsV2Api, PropertiesV2Api, SeriesV2Api
from iot_api_client.models import *

import time
import os
import shutil
import stat
import psycopg2
from datetime import datetime
from time import sleep
from dotenv import load_dotenv


load_dotenv()  # take environment variables from .env.
load_dotenv('../.env')  # take environment variables from .env.

HOST = "https://api2.arduino.cc"
TOKEN_URL = "https://api2.arduino.cc/iot/v1/clients/token"

# Where all output files are placed
output_file_path = os.getenv("OUTPUT_FILE_PATH")
outdoor_wx_output_file_path = f'{output_file_path}/{os.getenv("OUTDOOR_WX_OUTPUT_FILE")}'
george_wx_output_file_path = f'{output_file_path}/{os.getenv("GEORGE_WX_OUTPUT_FILE")}'
mbr_wx_output_file_path = f'{output_file_path}/{os.getenv("MBR_WX_OUTPUT_FILE")}'

client_id=os.getenv('CID')
client_secret= os.getenv('CSEC')
org_id=None # (Optional) get a valid one from your Arduino account 
extract_from="2025-01-01T00:00:00Z"
extract_to="2025-01-10T00:00:00Z"
filename="dump.csv"


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


def write_to_file(file, properties):
    # Write to /var/environment

    tmpfile = f'{output_file_path}/ard.tmp'

    try:
        os.remove(tmpfile)
    except:
        pass

    tname = properties[0].thing_name
    try:
        with open(tmpfile, 'w') as output_file:
            output_file.write(f"{rfc822_timestring_now()}\t")
            output_file.write(f"{tname}\n")
            
            for prop in properties:
                output_file.write(f"{{{prop.variable_name},")
                output_file.write(f"{prop.last_value},")
                output_file.write(f"{prop.value_updated_at}}}\n")

        os.rename(tmpfile, file)
    except Exception as e:
        print(f"Error writing to file {file}: {e}")
        

def get_token():
    oauth_client = BackendApplicationClient(client_id=client_id)
    oauth = OAuth2Session(client=oauth_client)
    token = oauth.fetch_token(
        token_url=TOKEN_URL,
        client_id=client_id,
        client_secret=client_secret,
        include_client_id=True,
        audience="https://api2.arduino.cc/iot"
        # headers={"X-Organization":org_id}
    )
    return token


def init_client(token):
    client_config = Configuration(HOST)
    client_config.access_token = token.get("access_token")
    if org_id != None:
        client = iot.ApiClient(client_config,header_name="X-Organization",header_value=org_id)
    else :
        client = iot.ApiClient(client_config)
    return client

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


def get_things_and_props():
    token = get_token()
    client = init_client(token)
    things_api = ThingsV2Api(client)
    properties_api = PropertiesV2Api(client)
    
    try:
        things = things_api.things_v2_list()
        for thing in things:
            sleep(1)
            tname=thing.name
            #print(f"Found thing: {tname}")

            if tname.casefold() == "outdoor-pod-main":
                properties=properties_api.properties_v2_list(id=thing.id, show_deleted=False)  
                write_to_file(outdoor_wx_output_file_path, properties)
                insert_into_database(10, properties)

            if tname.casefold() == "george-pod-1":
                properties=properties_api.properties_v2_list(id=thing.id, show_deleted=False)  
                write_to_file(george_wx_output_file_path, properties)
                insert_into_database(11, properties)

            if tname.casefold() == "mbr-pod-1":
                properties=properties_api.properties_v2_list(id=thing.id, show_deleted=False)  
                write_to_file(mbr_wx_output_file_path, properties)
                insert_into_database(12, properties)

    except Exception as e:
        print("Exception: {}".format(e))


def insert_into_database(station, properties):
    try:
        connection = psycopg2.connect(
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT")
        )
        cursor = connection.cursor()

        for prop in properties:
            # Truncate all timestamps to seconds
            prop.value_updated_at = prop.value_updated_at.replace(microsecond=0)

            match prop.variable_name:
                case "temperature":
                    temperature_value = prop.last_value
                    temperature_updated_at = prop.value_updated_at
                case "humidity":
                    humidity_value = prop.last_value
                    humidity_updated_at = prop.value_updated_at
                case "altimeterSetting":
                    altimeterSetting_value = prop.last_value
                    altimeterSetting_updated_at = prop.value_updated_at
                case "dewpoint":
                    dewpoint_value = prop.last_value
                    dewpoint_updated_at = prop.value_updated_at
                case "gas":
                    gas_value = prop.last_value
                    gas_updated_at = prop.value_updated_at
                case "seaLevelPressure":
                    seaLevelPressure_value = prop.last_value
                    seaLevelPressure_updated_at = prop.value_updated_at
                case "stationPressure":
                    stationPressure_value = prop.last_value
                    stationPressure_updated_at = prop.value_updated_at
                case "updays":
                    updays_value = prop.last_value
                    updays_updated_at = prop.value_updated_at
                case "airQuality":
                    airQuality_value = prop.last_value
                    airQuality_updated_at = prop.value_updated_at
                case "airQualityQual":
                    airQualityQual_value = prop.last_value
                    airQualityQual_updated_at = prop.value_updated_at
                case "deviations":
                    deviations_value = prop.last_value
                    deviations_updated_at = prop.value_updated_at
                case "errors":
                    errors_value = prop.last_value
                    errors_updated_at = prop.value_updated_at
                case _:
                    print("ERROR {} not found".format(prop.variable_name))


        ## NOTE: We use the temperature_updated_at timestamp for everything DB related
        
        # Check if an entry exists for the current wallclock hour
        check_query = """
            SELECT COUNT(*) FROM measurements
            WHERE station_id = %s AND DATE_TRUNC('hour', recorded_at) = DATE_TRUNC('hour', %s::TIMESTAMP WITH TIME ZONE)
        """
        cursor.execute(check_query, (station, temperature_updated_at))
        #print(cursor.query)
        result = cursor.fetchone()

        if result[0] == 0:
            insert_query = """
                INSERT INTO measurements (recorded_at, station_id, temperature_f, humidity_percent, pressure_inhg,
                                          dewpoint, gas, seaLevelPressure, stationPressure, updays, 
                                          airQuality, airQualityQual, deviations, errors)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_query, (
                temperature_updated_at, station, temperature_value, humidity_value, altimeterSetting_value,
                dewpoint_value, gas_value, seaLevelPressure_value, stationPressure_value, updays_value, 
                airQuality_value, airQualityQual_value, deviations_value, errors_value
            ))

            connection.commit()
            #print(cursor.query)
   
        cursor.close()
        connection.close()
    except psycopg2.DatabaseError as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


#################

ensure_directory_exists(output_file_path)
get_things_and_props()

