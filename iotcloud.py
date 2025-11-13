#!/usr/bin/python3

from __future__ import print_function

from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session

import iot_api_client as iot
from iot_api_client.rest import ApiException
from iot_api_client.configuration import Configuration

import time
import iot_api_client
from iot_api_client.rest import ApiException
from pprint import pprint

CID="1MIo8jSNtjb41pTn66syIc9TSyvu9gko"
CSEC="Dxv0khaHH2uHLyJa5CzdpcdNh6Rq3IWH0EPw1y3Eti0KaHpBR0vxbC8jpM4OfwUz"

oauth_client = BackendApplicationClient(client_id=CID)
token_url = "https://api2.arduino.cc/iot/v1/clients/token"

oauth = OAuth2Session(client=oauth_client)
token = oauth.fetch_token(
    token_url=token_url,
    client_id=CID,
    client_secret=CSEC,
    include_client_id=True,
    audience="https://api2.arduino.cc/iot",
)

#print(token.get("access_token"))

# Configure OAuth2 access token for authorization: oauth2
configuration = iot_api_client.Configuration(
    host = "https://api2.arduino.cc/iot"
)
configuration.access_token = token.get("access_token")

# Enter a context with an instance of the API client
with iot_api_client.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = iot_api_client.PropertiesV2Api(api_client)
    id = '4b76edfa-14e2-4514-b254-c7c9d88740a3' # str | The id of the thing
    pid = 'ce2be7d5-ba56-44bf-9dc6-17e0c762d63f' # str | The id of the property
    property_value = iot_api_client.PropertyValue() # PropertyValue | PropertyValuePayload describes a property value

try:
   # publish properties_v2
   api_instance.properties_v2_publish(id, pid, property_value)
except ApiException as e:
   print("Exception when calling PropertiesV2Api->properties_v2_publish: %s\n" % e)

