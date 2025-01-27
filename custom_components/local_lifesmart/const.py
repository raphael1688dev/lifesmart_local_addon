"""Constants for the LifeSmart API specification v1.9.

This module defines various constants used throughout the LifeSmart API, including default model and token, API protocol settings, and value types for different device capabilities.

Attributes:
    DOMAIN (str): The domain name for the LifeSmart API.
    MANUFACTURER (str): The name of the LifeSmart manufacturer.
    DEFAULT_MODEL (str): The default model used for the LifeSmart API.
    DEFAULT_TOKEN (str): The default token used for the LifeSmart API.
    API_TIMEOUT (int): The timeout in seconds for the LifeSmart API requests.
    API_PORT (int): The port number used for the LifeSmart API.
    API_VERSION (int): The version number of the LifeSmart API.
    REMARK (str): A remark or identifier used in the LifeSmart API.
    PLATFORMS (list): The list of supported platforms for the LifeSmart API.
    CMD_GET (int): The constant for a query command.
    CMD_SET (int): The constant for a control command.
    CMD_REPORT (int): The constant for a status report command.
    VAL_TYPE_ONOFF (int): The constant for an on/off value type.
    VAL_TYPE_BRIGHTNESS (int): The constant for a brightness value type.
    VAL_TYPE_COLOR_TEMP (int): The constant for a color temperature value type.
    VAL_TYPE_RGB (int): The constant for an RGB value type.
"""
"""Constants for LifeSmart API specification v1.9."""
DOMAIN = "lifesmart"
MANUFACTURER = "LifeSmart"
# API Constants
DEFAULT_MODEL = "OD_ALI_TECH"
DEFAULT_TOKEN = "8SptZ2l2xnQlb8bSdT8mwA"

# API Protocol Constants
API_TIMEOUT = 10  # seconds
API_PORT = 12348
API_VERSION = 1
REMARK = "JL"
PLATFORMS = ["switch", "sensor","cover" , "remote"]
# Command Types
CMD_GET = 1    # Query command
CMD_SET = 3    # Control command
CMD_REPORT = 2 # Status report

# Value Types
VAL_TYPE_ONOFF = 0
VAL_TYPE_BRIGHTNESS = 1
VAL_TYPE_COLOR_TEMP = 2
VAL_TYPE_RGB = 3