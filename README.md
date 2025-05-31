from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs
import json
import threading
import time
import logging
import sys
from uart_comm import UARTCommunicator

# Configure logging to print to both file and console
logging.basicConfig(
    level=logging.DEBUG,  # Change to DEBUG level
    format='%(asctime)s - %(levelname)s - %(message)s',  # Add timestamp and level
    handlers=[
        logging.FileHandler('backend.log', mode='a'),  # Append mode instead of write
        logging.StreamHandler(sys.stdout)  # Print to console
    ]
)
logger = logging.getLogger(__name__)

class Config:
    def __init__(self):
        # Sensor values
        self.sensors = {
            "MainTankWaterLevel": 0.0,
            "HeadGP1WaterLevel": 0.0,
            "HeadGP2WaterLevel": 0.0,
            "MainTankTemp": 0.0,
            "HeadGP1TopTemp": 0.0,
            "HeadGP1BottomTemp": 0.0,
            "HeadGP2TopTemp": 0.0,
            "HeadGP2BottomTemp": 0.0,
            "Pressure": 0.0,
            "MainTankWaterFlow": 0.0,
            "HeadGP1WaterFlow": 0.0,
            "HeadGP2WaterFlow": 0.0,
            "Current": 0.0,
            "Voltage": 0.0
        }
        
        # Group Head 1 Configuration
        self.gh1_config = {
            "temperature": 91.0,
            "extraction_volume": 0,
            "extraction_time": 20,
            "pre_infusion": {
                "enabled": False,
                "time": 0
            },
            "purge": 0,
            "backflush": False
        }
        
        # Group Head 2 Configuration
        self.gh2_config = {
            "temperature": 92.0,
            "extraction_volume": 0,
            "extraction_time": 20,
            "pre_infusion": {
                "enabled": False,
                "time": 0
            },
            "purge": 0,
            "backflush": False
        }
        
        # System states
        self.FLOWGPH1CGF = 0.0
        self.FLOWGPH2CGF = 0.0
        self.tempMainTankFlag = True
        self.tempHeadGP1Flag = True
        self.tempHeadGP2Flag = True
        self.enableHeadGP1 = True
        self.enableHeadGP2 = True
        self.enableMainTank = True
        self.Pressure1 = 0.0
        self.Pressure2 = 0.0
        
        # UI settings
        self.HGP1FlowVolume = 0
        self.HGP2FlowVolume = 0
        self.HGP1PreInfusion = 0
        self.HGP2PreInfusion = 0
        self.HGP1ExtractionTime = 20
        self.HGP2ExtractionTime = 20
        self.tempMainTankSetPoint = 110.0
        self.tempHeadGP1SetPoint = 114.0
        self.tempHeadGP2SetPoint = 92.0
        
        # Additional features
        self.tempCupFlag = False
        self.cup = 0
        self.baristaLight = False
        self.light = 0
        self.ecomode = 0
        self.dischargeMode = 0
        
        # System states
        self.mainTankState = 1
        self.HGP1State = 1
        self.HGP2State = 1
        self.HGP1ACTIVE = 0
        self.HGP2ACTIVE = 0
        self.HGP12MFlag = 4
        self.sebar = 0
        self.HGPCheckStatus = False
        self.backflush1 = 4
        self.backflush2 = 4
        
        # Timer for GH activation reset
        self.gh1_timer = None
        self.gh2_timer = None
        
        # Extraction process flags
        self.gh1_extraction_in_progress = False
        self.gh2_extraction_in_progress = False

        # GH Activation flags (13 for GH1, 14 for GH2)
        self.GH1_ACTIVATION_FLAG = 0  # 0 = not running, 1 = running
        self.GH2_ACTIVATION_FLAG = 0  # 0 = not running, 1 = running

        # Main ampere configuration
        self.mainAmpereConfig = {
            "temperature": 125.0,
            "pressure": 9.0
        }
        
        # Pressure configuration
        self.pressureConfig = {
            "pressure": 9.0,
            "max_pressure": 12.0,
            "min_pressure": 0.0
        }
        
        print("Configuration initialized")

    def start_gh_timer(self, gh_number, extraction_time):
        """Start a timer to reset GH activation after extraction time"""
        if gh_number == 1:
            if self.gh1_timer:
                self.gh1_timer.cancel()
            self.gh1_extraction_in_progress = True
            self.gh1_timer = threading.Timer(extraction_time + 5, self.reset_gh_active, args=[1])
            self.gh1_timer.start()
        elif gh_number == 2:
            if self.gh2_timer:
                self.gh2_timer.cancel()
            self.gh2_extraction_in_progress = True
            self.gh2_timer = threading.Timer(extraction_time + 5, self.reset_gh_active, args=[2])
            self.gh2_timer.start()

    def reset_gh_active(self, gh_number):
        """Reset GH activation flag"""
        if gh_number == 1:
            self.HGP1ACTIVE = 0
            self.gh1_extraction_in_progress = False
            print(f"Automatically reset HGP1ACTIVE to 0 after extraction")
        elif gh_number == 2:
            self.HGP2ACTIVE = 0
            self.gh2_extraction_in_progress = False
            print(f"Automatically reset HGP2ACTIVE to 0 after extraction")

