from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs
import json
import threading
import time
import logging
from uart_comm import UARTCommunication

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('backend.log'),
        logging.StreamHandler()
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

        # Initialize UART communication
        self.uart = UARTCommunication()
        self.uart.set_data_callback(self.handle_mcu_data)
        self.uart.start()
        logger.info("UART communication initialized")

    def handle_mcu_data(self, data):
        """Handle data received from MCU"""
        try:
            logger.debug(f"Received MCU data: {data}")
            
            # Update sensor values
            if 'sensors' in data:
                for sensor_id, value in data['sensors'].items():
                    if sensor_id in self.sensors:
                        self.sensors[sensor_id] = value
                        logger.debug(f"Updated sensor {sensor_id} to {value}")
            
            # Update system states
            if 'states' in data:
                for state_id, value in data['states'].items():
                    if hasattr(self, state_id):
                        setattr(self, state_id, value)
                        logger.debug(f"Updated state {state_id} to {value}")
                        
        except Exception as e:
            logger.error(f"Error handling MCU data: {e}")

    def send_to_mcu(self):
        """Send current state to MCU"""
        try:
            state = {
                'sensors': self.sensors,
                'states': {
                    'FLOWGPH1CGF': self.FLOWGPH1CGF,
                    'FLOWGPH2CGF': self.FLOWGPH2CGF,
                    'tempMainTankFlag': self.tempMainTankFlag,
                    'tempHeadGP1Flag': self.tempHeadGP1Flag,
                    'tempHeadGP2Flag': self.tempHeadGP2Flag,
                    'enableHeadGP1': self.enableHeadGP1,
                    'enableHeadGP2': self.enableHeadGP2,
                    'enableMainTank': self.enableMainTank,
                    'Pressure1': self.Pressure1,
                    'Pressure2': self.Pressure2,
                    'mainTankState': self.mainTankState,
                    'HGP1State': self.HGP1State,
                    'HGP2State': self.HGP2State,
                    'HGP1ACTIVE': self.HGP1ACTIVE,
                    'HGP2ACTIVE': self.HGP2ACTIVE
                }
            }
            self.uart.send_data(state)
            logger.debug("Sent state to MCU")
        except Exception as e:
            logger.error(f"Error sending state to MCU: {e}")

    def cleanup(self):
        """Cleanup resources"""
        try:
            self.uart.stop()
            logger.info("UART communication stopped")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

# Create global config instance
config = Config()

class RequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        logger.info(format % args)
    
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
            
            logger.debug(f"Sending data response: {data}")
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
            
            logger.debug(f"Sending error response: {data}")
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
            
            logger.debug(f"Sending gauge data: {gauge_data}")
            self.wfile.write(json.dumps(gauge_data).encode())

        elif self.path == '/getghconfig':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            gh_config = {
                "gh1": {
                    "temperature": config.tempHeadGP1SetPoint,
                    "pre_infusion": {
                        "enabled": config.HGP1PreInfusion == 1,
                        "time": config.HGP1PreInfusion
                    },
                    "extraction_time": config.HGP1ExtractionTime,
                    "volume": config.HGP1FlowVolume,
                    "pressure": config.Pressure1,
                    "flow": config.FLOWGPH1CGF
                },
                "gh2": {
                    "temperature": config.tempHeadGP2SetPoint,
                    "pre_infusion": {
                        "enabled": config.HGP2PreInfusion == 1,
                        "time": config.HGP2PreInfusion
                    },
                    "extraction_time": config.HGP2ExtractionTime,
                    "volume": config.HGP2FlowVolume,
                    "pressure": config.Pressure2,
                    "flow": config.FLOWGPH2CGF
                }
            }
            
            logger.debug(f"Sending group head config: {gh_config}")
            self.wfile.write(json.dumps(gh_config).encode())

        elif self.path == '/getmainconfig':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            main_config = {
                "temperature": config.tempMainTankSetPoint,
                "pressure": config.Pressure1,
                "flow": config.FLOWGPH1CGF
            }
            
            logger.debug(f"Sending main config: {main_config}")
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
        
        logger.info(f"Received POST request to {self.path}")
        logger.info(f"Request data: {json.dumps(params, indent=2)}")
        
        try:
            if self.path == '/setcup':
                config.cup = params['cupWarmer']
                config.tempCupFlag = True
                
            elif self.path == '/setlight':
                config.light = params['light']
                config.baristaLight = True
                
            elif self.path == '/backflush':
                machine_id = params['machineId']
                if machine_id == 1:
                    config.backflush1 = 0
                elif machine_id == 2:
                    config.backflush2 = 0
                    
            elif self.path == '/toggleOffOn':
                config.HGP12MFlag = params['machineId']
                config.HGPCheckStatus = True
                
            elif self.path == '/eco':
                config.ecomode = params['ecomode']
                
            elif self.path == '/discharg':
                config.dischargeMode = params['dischargeMode']
                
            elif self.path == '/setdata':
                config.HGP1FlowVolume = params['GH1_volume']
                config.HGP2FlowVolume = params['GH2_volume']
                config.HGP1PreInfusion = params['GH1_preInfusion']
                config.HGP2PreInfusion = params['GH2_preInfusion']
                config.HGP1ExtractionTime = params['GH1_extractionTime']
                config.HGP2ExtractionTime = params['GH2_extractionTime']
                config.tempMainTankSetPoint = params['mainTankTemp']
                config.tempHeadGP1SetPoint = params['GH1_temp']
                config.tempHeadGP2SetPoint = params['GH2_temp']

            # Send updated state to MCU
            config.send_to_mcu()
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
            self.wfile.write(b'POST request received!')
            
        except Exception as e:
            logger.error(f"Error processing POST request: {e}")
            self.send_response(500)
            self.send_header('Content-type', 'text/html')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b'Internal Server Error')

def run_server(port=8000):
    server_address = ('', port)
    httpd = HTTPServer(server_address, RequestHandler)
    logger.info(f'Starting server on port {port}...')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
        config.cleanup()
        httpd.server_close()

if __name__ == '__main__':
    run_server() 