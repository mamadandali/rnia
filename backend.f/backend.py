from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs
import json
import threading
import time
import logging
import sys

# Configure logging to print to both file and console
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',  # Remove timestamp and level
    handlers=[
        logging.FileHandler('backend.log', mode='w'),  # Clear file on start
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
        self.tempMainTankSetPoint = 120.0
        self.tempHeadGP1SetPoint = 91.0
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

        # Main ampere configuration
        self.mainAmpereConfig = {
            "temperature": 125.0,
            "pressure": 9.0
        }
        print("Configuration initialized")

# Create global config instance
config = Config()

class RequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Don't log HTTP requests
        pass
    
    def do_GET(self):
        if self.path == '/getdata':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            data = config.sensors.copy()
            
            # Add additional data
            data["HeadGP1WaterFlow"] = config.FLOWGPH2CGF
            data["HeadGP2WaterFlow"] = config.FLOWGPH1CGF
            data["HGP1ACTIVE"] = config.HGP1ACTIVE
            data["HGP2ACTIVE"] = config.HGP2ACTIVE
            data["mainTankState"] = config.mainTankState
            data["HGP1State"] = config.HGP1State
            data["HGP2State"] = config.HGP2State
            
            # Handle pressure data
            if config.sebar == 0:
                data["PressureGPH1"] = config.Pressure1
                data["PressureGPH2"] = config.Pressure2
            else:
                data["PressureGPH1"] = "3"
                data["PressureGPH2"] = "3"
            
            data["timeHGP1"] = config.timeHGP1
            data["timeHGP2"] = config.timeHGP2
            data["HeadGP1TopTemp"] = str(config.sensors["HeadGP1TopTemp"])
            data["HeadGP2TopTemp"] = str(config.sensors["HeadGP2TopTemp"])
            
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

        elif self.path == '/getghconfig':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            gh_config = {
                "gh1": config.gh1_config,
                "gh2": config.gh2_config
            }
            
            self.wfile.write(json.dumps(gh_config).encode())

        elif self.path == '/getmainconfig':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            main_config = config.mainAmpereConfig.copy()
            
            self.wfile.write(json.dumps(main_config).encode())
            
        else:
            self.send_response(404)
            self.send_header('Content-type', 'text/html')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b'404 Not Found')

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        params = json.loads(post_data)
        
        try:
            if self.path == '/setmainconfig':
                # Log the received request
                print("\nReceived POST request to /setmainconfig")
                print("Request data:", json.dumps(params, indent=2))
                
                # Get the new configuration
                new_config = params.get('config', {})
                
                # Update main configuration
                config.mainAmpereConfig.update({
                    "temperature": float(new_config.get('temperature', config.mainAmpereConfig['temperature']))
                })
                
                # Log the updated configuration
                print("\nUpdated Main Configuration:")
                print("--------------------------------")
                print(json.dumps({
                    "temperature": config.mainAmpereConfig['temperature']
                }, indent=2))
                print("--------------------------------\n")
            
            elif self.path == '/saveghconfig':
                # Log the received request
                print("\nReceived POST request to /saveghconfig")
                print("Request data:", json.dumps(params, indent=2))
                
                # Get the new configuration
                new_config = params.get('config', {})
                gh_id = params.get('gh_id', 'ghundefined')
                
                # Update Group Head 1
                config.gh1_config.update({
                    "temperature": float(new_config.get('temperature', config.gh1_config['temperature'])),
                    "extraction_volume": int(new_config.get('volume', config.gh1_config['extraction_volume'])),
                    "extraction_time": int(new_config.get('extraction_time', config.gh1_config['extraction_time'])),
                    "pre_infusion": int(new_config.get('pre_infusion', {}).get('time', config.gh1_config['pre_infusion'])),
                    "purge": int(new_config.get('purge', config.gh1_config['purge'])),
                    "backflush": bool(new_config.get('backflush', config.gh1_config['backflush']))
                })
                
                # Update Group Head 2
                config.gh2_config.update({
                    "temperature": float(new_config.get('temperature', config.gh2_config['temperature'])),
                    "extraction_volume": int(new_config.get('volume', config.gh2_config['extraction_volume'])),
                    "extraction_time": int(new_config.get('extraction_time', config.gh2_config['extraction_time'])),
                    "pre_infusion": int(new_config.get('pre_infusion', {}).get('time', config.gh2_config['pre_infusion'])),
                    "purge": int(new_config.get('purge', config.gh2_config['purge'])),
                    "backflush": bool(new_config.get('backflush', config.gh2_config['backflush']))
                })

                # Log the updated configurations
                print("\nUpdated Group Head Configurations:")
                print("--------------------------------")
                print("Group Head 1:")
                print(json.dumps({
                    "temperature": config.gh1_config['temperature'],
                    "pre_infusion": {
                        "enabled": bool(config.gh1_config['pre_infusion'] > 0),
                        "time": config.gh1_config['pre_infusion']
                    },
                    "extraction_time": config.gh1_config['extraction_time'],
                    "volume": config.gh1_config['extraction_volume'],
                    "purge": config.gh1_config['purge'],
                    "backflush": config.gh1_config['backflush']
                }, indent=2))
                print("\nGroup Head 2:")
                print(json.dumps({
                    "temperature": config.gh2_config['temperature'],
                    "pre_infusion": {
                        "enabled": bool(config.gh2_config['pre_infusion'] > 0),
                        "time": config.gh2_config['pre_infusion']
                    },
                    "extraction_time": config.gh2_config['extraction_time'],
                    "volume": config.gh2_config['extraction_volume'],
                    "purge": config.gh2_config['purge'],
                    "backflush": config.gh2_config['backflush']
                }, indent=2))
                print("--------------------------------\n")

            # Send success response
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(b'POST request received!')
            
        except Exception as e:
            print(f"Error processing POST request: {e}")
            self.send_response(500)
            self.send_header('Content-type', 'text/html')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b'Internal Server Error')

def run_server(port=8000):
    server_address = ('', port)
    httpd = HTTPServer(server_address, RequestHandler)
    print(f'Starting server on port {port}...')
    try:
    httpd.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down server...")
        httpd.server_close()

if __name__ == '__main__':
    run_server() 