# Add global timestamps for extraction start
last_gh1_start = 0
last_gh2_start = 0

def handle_uart_message(flag: int, values: list):
    global last_gh1_start, last_gh2_start
    print(f"handle_uart_message called with flag={flag}, values={values}")
    try:
        if flag == 8:  # Main boiler temperature
            config.sensors["MainTankTemp"] = values[0] / 10  # Convert back to decimal
        elif flag == 9:  # GH1 status
            config.sensors["HeadGP1TopTemp"] = values[0] / 10
            config.Pressure1 = values[1]
            config.FLOWGPH1CGF = values[2]
        elif flag == 10:  # GH2 status
            config.sensors["HeadGP2TopTemp"] = values[0] / 10
            config.Pressure2 = values[1]
            config.FLOWGPH2CGF = values[2]
        elif flag == 13:  # GH1 extraction start/stop
            now = time.time()
            print(f"Received flag 13 with values: {values} at {now}")
            if int(values[0]) == 1:
                if not config.gh1_extraction_in_progress:
                    print("Starting GH1 extraction timer")
                    config.HGP1ACTIVE = 1
                    config.start_gh_timer(1, config.HGP1ExtractionTime)
                    last_gh1_start = now
                else:
                    print("GH1 extraction already in progress, ignoring repeated start")
            elif int(values[0]) == 0:
                # Only allow stop if at least 2 seconds have passed since start
                if config.gh1_extraction_in_progress and (now - last_gh1_start > 2):
                    print("Received GH1 extraction stop (13;0), setting HGP1ACTIVE=0")
                    config.HGP1ACTIVE = 0
                    config.gh1_extraction_in_progress = False
                else:
                    print("Ignoring spurious GH1 stop")
        elif flag == 14:  # GH2 extraction start/stop
            now = time.time()
            print(f"Received flag 14 with values: {values} at {now}")
            if int(values[0]) == 1:
                if not config.gh2_extraction_in_progress:
                    print("Starting GH2 extraction timer")
                    config.HGP2ACTIVE = 1
                    config.start_gh_timer(2, config.HGP2ExtractionTime)
                    last_gh2_start = now
                else:
                    print("GH2 extraction already in progress, ignoring repeated start")
            elif int(values[0]) == 0:
                if config.gh2_extraction_in_progress and (now - last_gh2_start > 2):
                    print("Received GH2 extraction stop (14;0), setting HGP2ACTIVE=0")
                    config.HGP2ACTIVE = 0
                    config.gh2_extraction_in_progress = False
                else:
                    print("Ignoring spurious GH2 stop")
    except Exception as e:
        print(f"Error handling UART message: {e}")

