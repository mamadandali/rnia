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
            "Voltage": 0.0,
            "GH1_ACTIVATION_FLAG": 0,
            "GH2_ACTIVATION_FLAG": 0,
            "HGP1ACTIVE": 0,
            "HGP2ACTIVE": 0,
            "mainTankState": 0
        }
        
        # Current time from RTC
        self.current_time = {
            'year': 2024,
            'month': 1,
            'day': 1,
            'hour': 0,
            'minute': 0,
            'second': 0
        }
        
        # Service sensor values
        self.service_sensors = {
            "voltage": 0.0,          # سیستم ولتاژ
            "current": 0.0,          # سیستم جریان
            "main_flow": 0.0,        # حجم جریان اصلی
            "group1_flow": 0.0,      # حجم جریان گروه 1
            "group2_flow": 0.0,      # حجم جریان گروه 2
            "main_tank_temp": 0.0,   # دمای مخزن اصلی
            "group1_upper_temp": 0.0,# دمای بالای گروه 1
            "group1_lower_temp": 0.0,# دمای پایین گروه 1
            "group2_upper_temp": 0.0,# دمای بالای گروه 2
            "group2_lower_temp": 0.0,# دمای پایین گروه 2
            "pressure": 0.0,         # فشار
            "steam_tank_level": 0,   # سطح مخزن بخار
            "group1_tank_level": 0,  # سطح مخزن گروه 1
            "group2_tank_level": 0   # سطح مخزن گروه 2
        }
        
        # UART data storage
        self.uart_data = {
            "main_boiler_temp": 1200.0,  # Will be divided by 10 when used (120.0°C)
            "gh1": {
                "temperature": 0.0,   # Will be divided by 10 when used
                "pressure": 90.0,     # 9.0 bar
                "flow": 0.0
            },
            "gh2": {
                "temperature": 0.0,   # Will be divided by 10 when used
                "pressure": 90.0,     # 9.0 bar
                "flow": 0.0
            }
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
        
        # System states - using only HGP1ACTIVE/HGP2ACTIVE as single source of truth
        self.mainTankState = 1
        self.HGP1ACTIVE = 0  # 0 = not active, 1 = active
        self.HGP2ACTIVE = 0  # 0 = not active, 1 = active
        self.HGP12MFlag = 4
        self.sebar = 0
        self.HGPCheckStatus = False
        self.backflush1 = 4
        self.backflush2 = 4

        # GH deactivation timers
        self.gh1_deactivation_timer = None
        self.gh2_deactivation_timer = None
        
        # Extraction process flags
        self.gh1_extraction_in_progress = False
        self.gh2_extraction_in_progress = False

        # Main ampere configuration - initialize with default temperature
        self.mainAmpereConfig = {
            "temperature": 1200.0  # Will be divided by 10 when used (120.0°C)
        }
        
        # Pressure configuration - initialize with default values
        self.pressureConfig = {
            "pressure": 90.0,  # 9.0 bar
            "max_pressure": 120.0,  # 12.0 bar
            "min_pressure": 0.0  # 0.0 bar
        }
        
        print("Configuration initialized")

    def schedule_gh_deactivation(self, gh_number):
        """Schedule GH deactivation after 3 seconds"""
        if gh_number == 1:
            if self.gh1_deactivation_timer:
                self.gh1_deactivation_timer.cancel()
            self.gh1_deactivation_timer = threading.Timer(3.0, self.reset_gh_active, args=[1])
            self.gh1_deactivation_timer.start()
        elif gh_number == 2:
            if self.gh2_deactivation_timer:
                self.gh2_deactivation_timer.cancel()
            self.gh2_deactivation_timer = threading.Timer(3.0, self.reset_gh_active, args=[2])
            self.gh2_deactivation_timer.start()

    def reset_gh_active(self, gh_number):
        """Reset GH active state after timer expires"""
        if gh_number == 1:
            self.HGP1ACTIVE = 0
            self.gh1_extraction_in_progress = False
            print("GH1 deactivated after timer")
        elif gh_number == 2:
            self.HGP2ACTIVE = 0
            self.gh2_extraction_in_progress = False
            print("GH2 deactivated after timer")

def handle_uart_message(flag, values):
    global config
    try:
        if flag == 46:  # داده‌های سنسور سرویس (اعشاری)
            if len(values) >= 7:
                config.service_sensors["voltage"] = values[0] / 10
                config.service_sensors["current"] = values[1] / 10
                config.service_sensors["main_flow"] = values[2] / 10
                config.service_sensors["group1_flow"] = values[3] / 10
                config.service_sensors["group2_flow"] = values[4] / 10
                config.service_sensors["group1_upper_temp"] = values[5] / 10
                config.service_sensors["group1_lower_temp"] = values[6] / 10

        elif flag == 47:  # داده‌های سنسور سرویس (اعشاری بیشتر)
            if len(values) >= 7:
                config.service_sensors["group2_upper_temp"] = values[0] / 10
                config.service_sensors["group2_lower_temp"] = values[1] / 10
                config.service_sensors["pressure"] = values[2] / 10
                config.service_sensors["main_tank_temp"] = values[3] / 10

        elif flag == 48:  # داده‌های سنسور سرویس (سطح تانک‌ها)
            if len(values) >= 3:
                config.service_sensors["steam_tank_level"] = values[0]
                config.service_sensors["group1_tank_level"] = values[1]
                config.service_sensors["group2_tank_level"] = values[2]

        elif flag == 8:  # دمای بویلر اصلی
            if len(values) >= 1:
                config.uart_data['main_boiler_temp'] = values[0]
                config.sensors["MainTankTemp"] = values[0] / 10

        elif flag == 9:  # GH1 status
            if len(values) >= 3:
                config.uart_data['gh1']['temperature'] = values[0]
                config.uart_data['gh1']['pressure'] = values[1]
                config.uart_data['gh1']['flow'] = values[2]
                config.sensors["HeadGP1TopTemp"] = values[0] / 10
                config.Pressure1 = values[1] / 10
                config.FLOWGPH1CGF = values[2]

        elif flag == 10:  # GH2 status
            if len(values) >= 3:
                config.uart_data['gh2']['temperature'] = values[0]
                config.uart_data['gh2']['pressure'] = values[1]
                config.uart_data['gh2']['flow'] = values[2]
                config.sensors["HeadGP2TopTemp"] = values[0] / 10
                config.Pressure2 = values[1] / 10
                config.FLOWGPH2CGF = values[2]

        elif flag == 13:  # GH1 extraction start/stop
            now = time.time()
            print(f"Received flag 13 with values: {values} at {now}")
            if int(values[0]) == 1:
                if not config.gh1_extraction_in_progress:
                    print("Starting GH1 extraction")
                    config.HGP1ACTIVE = 1
                    config.gh1_extraction_in_progress = True
                    config.schedule_gh_deactivation(1)
                else:
                    print("GH1 extraction already in progress, ignoring repeated start")
            elif int(values[0]) == 0:
                print("Received GH1 extraction stop (13;0), setting HGP1ACTIVE=0")
                config.HGP1ACTIVE = 0
                config.gh1_extraction_in_progress = False
                if config.gh1_deactivation_timer:
                    config.gh1_deactivation_timer.cancel()

        elif flag == 14:  # GH2 extraction start/stop
            now = time.time()
            print(f"Received flag 14 with values: {values} at {now}")
            if int(values[0]) == 1:
                if not config.gh2_extraction_in_progress:
                    print("Starting GH2 extraction")
                    config.HGP2ACTIVE = 1
                    config.gh2_extraction_in_progress = True
                    config.schedule_gh_deactivation(2)
                else:
                    print("GH2 extraction already in progress, ignoring repeated start")
            elif int(values[0]) == 0:
                print("Received GH2 extraction stop (14;0), setting HGP2ACTIVE=0")
                config.HGP2ACTIVE = 0
                config.gh2_extraction_in_progress = False
                if config.gh2_deactivation_timer:
                    config.gh2_deactivation_timer.cancel()

        elif flag == 49:  # زمان RTC
            if len(values) >= 6:
                config.current_time.update({
                    'year': values[0],
                    'month': values[1],
                    'day': values[2],
                    'hour': values[3],
                    'minute': values[4],
                    'second': values[5]
                })
                print(f"RTC time updated: {config.current_time}")

    except Exception as e:
        print(f"Error handling UART message: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")

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

# State tracking variables - initialize with actual config values
last_main_data = [
    main_boiler_state,
    gh1_button_state,
    gh2_button_state,
    int(round(config.pressureConfig['pressure'])),
    int(round(config.mainAmpereConfig['temperature']))
]
last_gh1_data = None
last_gh2_data = None

# --- UART/Flag Handling Functions (from test_backend.py, adapted for Pi UART) ---
def print_uart_message(flag, data):
    print("\n" + "="*80)
    print("UART MESSAGE SENT:")
    print("-"*80)
    print(f"FLAG: {flag}")
    print(f"DATA: {data}")
    print("-"*80)
    print("="*80 + "\n")
    logging.info(f"UART MESSAGE: {data}")
    sys.stdout.flush()
    sys.stderr.flush()

def send_gh_uart(flag, cfg, send_preinfusion=True, send_backflush=True):
    print(f"\nSending GH{flag} UART message...")
    temp = int(round(cfg['temperature'] * 10))
    ext_vol = int(round(cfg['extraction_volume']))
    ext_time = int(round(cfg['extraction_time']))
    purge = int(round(cfg.get('purge', 0)))
    s = f"{flag};{temp};{ext_vol};{ext_time};{purge}"
    print(f"GH{flag} main config - Temp: {temp/10}°C, Volume: {ext_vol}, Time: {ext_time}s, Purge: {purge}")
    print_uart_message(flag, s)
    uart.send_gh_config(flag, cfg)
    if send_preinfusion:
        preinf_data = cfg.get('pre_infusion', {})
        if isinstance(preinf_data, dict):
            preinf_value = int(round(preinf_data.get('time', 0))) if preinf_data.get('enabled', False) else 0
        else:
            preinf_value = int(round(preinf_data)) if preinf_data > 0 else 0
        preinf_flag = 15 if flag == 1 else 16
        preinf_s = f"{preinf_flag};{preinf_value}"
        print(f"Sending pre-infusion config for GH{flag}: {preinf_value}s")
        print_uart_message(preinf_flag, preinf_s)
        uart.send_preinfusion(flag, preinf_value)
    if send_backflush:
        backflush_flag = 11 if flag == 1 else 12
        backflush_value = 1 if cfg.get('backflush', False) else 0
        backflush_s = f"{backflush_flag};{backflush_value}"
        print(f"Sending backflush status for GH{flag}: {backflush_value}")
        print_uart_message(backflush_flag, backflush_s)
        uart.send_backflush(flag, backflush_value)

def send_main_uart():
    """Send flag 3 UART message with format: 3;mainboiler button state;gh1 button state;gh2 b state;pressure;main boiler temp"""
    # Use default values if no data is present
    pressure = int(round(config.pressureConfig.get('pressure', 90.0)))  # Default 9.0 bar
    main_temp = int(round(config.mainAmpereConfig.get('temperature', 1200.0)))  # Default 120.0°C
    
    # Format: 3;mainboiler button state;gh1 button state;gh2 b state;pressure;main boiler temp
    s = f"3;{main_boiler_state};{gh1_button_state};{gh2_button_state};{pressure};{main_temp}"
    
    print("\nSending flag 3 UART message:")
    print("Format: 3;mainboiler button state;gh1 button state;gh2 b state;pressure;main boiler temp")
    print(f"Values: 3;{main_boiler_state};{gh1_button_state};{gh2_button_state};{pressure};{main_temp}")
    print("\nButton states:")
    print(f"- Main boiler button: {main_boiler_state}")
    print(f"- GH1 button: {gh1_button_state}")
    print(f"- GH2 button: {gh2_button_state}")
    print(f"\nOther values:")
    print(f"- Pressure: {pressure}")
    print(f"- Main boiler temp: {main_temp}")
    
    simulate_uart_send(s)

def send_system_status_uart():
    s = f"4;{mode_state};{barista_light};{cup_warmer}"
    print("\nSending system status UART message...")
    print(f"Current values - Mode: {mode_state}, Light: {barista_light}, Cup: {cup_warmer}")
    print_uart_message(4, s)
    uart.send_system_status(mode_state, boiler_discharge, barista_light, cup_warmer)

def update_system_status(mode=None, light=None, cup=None):
    global mode_state, barista_light, cup_warmer
    print("\nUpdating system status...")
    print(f"Current values - mode: {mode_state}, light: {barista_light}, cup: {cup_warmer}")
    print(f"New values - mode: {mode}, light: {light}, cup: {cup}")
    changed = False
    if mode is not None and mode != mode_state:
        print(f"Mode changing from {mode_state} to {mode}")
        mode_state = mode
        changed = True
    if light is not None and light != barista_light:
        print(f"Barista light changing from {barista_light} to {light}")
        barista_light = light
        changed = True
    if cup is not None and cup != cup_warmer:
        print(f"Cup warmer changing from {cup_warmer} to {cup}")
        cup_warmer = cup
        changed = True
    if changed:
        print("Values changed, sending system status update")
        send_system_status_uart()
    else:
        print("No values changed, skipping UART update")

def validate_gh_config(config: dict) -> dict:
    """Validate and sanitize group head configuration values"""
    validated = config.copy()
    
    # Temperature validation (86-97°C)
    validated['temperature'] = max(86.0, min(97.0, float(config.get('temperature', 90.0))))
    
    # Volume validation (20-85ml)
    volume = float(config.get('volume', 20.0))
    if volume < 20.0:
        # If volume is below minimum, allow it to be increased but not decreased
        validated['volume'] = max(volume, 0.0)  # Allow any non-negative value
    else:
        validated['volume'] = min(85.0, volume)  # Cap at maximum
    
    # Time validation (10-40s)
    time = float(config.get('extraction_time', 20.0))
    if time < 10.0:
        # If time is below minimum, allow it to be increased but not decreased
        validated['extraction_time'] = max(time, 0.0)  # Allow any non-negative value
    else:
        validated['extraction_time'] = min(40.0, time)  # Cap at maximum
    
    # Pre-infusion validation
    pre_infusion = config.get('pre_infusion', {})
    if isinstance(pre_infusion, dict):
        validated['pre_infusion'] = {
            'enabled': bool(pre_infusion.get('enabled', False)),
            'time': max(0.0, min(10.0, float(pre_infusion.get('time', 0.0))))
        }
    else:
        validated['pre_infusion'] = {
            'enabled': False,
            'time': 0.0
        }
    
    # Purge validation (3-6)
    validated['purge'] = max(3, min(6, int(config.get('purge', 3))))
    
    # Backflush validation
    validated['backflush'] = bool(config.get('backflush', False))
    
    return validated

def send_service_uart(enabled: bool):
    """Send service mode status (flag 21)"""
    try:
        value = 1 if enabled else 0
        message = f"21;{value}"
        print(f"\n=== Sending Service Mode UART Message ===")
        print(f"Service mode: {'enabled' if enabled else 'disabled'}")
        print(f"UART message: {message}")
        print("=======================================\n")
        uart.send_string(message)
    except Exception as e:
        print(f"\n!!! Service Mode UART Send Error !!!")
        print(f"Error: {e}")

def send_actuator_uart(flag: int, enabled: bool):
    """Send actuator control UART message"""
    try:
        value = 1 if enabled else 0
        message = f"{flag};{value}"
        print(f"\n=== Sending Actuator Control UART Message ===")
        print(f"Flag: {flag}")
        print(f"Enabled: {enabled}")
        print(f"UART message: {message}")
        print("===========================================\n")
        uart.send_string(message)
    except Exception as e:
        print(f"\n!!! Actuator Control UART Send Error !!!")
        print(f"Error: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")

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
            
            data = {
                "gh1": {
                    "temperature": config.gh1_config['temperature'],
                    "pre_infusion": config.gh1_config['pre_infusion'],
                    "extraction_time": config.gh1_config['extraction_time'],
                    "volume": config.gh1_config['extraction_volume'],
                    "purge": config.gh1_config['purge'],
                    "backflush": config.gh1_config['backflush'],
                    "pressure": config.uart_data['gh1']['pressure'],
                    "flow": config.uart_data['gh1']['flow']
                },
                "gh2": {
                    "temperature": config.gh2_config['temperature'],
                    "pre_infusion": config.gh2_config['pre_infusion'],
                    "extraction_time": config.gh2_config['extraction_time'],
                    "volume": config.gh2_config['extraction_volume'],
                    "purge": config.gh2_config['purge'],
                    "backflush": config.gh2_config['backflush'],
                    "pressure": config.uart_data['gh2']['pressure'],
                    "flow": config.uart_data['gh2']['flow']
                }
            }
            
            self.wfile.write(json.dumps(data).encode())
            return

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
            return

        elif self.path == '/getdata':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            data = config.sensors.copy()
            
            # Add UART data
            data.update({
                "MainTankTemp": config.uart_data['main_boiler_temp'] / 10,
                "HeadGP1TopTemp": config.uart_data['gh1']['temperature'] / 10,
                "HeadGP2TopTemp": config.uart_data['gh2']['temperature'] / 10,
                "PressureGPH1": config.uart_data['gh1']['pressure'],
                "PressureGPH2": config.uart_data['gh2']['pressure'],
                "HeadGP1WaterFlow": config.uart_data['gh1']['flow'],
                "HeadGP2WaterFlow": config.uart_data['gh2']['flow'],
                "GH1_ACTIVATION_FLAG": gh1_button_state,
                "GH2_ACTIVATION_FLAG": gh2_button_state,
                "HGP1ACTIVE": config.HGP1ACTIVE,
                "HGP2ACTIVE": config.HGP2ACTIVE,
                "mainTankState": config.mainTankState
            })
            
            self.wfile.write(json.dumps(data).encode())
            return

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
            return

        elif self.path == '/getgauge':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            query = parse_qs(self.path.split('?')[1] if '?' in self.path else '')
            gh_id = query.get('gh_id', ['1'])[0]
            
            gh_data = config.uart_data['gh1'] if gh_id == '1' else config.uart_data['gh2']
            
            gauge_data = {
                "pressure": {
                    "value": gh_data['pressure'],
                    "min": 0,
                    "max": 12,
                    "unit": "bar"
                },
                "temperature": {
                    "value": gh_data['temperature'] / 10,
                    "min": 0,
                    "max": 120,
                    "unit": "°C"
                },
                "flow": {
                    "value": gh_data['flow'],
                    "min": 0,
                    "max": 5,
                    "unit": "L/min"
                }
            }
            
            self.wfile.write(json.dumps(gauge_data).encode())
            return

        elif self.path == '/getpressureconfig':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            pressure_config = config.pressureConfig.copy()
            self.wfile.write(json.dumps(pressure_config).encode())
            return

        elif self.path == '/getservicedata':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            self.wfile.write(json.dumps(config.service_sensors).encode())
            return

        else:
            self.send_response(404)
            self.send_header('Content-type', 'text/html')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b'404 Not Found')

    def do_POST(self):
        print(f"\n=== POST Request to {self.path} ===")
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8')
            print(f"Raw POST data: {post_data}")
            params = json.loads(post_data)
            print(f"Parsed POST data: {json.dumps(params, indent=2)}")

            if self.path == '/setpressureconfig':
                print("\n=== Processing Pressure Config Update ===")
                new_config = params.get('config', {})
                config.pressureConfig.update({
                    "pressure": float(new_config.get('pressure', config.pressureConfig['pressure'])),
                    "max_pressure": float(new_config.get('max_pressure', config.pressureConfig['max_pressure'])),
                    "min_pressure": float(new_config.get('min_pressure', config.pressureConfig['min_pressure']))
                })
                
                new_main = [main_boiler_state, gh1_button_state, gh2_button_state, 
                          int(round(config.pressureConfig['pressure'])), 
                          int(round(config.mainAmpereConfig['temperature']))]
                if last_main_data != new_main:
                    send_main_uart()
                    last_main_data = new_main

            elif self.path == '/setmainconfig':
                print("\n=== Processing Main Config Update ===")
                new_config = params.get('config', {})
                config.mainAmpereConfig.update({
                    "temperature": float(new_config.get('temperature', config.mainAmpereConfig['temperature']))
                })
                
                new_main = [main_boiler_state, gh1_button_state, gh2_button_state,
                          int(round(config.pressureConfig['pressure'])), 
                          int(round(config.mainAmpereConfig['temperature']))]
                if last_main_data != new_main:
                    send_main_uart()
                    last_main_data = new_main

            elif self.path == '/saveghconfig':
                print("\n=== Processing GH Config Save ===")
                new_config = params.get('config', {})
                gh_id = params.get('gh_id', 'ghundefined')

                if gh_id == 'ghundefined':
                    query = parse_qs(self.path.split('?')[1] if '?' in self.path else '')
                    amper_id = query.get('amperId', ['1'])[0]
                    gh_id = f'gh{amper_id}'

                preinf_data = new_config.get('pre_infusion', {})
                if isinstance(preinf_data, dict):
                    preinf = {
                        "enabled": bool(preinf_data.get('enabled', False)),
                        "time": int(preinf_data.get('time', 0))
                    }
                else:
                    preinf_time = int(preinf_data)
                    preinf = {
                        "enabled": preinf_time > 0,
                        "time": preinf_time
                    }

                if gh_id == 'gh1':
                    extraction_time = int(new_config.get('extraction_time', config.gh1_config['extraction_time']))
                    ext_volume = new_config.get('extraction_volume', new_config.get('volume', config.gh1_config['extraction_volume']))
                    config.gh1_config.update({
                        "temperature": float(new_config.get('temperature', config.gh1_config['temperature'])),
                        "extraction_volume": int(ext_volume),
                        "extraction_time": extraction_time,
                        "pre_infusion": preinf,
                        "purge": int(new_config.get('purge', config.gh1_config['purge'])),
                        "backflush": bool(new_config.get('backflush', config.gh1_config['backflush']))
                    })
                    config.HGP1ExtractionTime = extraction_time
                    config.HGP1PreInfusion = preinf['time'] if preinf['enabled'] else 0
                    send_gh_uart(1, config.gh1_config)
                elif gh_id == 'gh2':
                    extraction_time = int(new_config.get('extraction_time', config.gh2_config['extraction_time']))
                    ext_volume = new_config.get('extraction_volume', new_config.get('volume', config.gh2_config['extraction_volume']))
                    config.gh2_config.update({
                        "temperature": float(new_config.get('temperature', config.gh2_config['temperature'])),
                        "extraction_volume": int(ext_volume),
                        "extraction_time": extraction_time,
                        "pre_infusion": preinf,
                        "purge": int(new_config.get('purge', config.gh2_config['purge'])),
                        "backflush": bool(new_config.get('backflush', config.gh2_config['backflush']))
                    })
                    config.HGP2ExtractionTime = extraction_time
                    config.HGP2PreInfusion = preinf['time'] if preinf['enabled'] else 0
                    send_gh_uart(2, config.gh2_config)

            elif self.path == '/updatepreinfusion':
                print("\n=== Processing Pre-Infusion Update ===")
                gh_id = params.get('gh_id', 'ghundefined')
                preinf_data = params.get('pre_infusion', {})
                if gh_id == 'gh1':
                    config.gh1_config['pre_infusion'] = preinf_data
                    preinf_value = int(preinf_data.get('time', 0)) if preinf_data.get('enabled', False) else 0
                    send_gh_uart(1, config.gh1_config, send_preinfusion=True, send_backflush=False)
                elif gh_id == 'gh2':
                    config.gh2_config['pre_infusion'] = preinf_data
                    preinf_value = int(preinf_data.get('time', 0)) if preinf_data.get('enabled', False) else 0
                    send_gh_uart(2, config.gh2_config, send_preinfusion=True, send_backflush=False)

            elif self.path == '/updatebackflush':
                print("\n=== Processing Backflush Update ===")
                gh_id = params.get('gh_id', 'ghundefined')
                enabled = bool(params.get('backflush', False))
                if gh_id == 'gh1':
                    config.gh1_config['backflush'] = enabled
                    send_gh_uart(1, config.gh1_config, send_preinfusion=False, send_backflush=True)
                elif gh_id == 'gh2':
                    config.gh2_config['backflush'] = enabled
                    send_gh_uart(2, config.gh2_config, send_preinfusion=False, send_backflush=True)

            elif self.path == '/setstatusupdate':
                print("\n=== Processing Status Update ===")
                target = params.get('target')
                status = params.get('status')
                state_changed = False
                
                if target == 'main_boiler':
                    new_state = 1 if status else 0
                    if new_state != main_boiler_state:
                        main_boiler_state = new_state
                        state_changed = True
                elif target == 'gh1':
                    new_state = 1 if status else 0
                    if new_state != gh1_button_state:
                        gh1_button_state = new_state
                        state_changed = True
                elif target == 'gh2':
                    new_state = 1 if status else 0
                    if new_state != gh2_button_state:
                        gh2_button_state = new_state
                        state_changed = True
                
                if state_changed or (target == 'main_boiler' and status) or (target == 'gh1' and status) or (target == 'gh2' and status):
                    new_main = [main_boiler_state, gh1_button_state, gh2_button_state,
                              int(round(config.pressureConfig['pressure'])), 
                              int(round(config.mainAmpereConfig['temperature']))]
                    send_main_uart()
                    last_main_data = new_main

            elif self.path == '/savemainconfig':
                print("\n=== Processing Main Config Save ===")
                new_config = params.get('config', {})
                eco_mode = new_config.get('eco_mode')
                barista_light_val = new_config.get('barista_light')
                cup_warmer_val = new_config.get('cup_warmer')
                mode_map = {'off': 0, 'eco': 1, 'sleep': 2}
                mode_val = mode_map.get(eco_mode, None) if eco_mode is not None else None
                
                light_val = None
                if barista_light_val is not None:
                    if isinstance(barista_light_val, dict):
                        light_val = int(barista_light_val.get('percentage', 0)) if barista_light_val.get('enabled', False) else 0
                    else:
                        light_val = int(barista_light_val)
                
                cup_val = None
                if cup_warmer_val is not None:
                    if isinstance(cup_warmer_val, dict):
                        cup_val = int(cup_warmer_val.get('percentage', 0)) if cup_warmer_val.get('enabled', False) else 0
                    else:
                        cup_val = int(cup_warmer_val)
                
                if eco_mode is not None or barista_light_val is not None or cup_warmer_val is not None:
                    update_system_status(mode=mode_val, light=light_val, cup=cup_val)

            elif self.path == '/setboilerdischarge':
                print("\n=== Processing Boiler Discharge Update ===")
                discharge_map = {'none': 0, 'drain_refill': 1, 'drain_shutdown': 2}
                discharge_value = params.get('discharge', 'none')
                discharge_flag_value = discharge_map.get(discharge_value, 0)
                s = f"17;{discharge_flag_value}"
                uart.send_string(s)

            elif self.path == '/setactuator':
                print("\n=== Processing Actuator Control Update ===")
                actuator_id = params.get('actuator_id')
                enabled = bool(params.get('enabled', False))
                
                actuator_flags = {
                    'main_boiler': 1,
                    'gh1_water': 2,
                    'gh2_water': 3,
                    'gh1_steam': 4,
                    'gh2_steam': 5,
                    'gh1_drain': 6,
                    'gh2_drain': 7,
                    'main_drain': 8,
                    'cup_warmer': 9,
                    'barista_light': 10
                }
                
                if actuator_id in actuator_flags:
                    flag = actuator_flags[actuator_id]
                    send_actuator_uart(flag, enabled)
                else:
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': 'Unknown actuator ID'}).encode())
                    return

            elif self.path == '/setservicemode':
                print("\n=== Processing Service Mode Update ===")
                enabled = bool(params.get('enabled', False))
                send_service_uart(enabled)

            elif self.path == '/setdatetime':
                print("\n=== Processing Date & Time Update ===")
                year = int(params.get('year', 0))
                month = int(params.get('month', 0))
                day = int(params.get('day', 0))
                hour = int(params.get('hour', 0))
                minute = int(params.get('minute', 0))
                second = int(params.get('second', 0))
                last_two_digits = year % 100
                uart_message = f"19;{last_two_digits:02d};{month:02d};{day:02d};{hour:02d};{minute:02d};{second:02d}"
                uart.send_string(uart_message)

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
