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
            "pre_infusion": 0,
            "purge": 0,
            "backflush": False
        }
        
        # Group Head 2 Configuration
        self.gh2_config = {
            "temperature": 92.0,
            "extraction_volume": 0,
            "extraction_time": 20,
            "pre_infusion": 0,
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

def handle_uart_message(flag: int, values: list):
    """Handle received UART messages"""
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
        elif flag == 13:  # GH1 extraction start
            config.GH1_ACTIVATION_FLAG = int(values[0])
            if int(values[0]) == 1:
                config.start_gh_timer(1, config.HGP1ExtractionTime)
        elif flag == 14:  # GH2 extraction start
            config.GH2_ACTIVATION_FLAG = int(values[0])
            if int(values[0]) == 1:
                config.start_gh_timer(2, config.HGP2ExtractionTime)
    except Exception as e:
        print(f"Error handling UART message: {e}")

# Create global config instance
config = Config()

# Initialize UART communication
uart = UARTCommunicator()
uart.set_message_callback(handle_uart_message)
try:
    uart.start()
except Exception as e:
    print(f"UART not started: {e}")

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
    print("\n=== Sending Main UART Message ===")
    pressure = int(round(config.pressureConfig['pressure']))
    main_temp = int(round(config.mainAmpereConfig['temperature']))
    print(f"Main boiler state: {main_boiler_state}")
    print(f"GH1 button state: {gh1_button_state}")
    print(f"GH2 button state: {gh2_button_state}")
    print(f"Pressure: {pressure}")
    print(f"Main temp: {main_temp}")
    uart.send_main_status(main_boiler_state, gh1_button_state, gh2_button_state, pressure, main_temp)
    print("=== Main UART Message Sent ===\n")

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
    
    def do_GET(self):
        print(f"\n=== GET Request to {self.path} ===")
        if self.path == '/getmainstatus':
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
                print(f"Config: {json.dumps(params.get('config', {}), indent=2)}")
                new_config = params.get('config', {})
                gh_id = params.get('gh_id', 'ghundefined')
                
                if gh_id == 'gh1':
                    extraction_time = int(new_config.get('extraction_time', config.gh1_config['extraction_time']))
                    config.gh1_config.update({
                        "temperature": float(new_config.get('temperature', config.gh1_config['temperature'])),
                        "extraction_volume": int(new_config.get('volume', config.gh1_config['extraction_volume'])),
                        "extraction_time": extraction_time,
                        "pre_infusion": int(new_config.get('pre_infusion', {}).get('time', config.gh1_config['pre_infusion'])),
                        "purge": int(new_config.get('purge', config.gh1_config['purge'])),
                        "backflush": bool(new_config.get('backflush', config.gh1_config['backflush']))
                    })
                    config.HGP1ExtractionTime = extraction_time
                    send_gh_uart(1, config.gh1_config)
                    last_gh1_data = [
                        int(round(config.gh1_config['temperature'])),
                        int(round(config.gh1_config['extraction_volume'])),
                        int(round(config.gh1_config['extraction_time'])),
                        int(round(config.gh1_config['purge'])),
                        1 if config.gh1_config['pre_infusion'] > 0 else 0,
                        int(round(config.gh1_config['pre_infusion']))
                    ]
                elif gh_id == 'gh2':
                    extraction_time = int(new_config.get('extraction_time', config.gh2_config['extraction_time']))
                    config.gh2_config.update({
                        "temperature": float(new_config.get('temperature', config.gh2_config['temperature'])),
                        "extraction_volume": int(new_config.get('volume', config.gh2_config['extraction_volume'])),
                        "extraction_time": extraction_time,
                        "pre_infusion": int(new_config.get('pre_infusion', {}).get('time', config.gh2_config['pre_infusion'])),
                        "purge": int(new_config.get('purge', config.gh2_config['purge'])),
                        "backflush": bool(new_config.get('backflush', config.gh2_config['backflush']))
                    })
                    config.HGP2ExtractionTime = extraction_time
                    send_gh_uart(2, config.gh2_config)
                    last_gh2_data = [
                        int(round(config.gh2_config['temperature'])),
                        int(round(config.gh2_config['extraction_volume'])),
                        int(round(config.gh2_config['extraction_time'])),
                        int(round(config.gh2_config['purge'])),
                        1 if config.gh2_config['pre_infusion'] > 0 else 0,
                        int(round(config.gh2_config['pre_infusion']))
                    ]
                
                print("\nUpdated Group Head Configurations:")
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
                print(f"Target: {params.get('target')}")
                print(f"Status: {params.get('status')}")
                target = params.get('target')
                status = params.get('status')
                state_changed = False
                
                print("\nCurrent states:")
                print("Button states:")
                print(f"- Main boiler button: {main_boiler_state}")
                print(f"- GH1 button: {gh1_button_state}")
                print(f"- GH2 button: {gh2_button_state}")
                
                if target == 'main_boiler':
                    new_state = 1 if status else 0
                    if new_state != main_boiler_state:
                        print(f"\nUpdating main boiler button state:")
                        print(f"Old state: {main_boiler_state}")
                        print(f"New state: {new_state}")
                        main_boiler_state = new_state
                        state_changed = True
                elif target == 'gh1':
                    new_state = 1 if status else 0
                    if new_state != gh1_button_state:
                        print(f"\nUpdating GH1 button state:")
                        print(f"Old state: {gh1_button_state}")
                        print(f"New state: {new_state}")
                        gh1_button_state = new_state
                        state_changed = True
                elif target == 'gh2':
                    new_state = 1 if status else 0
                    if new_state != gh2_button_state:
                        print(f"\nUpdating GH2 button state:")
                        print(f"Old state: {gh2_button_state}")
                        print(f"New state: {new_state}")
                        gh2_button_state = new_state
                        state_changed = True
                
                if state_changed:
                    print("\nButton state changed, sending flag 3 UART message...")
                    new_main = [main_boiler_state, gh1_button_state, gh2_button_state,
                              int(round(config.pressureConfig['pressure'])), 
                              int(round(config.mainAmpereConfig['temperature']))]
                    if last_main_data != new_main:
                        send_main_uart()
                        last_main_data = new_main
                else:
                    print("\nNo button state changes, skipping UART message")
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success"}).encode())
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