# Create global config instance
config = Config()

# Initialize UART communication
print("\n=== Starting Backend Server ===")
print("Initializing UART communication...")
uart = UARTCommunicator(port='/dev/ttyAMA0')
uart.set_message_callback(handle_uart_message)
try:
    print("\n=== Initializing UART Communication ===")
    print("Port: /dev/ttyAMA0")
    print("Baudrate: 9600")
    uart.start()
    print("UART initialization completed successfully")
except Exception as e:
    print(f"\n!!! UART INITIALIZATION ERROR !!!")
    print(f"Error type: {type(e).__name__}")
    print(f"Error message: {str(e)}")
    import traceback
    print(f"Traceback: {traceback.format_exc()}")
    print("====================================\n")

# Initialize system status variables
print("Initializing system status variables...")

# System status variables
mode_state = 0  # 0=off, 1=eco, 2=sleep
boiler_discharge = 0  # 0=nothing, 1=drain&refill, 2=drain&shutdown
barista_light = 0  # 0-100 percentage
cup_warmer = 0  # 0-100 percentage
discharge_timer = None

# Button and UART state variables
main_boiler_state = 0  # 0 = off, 1 = on
gh1_button_state = 0  # 0 = off, 1 = on
gh2_button_state = 0  # 0 = off, 1 = on

# State tracking variables
last_main_data = [0, 0, 0, 9, 230]  # Initialize with default values
last_gh1_data = None
last_gh2_data = None

def send_gh_uart(flag, cfg):
    """Send group head configuration"""
    print(f"\n=== Sending GH{flag} UART Message ===")
    print(f"Configuration: {json.dumps(cfg, indent=2)}")
    uart.send_gh_config(flag, cfg)
    print(f"=== GH{flag} UART Message Sent ===\n")

def send_main_uart():
    """Send main status UART message"""
    print("\n=== Attempting to Send Main UART Message ===")
    try:
        pressure = int(round(config.pressureConfig['pressure']))
        main_temp = int(round(config.mainAmpereConfig['temperature']))
        
        print("Current states:")
        print(f"Main boiler state: {main_boiler_state}")
        print(f"GH1 button state: {gh1_button_state}")
        print(f"GH2 button state: {gh2_button_state}")
        print(f"Pressure: {pressure}")
        print(f"Main temp: {main_temp}")
        
        print("\nLast main data:", last_main_data)
        new_main = [main_boiler_state, gh1_button_state, gh2_button_state, pressure, main_temp]
        print("New main data:", new_main)
        
        if last_main_data != new_main:
            print("State changed, sending UART message...")
            uart.send_main_status(main_boiler_state, gh1_button_state, gh2_button_state, pressure, main_temp)
            print("=== Main UART Message Sent ===\n")
        else:
            print("No state change, skipping UART message")
    except Exception as e:
        print(f"\n!!! Error in send_main_uart !!!")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        print("==============================\n")

def send_system_status_uart():
    """Send system status UART message"""
    print("\n=== Sending System Status UART Message ===")
    print(f"Mode: {mode_state}")
    print(f"Discharge: {boiler_discharge}")
    print(f"Light: {barista_light}")
    print(f"Cup warmer: {cup_warmer}")
    uart.send_system_status(mode_state, boiler_discharge, barista_light, cup_warmer)
    print("=== System Status UART Message Sent ===\n")

class RequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Enable HTTP request logging
        print(f"\n=== HTTP Request ===")
        print(f"Path: {self.path}")
        print(f"Method: {self.command}")
        print(f"Headers: {dict(self.headers)}")
        print("===================\n")
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        print(f"\n=== GET Request to {self.path} ===")
        if self.path == '/getghconfig':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            # Return both group head configurations
            data = {
                "gh1": {
                    "temperature": config.gh1_config['temperature'],
                    "pre_infusion": config.gh1_config['pre_infusion'],
                    "extraction_time": config.gh1_config['extraction_time'],
                    "volume": config.gh1_config['extraction_volume'],
                    "purge": config.gh1_config['purge'],
                    "backflush": config.gh1_config['backflush'],
                    "pressure": 9.0,
                    "flow": 2.5
                },
                "gh2": {
                    "temperature": config.gh2_config['temperature'],
                    "pre_infusion": config.gh2_config['pre_infusion'],
                    "extraction_time": config.gh2_config['extraction_time'],
                    "volume": config.gh2_config['extraction_volume'],
                    "purge": config.gh2_config['purge'],
                    "backflush": config.gh2_config['backflush'],
                    "pressure": 9.0,
                    "flow": 2.5
                }
            }
            
            print("\nSending GH Configurations:")
            print("--------------------------------")
            print(json.dumps(data, indent=2))
            print("--------------------------------\n")
            
            self.wfile.write(json.dumps(data).encode())
            
        elif self.path == '/getmainstatus':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            status_data = {
                "main_temperature": {
                    "value": config.tempMainTankSetPoint,
                    "unit": "°C"
                },
                "gh1": {
                    "temperature": {
                        "value": config.tempHeadGP1SetPoint,
                        "unit": "°C"
                    },
                    "pressure": {
                        "value": config.Pressure1,
                        "unit": "bar"
                    }
                },
                "gh2": {
                    "temperature": {
                        "value": config.tempHeadGP2SetPoint,
                        "unit": "°C"
                    },
                    "pressure": {
                        "value": config.Pressure2,
                        "unit": "bar"
                    }
                }
            }
            
            self.wfile.write(json.dumps(status_data).encode())
            
        elif self.path == '/getdata':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            data = config.sensors.copy()
            
            # Add additional data
            data["HeadGP1WaterFlow"] = config.FLOWGPH1CGF
            data["HeadGP2WaterFlow"] = config.FLOWGPH2CGF
            data["HGP1ACTIVE"] = config.HGP1ACTIVE
            data["HGP2ACTIVE"] = config.HGP2ACTIVE
            data["mainTankState"] = config.mainTankState
            data["HGP1State"] = config.HGP1State
            data["HGP2State"] = config.HGP2State
            
            # Add GH activation flags
            data["GH1_ACTIVATION_FLAG"] = config.GH1_ACTIVATION_FLAG
            data["GH2_ACTIVATION_FLAG"] = config.GH2_ACTIVATION_FLAG
            
            # Handle pressure data
            if config.sebar == 0:
                data["PressureGPH1"] = config.Pressure1
                data["PressureGPH2"] = config.Pressure2
            else:
                data["PressureGPH1"] = "3"
                data["PressureGPH2"] = "3"
            
            self.wfile.write(json.dumps(data).encode())
            
        elif self.path == '/geterror':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            data = {
                "HeadGroup1TemperatureStatus": config.tempHeadGP1Flag,
                "HeadGroup2TemperatureStatus": config.tempHeadGP2Flag,
                "MainTankTemperatureStatus": config.tempMainTankFlag
            }
            
            self.wfile.write(json.dumps(data).encode())
            
        elif self.path == '/getgauge':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            gauge_data = {
                "pressure": {
                    "value": config.Pressure1,
                    "min": 0,
                    "max": 12,
                    "unit": "bar"
                },
                "temperature": {
                    "value": config.tempMainTankSetPoint,
                    "min": 0,
                    "max": 120,
                    "unit": "°C"
                },
                "flow": {
                    "value": config.FLOWGPH1CGF,
                    "min": 0,
                    "max": 5,
                    "unit": "L/min"
                },
                "water_level": {
                    "value": config.sensors["MainTankWaterLevel"],
                    "min": 0,
                    "max": 100,
                    "unit": "%"
                }
            }
            
            self.wfile.write(json.dumps(gauge_data).encode())

    def do_POST(self):
        print(f"\n=== POST Request to {self.path} ===")
        global last_main_data, last_gh1_data, last_gh2_data, main_boiler_state, gh1_button_state, gh2_button_state
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8')
            print(f"Raw POST data: {post_data}")
            params = json.loads(post_data)
            print(f"Parsed POST data: {json.dumps(params, indent=2)}")
            
            if self.path == '/setpressureconfig':
                print("\n=== Processing Pressure Config Update ===")
                print(f"Config: {json.dumps(params.get('config', {}), indent=2)}")
                new_config = params.get('config', {})
                config.pressureConfig.update({
                    "pressure": float(new_config.get('pressure', config.pressureConfig['pressure'])),
                    "max_pressure": float(new_config.get('max_pressure', config.pressureConfig['max_pressure'])),
                    "min_pressure": float(new_config.get('min_pressure', config.pressureConfig['min_pressure']))
                })
                
                print("\nUpdated Pressure Configuration:")
                print("--------------------------------")
                print(json.dumps(config.pressureConfig, indent=2))
                print("--------------------------------\n")
                
                new_main = [main_boiler_state, gh1_button_state, gh2_button_state, int(round(config.pressureConfig['pressure'])), int(round(config.mainAmpereConfig['temperature']))]
                if last_main_data != new_main:
                    send_main_uart()
                    last_main_data = new_main
            
            elif self.path == '/setmainconfig':
                print("\n=== Processing Main Config Update ===")
                print(f"Config: {json.dumps(params.get('config', {}), indent=2)}")
                new_config = params.get('config', {})
                config.mainAmpereConfig.update({
                    "temperature": float(new_config.get('temperature', config.mainAmpereConfig['temperature']))
                })
                
                print("\nUpdated Main Configuration:")
                print("--------------------------------")
                print(json.dumps({
                    "temperature": config.mainAmpereConfig['temperature']
                }, indent=2))
                print("--------------------------------\n")
                
                new_main = [main_boiler_state, gh1_button_state, gh2_button_state, int(round(config.pressureConfig['pressure'])), int(round(config.mainAmpereConfig['temperature']))]
                if last_main_data != new_main:
                    send_main_uart()
                    last_main_data = new_main

            elif self.path == '/saveghconfig':
                print("\n=== Processing GH Config Save ===")
                print(f"GH ID: {params.get('gh_id')}")
                print(f"Raw config data: {json.dumps(params.get('config', {}), indent=2)}")
                new_config = params.get('config', {})
                gh_id = params.get('gh_id', 'ghundefined')

                # Log the current pre-infusion state before update
                if gh_id == 'gh1':
                    print("\nCurrent GH1 pre-infusion state:", config.gh1_config['pre_infusion'])
                elif gh_id == 'gh2':
                    print("\nCurrent GH2 pre-infusion state:", config.gh2_config['pre_infusion'])

                # Handle pre-infusion data consistently
                preinf_data = new_config.get('pre_infusion', {})
                print("\nReceived pre-infusion data:", preinf_data)
                
                # Always preserve the existing pre-infusion data if not explicitly changed
                if gh_id == 'gh1':
                    current_preinf = config.gh1_config['pre_infusion']
                else:
                    current_preinf = config.gh2_config['pre_infusion']
                
                if isinstance(preinf_data, dict):
                    # If it's a dict, preserve both enabled state and time
                    preinf = {
                        "enabled": bool(preinf_data.get('enabled', current_preinf['enabled'])),
                        "time": int(preinf_data.get('time', current_preinf['time']))
                    }
                    print("Using new pre-infusion dict:", preinf)
                else:
                    # If it's just a number (backward compatibility), only update time
                    preinf_time = int(preinf_data)
                    preinf = {
                        "enabled": current_preinf['enabled'],
                        "time": preinf_time
                    }
                    print("Using legacy format, preserving enabled state:", preinf)

                if gh_id == 'gh1':
                    extraction_time = int(new_config.get('extraction_time', config.gh1_config['extraction_time']))
                    ext_volume = new_config.get('extraction_volume', new_config.get('volume', config.gh1_config['extraction_volume']))
                    config.gh1_config.update({
                        "temperature": float(new_config.get('temperature', config.gh1_config['temperature'])),
                        "extraction_volume": int(ext_volume),
                        "extraction_time": extraction_time,
                        "pre_infusion": preinf,  # Store as dict with enabled state and time
                        "purge": int(new_config.get('purge', config.gh1_config['purge'])),
                        "backflush": bool(new_config.get('backflush', config.gh1_config['backflush']))
                    })
                    print("\nUpdated GH1 pre-infusion state:", config.gh1_config['pre_infusion'])
                    config.HGP1ExtractionTime = extraction_time
                    # Send UART after updating config
                    send_gh_uart(1, config.gh1_config)
                    last_gh1_data = [
                        int(round(config.gh1_config['temperature'])),
                        int(round(config.gh1_config['extraction_volume'])),
                        int(round(config.gh1_config['extraction_time'])),
                        int(round(config.gh1_config['purge'])),
                        1 if config.gh1_config['pre_infusion']['enabled'] else 0,
                        int(round(config.gh1_config['pre_infusion']['time']))
                    ]
                elif gh_id == 'gh2':
                    extraction_time = int(new_config.get('extraction_time', config.gh2_config['extraction_time']))
                    ext_volume = new_config.get('extraction_volume', new_config.get('volume', config.gh2_config['extraction_volume']))
                    config.gh2_config.update({
                        "temperature": float(new_config.get('temperature', config.gh2_config['temperature'])),
                        "extraction_volume": int(ext_volume),
                        "extraction_time": extraction_time,
                        "pre_infusion": preinf,  # Store as dict with enabled state and time
                        "purge": int(new_config.get('purge', config.gh2_config['purge'])),
                        "backflush": bool(new_config.get('backflush', config.gh2_config['backflush']))
                    })
                    print("\nUpdated GH2 pre-infusion state:", config.gh2_config['pre_infusion'])
                    config.HGP2ExtractionTime = extraction_time
                    # Send UART after updating config
                    send_gh_uart(2, config.gh2_config)
                    last_gh2_data = [
                        int(round(config.gh2_config['temperature'])),
                        int(round(config.gh2_config['extraction_volume'])),
                        int(round(config.gh2_config['extraction_time'])),
                        int(round(config.gh2_config['purge'])),
                        1 if config.gh2_config['pre_infusion']['enabled'] else 0,
                        int(round(config.gh2_config['pre_infusion']['time']))
                    ]

                print("\nFinal Group Head Configurations:")
                print("--------------------------------")
                print("Group Head 1:")
                print(json.dumps(config.gh1_config, indent=2))
                print("\nGroup Head 2:")
                print(json.dumps(config.gh2_config, indent=2))
                print("--------------------------------\n")

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
                return

            elif self.path == '/setstatusupdate':
                print("\n=== Processing Button State Update ===")
                target = params.get('target')
                status = params.get('status')
                print(f"Target: {target}")
                print(f"Status: {status}")
                print(f"Current states - Main: {main_boiler_state}, GH1: {gh1_button_state}, GH2: {gh2_button_state}")
                
                state_changed = False
                
                if target == 'main_boiler':
                    new_state = 1 if status else 0
                    if new_state != main_boiler_state:
                        print(f"\nUpdating main boiler button state:")
                        print(f"Old state: {main_boiler_state}")
                        print(f"New state: {new_state}")
                        main_boiler_state = new_state
                        state_changed = True
                elif target == 'gh1':
                    # Force state to 0 if it's currently 1, regardless of status
                    if gh1_button_state == 1:
                        gh1_button_state = 0
                        state_changed = True
                    elif status:  # Only set to 1 if status is True and current state is 0
                        gh1_button_state = 1
                        state_changed = True
                elif target == 'gh2':
                    # Force state to 0 if it's currently 1, regardless of status
                    if gh2_button_state == 1:
                        gh2_button_state = 0
                        state_changed = True
                    elif status:  # Only set to 1 if status is True and current state is 0
                        gh2_button_state = 1
                        state_changed = True
                
                if state_changed:
                    print("\nButton state changed, preparing to send UART message...")
                    print("Current states:")
                    print(f"Main boiler: {main_boiler_state}")
                    print(f"GH1 button: {gh1_button_state}")
                    print(f"GH2 button: {gh2_button_state}")
                    print(f"Pressure: {int(round(config.pressureConfig['pressure']))}")
                    print(f"Main temp: {int(round(config.mainAmpereConfig['temperature']))}")
                    
                    new_main = [main_boiler_state, gh1_button_state, gh2_button_state,
                              int(round(config.pressureConfig['pressure'])), 
                              int(round(config.mainAmpereConfig['temperature']))]
                    print(f"Last main data: {last_main_data}")
                    print(f"New main data: {new_main}")
                    
                    if last_main_data != new_main:
                        print("State changed, sending UART message...")
                        send_main_uart()
                        last_main_data = new_main
                    else:
                        print("No state change detected, skipping UART message")
                else:
                    print("\nNo button state changes, skipping UART message")
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success"}).encode())
                return

            elif self.path == '/savemainconfig':
                global mode_state, boiler_discharge, barista_light, cup_warmer
                print("\n=== Processing Main Config Save (Mode, Eco, etc.) ===")
                print(f"Config: {json.dumps(params.get('config', {}), indent=2)}")
                new_config = params.get('config', {})
                # Update mode_state, boiler_discharge, barista_light, cup_warmer if present
                if 'eco_mode' in new_config:
                    mode_map = {'off': 0, 'eco': 1, 'sleep': 2}
                    mode_state = mode_map.get(new_config['eco_mode'], 0)
                if 'boiler_discharge' in new_config:
                    discharge_map = {'none': 0, 'drain_refill': 1, 'drain_shutdown': 2}
                    boiler_discharge = discharge_map.get(new_config['boiler_discharge'], 0)
                if 'barista_light' in new_config:
                    if isinstance(new_config['barista_light'], dict):
                        barista_light = int(new_config['barista_light'].get('percentage', 0)) if new_config['barista_light'].get('enabled', False) else 0
                    else:
                        barista_light = int(new_config['barista_light'])
                if 'cup_warmer' in new_config:
                    if isinstance(new_config['cup_warmer'], dict):
                        cup_warmer = int(new_config['cup_warmer'].get('percentage', 0)) if new_config['cup_warmer'].get('enabled', False) else 0
                    else:
                        cup_warmer = int(new_config['cup_warmer'])
                # After updating, send flag 4 UART
                send_system_status_uart()
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
                return

            # Send success response
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True}).encode())
            
        except Exception as e:
            print(f"\n!!! ERROR in POST request handling !!!")
            print(f"Error type: {type(e).__name__}")
            print(f"Error message: {str(e)}")
            print(f"Request path: {self.path}")
            print(f"Request headers: {dict(self.headers)}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

def run_server(port=8000):
    server_address = ('', port)
    httpd = HTTPServer(server_address, RequestHandler)
    print(f'\n=== Starting Backend Server ===')
    print(f'Server address: {server_address}')
    print(f'UART port: {uart.port}')
    print(f'UART baudrate: {uart.baudrate}')
    print('==============================\n')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n=== Shutting down server ===")
        httpd.server_close()
        uart.stop()
    except Exception as e:
        print(f"\n!!! SERVER ERROR !!!")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        httpd.server_close()
        uart.stop()

if __name__ == '__main__':
    run_server() 
