import json
import logging
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional, Callable
import threading
import time
import random
from urllib.parse import parse_qs
from datetime import datetime
import serial

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[
        logging.FileHandler('backend.log', mode='w'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Add filter to ignore /getdata requests
class GetDataFilter(logging.Filter):
    def filter(self, record):
        return not ('GET /getdata' in record.getMessage())

# Apply filter to all handlers
for handler in logger.handlers:
    handler.addFilter(GetDataFilter())

class UARTCommunicator:
    def __init__(self, port='/dev/ttyAMA0', baudrate=9600):
        self.port = port
        self.baudrate = baudrate
        self.serial = None
        self.running = False
        self.thread = None
        self.current_data = {
            'main_temperature': 0,
            'gh1': {'temperature': 0, 'pressure': 0, 'flow': 0},
            'gh2': {'temperature': 0, 'pressure': 0, 'flow': 0}
        }
        self.last_gh1_start = 0
        self.last_gh2_start = 0
        self.last_service_mode_state = False
        self.last_actuator_states = {i: False for i in range(22, 45)}
        self.data_lock = threading.Lock()
        self.message_callback = None

    def set_message_callback(self, callback: Callable[[int, list], None]):
        """Set callback for received messages"""
        self.message_callback = callback

    def start(self):
        """Start UART communication"""
        try:
            print("\n=== Starting UART Communication ===")
            print(f"Attempting to open port: {self.port}")
            print(f"Baudrate: {self.baudrate}")
            
            # Close port if it's already open
            if self.serial and self.serial.is_open:
                print("Closing existing port connection...")
                self.serial.close()
                time.sleep(0.5)
            
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1,
                write_timeout=1  # Add write timeout
            )
            
            # Reset buffers
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()
            
            print(f"Serial port opened successfully: {self.serial.is_open}")
            print(f"Port settings: {self.serial.get_settings()}")
            print(f"Input buffer size: {self.serial.in_waiting}")
            print(f"Output buffer size: {self.serial.out_waiting}")
            
            self.running = True
            self.thread = threading.Thread(target=self._read_loop)
            self.thread.daemon = True
            self.thread.start()
            
            logging.info(f"UART communication started on {self.port}")
            print(f"UART communication started on {self.port}")
            print("=== UART Initialization Complete ===\n")
            
        except serial.SerialException as e:
            print(f"\n!!! Serial Port Error !!!")
            print(f"Error type: {type(e).__name__}")
            print(f"Error message: {str(e)}")
            print("Common causes:")
            print("1. Port not found")
            print("2. Permission denied")
            print("3. Port already in use")
            print("4. Wrong port name")
            print("============================\n")
            logging.error(f"Failed to start UART communication: {str(e)}")
            raise
        except Exception as e:
            print(f"\n!!! General UART Error !!!")
            print(f"Error type: {type(e).__name__}")
            print(f"Error message: {str(e)}")
            print("============================\n")
            logging.error(f"Failed to start UART communication: {str(e)}")
            raise

    def stop(self):
        """Stop UART communication"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        if self.serial and self.serial.is_open:
            self.serial.close()
        logging.info("UART communication stopped")
        print("UART communication stopped")

    def _read_loop(self):
        """Background thread for reading UART data"""
        buffer = ""
        print("\n=== Starting UART Read Loop ===")
        print("Waiting for data...")
        
        while self.running:
            try:
                if self.serial.in_waiting:
                    data = self.serial.read(self.serial.in_waiting).decode('utf-8')
                    print(f"\nRaw UART data received: {repr(data)}")  # Using repr to show special characters
                    buffer += data
                    
                    # Process complete messages
                    while '\n' in buffer:
                        message, buffer = buffer.split('\n', 1)
                        message = message.strip()
                        if message:
                            print(f"\nProcessing message: {message}")
                            self.process_message(message)
                            
            except serial.SerialException as e:
                print(f"\n!!! Serial Read Error !!!")
                print(f"Error type: {type(e).__name__}")
                print(f"Error message: {str(e)}")
                print("============================\n")
                logging.error(f"Error in UART read loop: {str(e)}")
                time.sleep(1)  # Prevent tight loop on error
            except Exception as e:
                print(f"\n!!! General Read Error !!!")
                print(f"Error type: {type(e).__name__}")
                print(f"Error message: {str(e)}")
                print("============================\n")
                logging.error(f"Error in UART read loop: {str(e)}")
                time.sleep(1)  # Prevent tight loop on error

    def process_message(self, message: str):
        """Process a received UART message"""
        try:
            parts = message.split(';')
            if len(parts) < 2:
                print(f"Invalid UART message format: {message}")
                return

            flag = int(parts[0])
            values = [float(x) if '.' in x else int(x) for x in parts[1:]]
            
            # Print received message
            print(f"\nUART IN: {message}")
            
            # Update current data based on flag
            with self.data_lock:
                if flag == 50:  # Update system time
                    if len(values) >= 6:
                        year, month, day, hour, minute, second = [int(x) for x in values[:6]]
                        config.current_time.update({
                            "year": year,
                            "month": month,
                            "day": day,
                            "hour": hour,
                            "minute": minute,
                            "second": second
                        })
                elif flag == 46:  # Service sensors - part 1
                    config.service_sensors["voltage"] = values[0] / 10
                    config.service_sensors["current"] = values[1] / 10
                    config.service_sensors["main_flow"] = values[2] / 10
                    config.service_sensors["group1_flow"] = values[3] / 10
                    config.service_sensors["group2_flow"] = values[4] / 10
                    config.service_sensors["main_tank_temp"] = values[5] / 10
                    config.service_sensors["group1_upper_temp"] = values[6] / 10
                elif flag == 47:  # Service sensors - part 2
                    config.service_sensors["group1_lower_temp"] = values[0] / 10
                    config.service_sensors["group2_upper_temp"] = values[1] / 10
                    config.service_sensors["group2_lower_temp"] = values[2] / 10
                    config.service_sensors["pressure"] = values[3] / 10
                elif flag == 48:  # Service sensors - tank levels
                    config.service_sensors["steam_tank_level"] = values[0]
                    config.service_sensors["group1_tank_level"] = values[1]
                    config.service_sensors["group2_tank_level"] = values[2]
                elif flag == 8:  # Main boiler temperature
                    self.current_data['main_temperature'] = values[0]
                    config.sensors["MainTankTemp"] = values[0] / 10
                elif flag == 1:  # GH1 config
                    self.current_data['gh1'].update({
                        "temperature": values[0],
                        "pressure": values[1] / 10,
                        "flow": values[2]
                    })
                    config.gh1_config.update({
                        "temperature": values[0] / 10,
                        "extraction_volume": values[1],
                        "extraction_time": values[2],
                        "purge": values[3]
                    })
                elif flag == 2:  # GH2 config
                    self.current_data['gh2'].update({
                        "temperature": values[0],
                        "pressure": values[1] / 10,
                        "flow": values[2]
                    })
                    config.gh2_config.update({
                        "temperature": values[0] / 10,
                        "extraction_volume": values[1],
                        "extraction_time": values[2],
                        "purge": values[3]
                    })
                elif flag == 9:  # GH1 status
                    self.current_data['gh1'].update({
                        "temperature": values[0],
                        "pressure": values[1] / 10,
                        "flow": values[2]
                    })
                    config.sensors["HeadGP1TopTemp"] = values[0] / 10
                    config.Pressure1 = values[1] / 10
                    config.FLOWGPH1CGF = values[2]
                elif flag == 10:  # GH2 status
                    self.current_data['gh2'].update({
                        "temperature": values[0],
                        "pressure": values[1] / 10,
                        "flow": values[2]
                    })
                    config.sensors["HeadGP2TopTemp"] = values[0] / 10
                    config.Pressure2 = values[1] / 10
                    config.FLOWGPH2CGF = values[2]
                elif flag == 13:  # GH1 extraction start/stop
                    now = time.time()
                    if int(values[0]) == 1:
                        if not config.gh1_extraction_in_progress:
                            config.HGP1ACTIVE = 1
                            config.gh1_extraction_in_progress = True
                            self.last_gh1_start = now
                    elif int(values[0]) == 0:
                        config.HGP1ACTIVE = 0
                        config.gh1_extraction_in_progress = False
                elif flag == 14:  # GH2 extraction start/stop
                    now = time.time()
                    if int(values[0]) == 1:
                        if not config.gh2_extraction_in_progress:
                            config.HGP2ACTIVE = 1
                            config.gh2_extraction_in_progress = True
                            self.last_gh2_start = now
                    elif int(values[0]) == 0:
                        config.HGP2ACTIVE = 0
                        config.gh2_extraction_in_progress = False

            # Call message callback if set
            if self.message_callback:
                self.message_callback(flag, values)

            # Print updated data
            print("\nUpdated Current Data:")
            print(json.dumps(self.current_data, indent=2))
            print("\nUpdated Config Data:")
            print(json.dumps({
                "gh1_config": config.gh1_config,
                "gh2_config": config.gh2_config,
                "sensors": config.sensors,
                "service_sensors": config.service_sensors
            }, indent=2))

        except ValueError as e:
            print(f"Error parsing UART message: {e}")
        except Exception as e:
            print(f"Error processing UART message: {e}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")

    def get_current_data(self) -> Dict[str, Any]:
        """Get current sensor data"""
        with self.data_lock:
            return self.current_data.copy()

    def send_string(self, message: str):
        """Send a string message over UART"""
        try:
            print(f"\n=== Sending UART Message ===")
            print(f"Message: {message}")
            
            if not self.serial or not self.serial.is_open:
                print("!!! Error: Serial port not initialized or not open !!!")
                return
            
            # Add delay before sending
            time.sleep(0.1)  # 100ms delay
            
            # Prepare and send message
            encoded_message = f"{message}\n".encode('utf-8')
            print(f"Encoded message: {repr(encoded_message)}")
            
            # Send message
            bytes_written = self.serial.write(encoded_message)
            self.serial.flush()  # Ensure data is sent
            
            print(f"Wrote {bytes_written} bytes")
            logging.info(f"UART message sent: {message}")
            
            # Add delay after sending
            time.sleep(0.1)  # 100ms delay
            
            print("=== Message Send Complete ===\n")
            
        except Exception as e:
            print(f"\n!!! UART Send Error !!!")
            print(f"Error type: {type(e).__name__}")
            print(f"Error message: {str(e)}")
            print("============================\n")
            logging.error(f"Error sending UART message: {str(e)}")

    def send_gh_config(self, gh_id: int, config: Dict[str, Any]):
        """Send group head configuration (flag 1 or 2) - NO pre-infusion or backflush here"""
        try:
            print(f"\n=== Sending GH{gh_id} Main Config ===")
            flag = 1 if gh_id == 1 else 2
            temp = int(round(config['temperature']))
            ext_vol = int(round(config['extraction_volume']))
            ext_time = int(round(config['extraction_time']))
            purge = int(round(config.get('purge', 0)))
            message = f"{flag};{temp};{ext_vol};{ext_time};{purge}"
            print(f"UART main config: {message}")
            self.send_string(message)
            print(f"=== GH{gh_id} Main Config Sent ===\n")
        except Exception as e:
            print(f"\n!!! GH Config Send Error !!!")
            print(f"Error type: {type(e).__name__}")
            print(f"Error message: {str(e)}")
            print(f"GH ID: {gh_id}")
            print(f"Config: {config}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            print("============================\n")

    def send_preinfusion(self, gh_id: int, time_value: int):
        """Send pre-infusion time (flag 15 or 16)"""
        try:
            flag = 15 if gh_id == 1 else 16
            message = f"{flag};{time_value}"
            print(f"UART pre-infusion: {message}")
            self.send_string(message)
        except Exception as e:
            print(f"\n!!! Pre-infusion Send Error !!!")
            print(f"Error: {e}")

    def send_backflush(self, gh_id: int, enabled: bool):
        """Send backflush status (flag 11 or 12)"""
        try:
            flag = 11 if gh_id == 1 else 12
            value = 1 if enabled else 0
            message = f"{flag};{value}"
            print(f"UART backflush: {message}")
            self.send_string(message)
        except Exception as e:
            print(f"\n!!! Backflush Send Error !!!")
            print(f"Error: {e}")

    def send_main_status(self, main_boiler: int, gh1_button: int, gh2_button: int, pressure: int, temp: int):
        """Send main status (flag 3)"""
        try:
            print(f"\n=== Sending Main Status ===")
            print(f"Main boiler: {main_boiler}")
            print(f"GH1 button: {gh1_button}")
            print(f"GH2 button: {gh2_button}")
            print(f"Pressure: {pressure} bar")
            print(f"Temperature: {temp/10}°C (raw: {temp})")
            
            message = f"3;{main_boiler};{gh1_button};{gh2_button};{pressure};{temp}"
            self.send_string(message)
            
            print("=== Main Status Sent ===\n")
            
        except Exception as e:
            print(f"\n!!! Main Status Send Error !!!")
            print(f"Error type: {type(e).__name__}")
            print(f"Error message: {str(e)}")
            print(f"Values: main_boiler={main_boiler}, gh1={gh1_button}, gh2={gh2_button}, pressure={pressure}, temp={temp}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            print("===========================\n")

    def send_system_status(self, mode: int, light: int, cup: int, month: int, day: int, hour: int, minute: int):
        """Send system status (flag 4)"""
        try:
            print(f"\n=== Sending System Status ===")
            print(f"Mode: {mode}")
            print(f"Light: {light}%")
            print(f"Cup warmer: {cup}%")
            print(f"Time: {month}/{day} {hour}:{minute}")
            
            message = f"4;{mode};{light};{cup};{month};{day};{hour};{minute}"
            self.send_string(message)
            
            print("=== System Status Sent ===\n")
            
        except Exception as e:
            print(f"\n!!! System Status Send Error !!!")
            print(f"Error: {e}")

    def send_gh_activation(self, gh_id: int, is_active: bool):
        """Send group head activation status (flag 13 or 14)"""
        try:
            flag = 13 if gh_id == 1 else 14
            value = 1 if is_active else 0
            message = f"{flag};{value}"
            print(f"UART GH activation: {message}")
            self.send_string(message)
        except Exception as e:
            print(f"\n!!! GH Activation Send Error !!!")
            print(f"Error: {e}")

    def send_boiler_discharge(self, discharge_flag_value: int):
        """Send boiler discharge command (flag 17)"""
        try:
            message = f"17;{discharge_flag_value}"
            print(f"UART boiler discharge: {message}")
            self.send_string(message)
        except Exception as e:
            print(f"\n!!! Boiler Discharge Send Error !!!")
            print(f"Error: {e}")

    def send_service_mode(self, enabled: bool):
        """Send service mode status (flag 21)"""
        try:
            value = 1 if enabled else 0
            message = f"21;{value}"
            print(f"UART service mode: {message}")
            self.send_string(message)
        except Exception as e:
            print(f"\n!!! Service Mode Send Error !!!")
            print(f"Error: {e}")

    def send_actuator(self, flag: int, enabled: bool):
        """Send actuator control (flag 22-44)"""
        try:
            value = 1 if enabled else 0
            message = f"{flag};{value}"
            print(f"UART actuator control: {message}")
            self.send_string(message)
        except Exception as e:
            print(f"\n!!! Actuator Control Send Error !!!")
            print(f"Error: {e}")

    def send_datetime(self, year: int, month: int, day: int, hour: int, minute: int, second: int):
        """Send date and time (flag 19)"""
        try:
            last_two_digits = year % 100
            message = f"19;{last_two_digits:02d};{month:02d};{day:02d};{hour:02d};{minute:02d};{second:02d}"
            print(f"UART datetime: {message}")
            self.send_string(message)
        except Exception as e:
            print(f"\n!!! DateTime Send Error !!!")
            print(f"Error: {e}")

    def send_gh_uart(self, flag, cfg, send_preinfusion=False, send_backflush=False):
        """Send group head configuration"""
        try:
            print(f"\n=== Sending GH{flag} Config ===")
            temp = int(round(cfg['temperature'] * 10))
            ext_vol = int(round(cfg['extraction_volume']))
            ext_time = int(round(cfg['extraction_time']))
            purge = int(round(cfg.get('purge', 0)))
            
            # Send main configuration
            message = f"{flag};{temp};{ext_vol};{ext_time};{purge}"
            print(f"Main config message: {message}")
            self.send_string(message)
            
            # Send pre-infusion if requested
            if send_preinfusion:
                preinf_data = cfg.get('pre_infusion', {})
                if isinstance(preinf_data, dict):
                    preinf_value = int(round(preinf_data.get('time', 0))) if preinf_data.get('enabled', False) else 0
                else:
                    preinf_value = int(round(preinf_data)) if preinf_data > 0 else 0
                preinf_flag = 15 if flag == 1 else 16
                preinf_message = f"{preinf_flag};{preinf_value}"
                print(f"Pre-infusion message: {preinf_message}")
                self.send_string(preinf_message)
            
            # Send backflush if requested
            if send_backflush:
                backflush_flag = 11 if flag == 1 else 12
                backflush_value = 1 if cfg.get('backflush', False) else 0
                backflush_message = f"{backflush_flag};{backflush_value}"
                print(f"Backflush message: {backflush_message}")
                self.send_string(backflush_message)
            
            print(f"=== GH{flag} Config Sent ===\n")
            
        except Exception as e:
            print(f"\n!!! GH Config Send Error !!!")
            print(f"Error type: {type(e).__name__}")
            print(f"Error message: {str(e)}")
            print(f"GH ID: {flag}")
            print(f"Config: {cfg}")
            print("============================\n")

    def send_main_uart(self, main_boiler_state, gh1_button_state, gh2_button_state):
        """Send main status UART message"""
        try:
            print(f"\n=== Sending Main Status ===")
            pressure = int(round(config.pressureConfig.get('pressure', 90.0)))
            main_temp = int(round(config.mainAmpereConfig.get('temperature', 1200.0)))
            
            message = f"3;{main_boiler_state};{gh1_button_state};{gh2_button_state};{pressure};{main_temp}"
            print(f"Main status message: {message}")
            self.send_string(message)
            
            print("=== Main Status Sent ===\n")
            
        except Exception as e:
            print(f"\n!!! Main Status Send Error !!!")
            print(f"Error type: {type(e).__name__}")
            print(f"Error message: {str(e)}")
            print("============================\n")

    def send_system_status_uart(self, mode=None, light=None, cup=None, month=None, day=None, hour=None, minute=None):
        """Send system status UART message"""
        try:
            print(f"\n=== Sending System Status ===")
            mode = mode if mode is not None else config.mode_state
            light = light if light is not None else config.barista_light
            cup = cup if cup is not None else config.cup_warmer
            month = month if month is not None else 1
            day = day if day is not None else 1
            hour = hour if hour is not None else 0
            minute = minute if minute is not None else 0
            
            message = f"4;{mode};{light};{cup};{month};{day};{hour};{minute}"
            print(f"System status message: {message}")
            self.send_string(message)
            
            print("=== System Status Sent ===\n")
            
        except Exception as e:
            print(f"\n!!! System Status Send Error !!!")
            print(f"Error type: {type(e).__name__}")
            print(f"Error message: {str(e)}")
            print("============================\n")

    def send_service_uart(self, enabled: bool):
        """Send service mode UART message"""
        if enabled != self.last_service_mode_state:
            s = f"21;{1 if enabled else 0}"
            self.send_string(s)
            self.last_service_mode_state = enabled

    def send_actuator_uart(self, flag: int, enabled: bool):
        """Send actuator control UART message"""
        if self.last_actuator_states[flag] != enabled:
            message = f"{flag};{1 if enabled else 0}"
            self.send_string(message)
            self.last_actuator_states[flag] = enabled

    def send_boiler_discharge_uart(self, discharge_value: int):
        """Send boiler discharge UART message"""
        s = f"17;{discharge_value}"
        self.send_string(s)

    def send_datetime_uart(self, year: int, month: int, day: int, hour: int, minute: int, second: int):
        """Send date and time UART message"""
        last_two_digits = year % 100
        s = f"19;{last_two_digits:02d};{month:02d};{day:02d};{hour:02d};{minute:02d};{second:02d}"
        self.send_string(s)

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
            "Voltage": 0.0
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
        
        # Service sensor values (separate from main sensor values)
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
        """Reset GH activation flag"""
        if gh_number == 1:
            self.HGP1ACTIVE = 0
            self.gh1_extraction_in_progress = False
            print(f"Deactivated HGP1ACTIVE after 3-second delay")
        elif gh_number == 2:
            self.HGP2ACTIVE = 0
            self.gh2_extraction_in_progress = False
            print(f"Deactivated HGP2ACTIVE after 3-second delay")

# Create global config instance
config = Config()

# Initialize all state variables at the top of the file
print("Initializing system status variables...")

# System status variables
mode_state = 0  # 0=off, 1=eco, 2=sleep
boiler_discharge = 0  # 0=nothing, 1=drain&refill, 2=drain&shutdown
barista_light = 0  # 0-100 percentage
cup_warmer = 0  # 0-100 percentage
discharge_timer = None

# اضافه کردن متغیر برای ذخیره آخرین وضعیت حالت سرویس
last_service_mode_state = False

# لیست ثابت خطاها (کد و توضیح)
ERROR_LIST = [
    {"row": i+1, "code": f"E{i:02d}", "description": desc}
    for i, desc in enumerate([
        "جریان اضافه مصرفی", # E00
        "افت جریان مصرفی", # E01
        "دبی آب اضافه", # E02
        "دبی آب کم", # E03
        "خطای الکتروموتور", # E04
        "خطای سنسور دما بویلر", # E05
        "خطای سنسور سطح آب بویلر", # E06
        "خطای المنت ۱ بویلر", # E07
        "خطای المنت ۲ بویلر", # E08
        "خطای المنت ۳ بویلر", # E09
        "خطای سوئیچ فشار بویلر", # E10
        "خطای سنسور فشار بالا بویلر", # E11
        "خطای شیر برقی بویلر", # E12
        "خطای شیر تخلیه بویلر", # E13
        "خطای زمان شارژ بویلر", # E14
        "خطای سنسور دما ورودی هدگروپ ۱", # E15
        "خطای سنسور سطح آب هدگروپ ۱", # E16
        "خطای سنسور دما خروجی هدگروپ ۱", # E17
        "خطای المنت هدگروپ ۱", # E18
        "خطای سوئیچ فشار هدگروپ ۱", # E19
        "خطای شیر برقی خروجی هدگروپ ۱", # E20
        "خطای زمان شارژ آب هدگروپ ۱", # E21
        "خطای سنسور دما ورودی هدگروپ ۲", # E22
        "خطای سنسور دما خروجی هدگروپ ۲", # E23
        "خطای سنسور سطح آب هدگروپ ۲", # E24
        "خطای المنت هدگروپ ۲", # E25
        "خطای شیر برقی ورودی هدگروپ ۲", # E26
        "خطای شیر برقی خروجی هدگروپ ۲", # E27
        "خطای زمان شارژ آب هدگروپ ۲", # E28
    ] + ["" for _ in range(29, 57)])
]

# لیست سراسری برای ذخیره خطاهای ثبت‌شده (فقط شماره خطا و زمان)
ERROR_HISTORY = []

# نگهداری آخرین وضعیت هر actuator
last_actuator_states = {i: False for i in range(22, 45)}

# Create UART communicator instance
uart = UARTCommunicator(port='/dev/ttyAMA0', baudrate=9600) 

class RequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Log all requests except frequent getdata requests
        if not ('GET /getdata' in (format % args)):
            logging.info("%s - %s", self.address_string(), format % args)
            print(f"\n{self.address_string()} - {format % args}\n")
        elif 'POST /setstatusupdate' in (format % args):
            # Always log setstatusupdate requests
            logging.info("%s - %s", self.address_string(), format % args)
            print(f"\n{self.address_string()} - {format % args}\n")
    
    def do_GET(self):
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
            
            # Get current UART data
            uart_data = uart.get_current_data()
            
            # Prepare response data
            data = config.sensors.copy()
            
            # Add UART data
            data.update({
                "MainTankTemp": uart_data['main_temperature'] / 10,  # Convert back to decimal
                "HeadGP1TopTemp": uart_data['gh1']['temperature'] / 10,
                "HeadGP2TopTemp": uart_data['gh2']['temperature'] / 10,
                "PressureGPH1": uart_data['gh1']['pressure'],
                "PressureGPH2": uart_data['gh2']['pressure'],
                "HeadGP1WaterFlow": uart_data['gh1']['flow'],
                "HeadGP2WaterFlow": uart_data['gh2']['flow']
            })
            
            # Add additional data
            data["MainTankWaterLevel"] = 100  # Fixed value since we don't have UART data for this
            data["HeadGP1WaterLevel"] = 100   # Fixed value since we don't have UART data for this
            data["HeadGP2WaterLevel"] = 100   # Fixed value since we don't have UART data for this
            data["Current"] = 10              # Fixed value since we don't have UART data for this
            data["Voltage"] = 230             # Fixed value since we don't have UART data for this
            
            # Use button states for activation flags
            data["GH1_ACTIVATION_FLAG"] = config.HGP1ACTIVE
            data["GH2_ACTIVATION_FLAG"] = config.HGP2ACTIVE
            data["HGP1ACTIVE"] = config.HGP1ACTIVE
            data["HGP2ACTIVE"] = config.HGP2ACTIVE
            data["mainTankState"] = config.mainTankState
            
            # Add current time from config
            data["current_time"] = config.current_time
            
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
            print("\nReceived GET request to /getgauge")
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            # Get the group head ID from query parameters
            query = parse_qs(self.path.split('?')[1] if '?' in self.path else '')
            gh_id = query.get('gh_id', ['1'])[0]
            
            # Get current UART data
            uart_data = uart.get_current_data()
            
            # Select the appropriate group head data
            gh_data = uart_data['gh1'] if gh_id == '1' else uart_data['gh2']
            
            gauge_data = {
                "pressure": {
                    "value": gh_data['pressure'],
                    "min": 0,
                    "max": 12,
                    "unit": "bar"
                },
                "temperature": {
                    "value": gh_data['temperature'] / 10,  # Convert back to decimal
                    "min": 0,
                    "max": 120,
                    "unit": "°C"
                },
                "flow": {
                    "value": gh_data['flow'],
                    "min": 0,
                    "max": 5,
                    "unit": "L/min"
                },
                "water_level": {
                    "value": 0.0,
                    "min": 0,
                    "max": 100,
                    "unit": "%"
                }
            }
            
            print(f"DEBUG: Sending gauge data for GH{gh_id}: {json.dumps(gauge_data, indent=2)}")
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
            
        elif self.path == '/getpressureconfig':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            pressure_config = config.pressureConfig.copy()
            
            self.wfile.write(json.dumps(pressure_config).encode())
            
        elif self.path == '/geterrors':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(ERROR_HISTORY).encode())
            return

        elif self.path == '/getservicedata':
            logging.info("Received request for service sensor data")
            print("\n=== Received request for service sensor data ===")
            print("Current service sensor values:")
            for key, value in config.service_sensors.items():
                print(f"{key}: {value}")
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            response_data = json.dumps(config.service_sensors)
            logging.info(f"Sending service sensor data: {response_data}")
            print(f"\nSending response: {response_data}")
            
            self.wfile.write(response_data.encode())
            return

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
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8')
            params = json.loads(post_data)
            
            if self.path == '/setstatusupdate':
                print("\nReceived button state update request")
                print("Request data:", json.dumps(params, indent=2))
                target = params.get('target')
                status = params.get('status')
                
                print("\nCurrent states:")
                print(f"- Main boiler button: {config.mainTankState}")
                print(f"- GH1 button: {config.HGP1ACTIVE}")
                print(f"- GH2 button: {config.HGP2ACTIVE}")
                
                # Update button states
                if target == 'main_boiler':
                    new_state = 1 if status else 0
                    if new_state != config.mainTankState:
                        print(f"\nUpdating main boiler button state:")
                        print(f"Old state: {config.mainTankState}")
                        print(f"New state: {new_state}")
                        config.mainTankState = new_state
                elif target == 'gh1':
                    new_state = 1 if status else 0
                    if new_state != config.HGP1ACTIVE:
                        print(f"\nUpdating GH1 button state:")
                        print(f"Old state: {config.HGP1ACTIVE}")
                        print(f"New state: {new_state}")
                        config.HGP1ACTIVE = new_state
                elif target == 'gh2':
                    new_state = 1 if status else 0
                    if new_state != config.HGP2ACTIVE:
                        print(f"\nUpdating GH2 button state:")
                        print(f"Old state: {config.HGP2ACTIVE}")
                        print(f"New state: {new_state}")
                        config.HGP2ACTIVE = new_state
                
                # Send UART message for button state changes
                print("\nSending flag 3 UART message...")
                uart.send_main_status(
                    config.mainTankState,
                    config.HGP1ACTIVE,
                    config.HGP2ACTIVE,
                    int(round(config.pressureConfig['pressure'])),
                    int(round(config.mainAmpereConfig['temperature']))
                )
                
                # Send success response
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success"}).encode())
                return

            elif self.path == '/setactuator':
                try:
                    data = json.loads(post_data)
                    logging.info(f"Received actuator data: {data}")
                    print(f"\nReceived actuator data: {data}")
                    
                    flag = data.get('flag')
                    enabled = data.get('enabled')
                    
                    if flag is None or enabled is None:
                        logging.error("Missing required parameters")
                        print("\nMissing required parameters")
                        self.send_error(400, "Missing required parameters")
                        return
                        
                    if not isinstance(flag, int) or not isinstance(enabled, bool):
                        logging.error("Invalid parameter types")
                        print("\nInvalid parameter types")
                        self.send_error(400, "Invalid parameter types")
                        return
                        
                    if flag < 22 or flag > 44:
                        logging.error(f"Invalid actuator flag: {flag}")
                        print(f"\nInvalid actuator flag: {flag}")
                        self.send_error(400, "Invalid actuator flag")
                        return
                    
                    logging.info(f"Calling send_actuator with flag={flag}, enabled={enabled}")
                    print(f"\nCalling send_actuator with flag={flag}, enabled={enabled}")
                    
                    uart.send_actuator(flag, enabled)
                    
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': True}).encode())
                    
                    logging.info("Actuator request handled successfully")
                    print("\nActuator request handled successfully")
                    
                except Exception as e:
                    logging.error(f"Error handling actuator request: {str(e)}")
                    print(f"\nError handling actuator request: {str(e)}")
                    self.send_error(500, str(e))
                    return

            elif self.path == '/setpressureconfig':
                try:
                    print("\n=== Processing Pressure Config Update ===")
                    print(f"Config: {json.dumps(params.get('config', {}), indent=2)}")
                    new_config = params.get('config', {})
                    old_pressure = config.pressureConfig['pressure']
                    
                    # به‌روزرسانی تنظیمات فشار با مقادیر پیش‌فرض در صورت عدم وجود
                    config.pressureConfig.update({
                        "pressure": float(new_config.get('pressure', config.pressureConfig['pressure'])),
                        "max_pressure": float(new_config.get('max_pressure', config.pressureConfig.get('max_pressure', 120.0))),
                        "min_pressure": float(new_config.get('min_pressure', config.pressureConfig.get('min_pressure', 0.0)))
                    })
                    
                    print("\nUpdated Pressure Configuration:")
                    print("--------------------------------")
                    print(json.dumps(config.pressureConfig, indent=2))
                    print("--------------------------------\n")
                    
                    print(f"\nDebug - Pressure Config Update:")
                    print(f"Old pressure: {old_pressure}")
                    print(f"New pressure: {config.pressureConfig['pressure']}")
                    
                    # همیشه فلگ 3 را ارسال کن
                    print("\nSending flag 3 UART message due to pressure config change...")
                    uart.send_main_status(
                        config.mainTankState,
                        config.HGP1ACTIVE,
                        config.HGP2ACTIVE,
                        int(round(config.pressureConfig['pressure'])),
                        int(round(config.mainAmpereConfig['temperature']))
                    )
                    
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': True}).encode())
                    return
                except Exception as e:
                    print(f"\nError updating pressure config: {str(e)}")
                    logging.error(f"Error updating pressure config: {str(e)}")
                    self.send_error(500, str(e))
                    return

            elif self.path == '/setboilerdischarge':
                print("\n=== Processing Boiler Discharge Update ===")
                discharge_map = {'none': 0, 'drain_refill': 1, 'drain_shutdown': 2}
                discharge_value = params.get('discharge', 'none')
                discharge_flag_value = discharge_map.get(discharge_value, 0)
                print(f"Received discharge: {discharge_value} (flag value: {discharge_flag_value})")
                uart.send_boiler_discharge(discharge_flag_value)
                print(f"=== Boiler Discharge (Flag 17) Sent ===\n")
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
                return

            elif self.path == '/savemainconfig':
                print("\n=== Processing Main Config Save (Mode, Eco, etc.) ===")
                print(f"Config: {json.dumps(params.get('config', {}), indent=2)}")
                new_config = params.get('config', {})
                # Only update and send flag 4 if eco_mode, barista_light, or cup_warmer are present
                eco_mode = new_config.get('eco_mode')
                barista_light_val = new_config.get('barista_light')
                cup_warmer_val = new_config.get('cup_warmer')
                sleep_time = new_config.get('sleep_time')
                print(f"Sleep time data: {sleep_time}")
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
                    month = sleep_time.get('month') if sleep_time else None
                    day = sleep_time.get('day') if sleep_time else None
                    hour = sleep_time.get('hour') if sleep_time else None
                    minute = sleep_time.get('minute') if sleep_time else None
                    print(f"Extracted time values - Month: {month}, Day: {day}, Hour: {hour}, Minute: {minute}")
                    uart.send_system_status(mode_val, light_val, cup_val, month, day, hour, minute)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
                return

            elif self.path == '/setmainconfig':
                print("\n=== Processing Main Config Update ===")
                print(f"Config: {json.dumps(params.get('config', {}), indent=2)}")
                new_config = params.get('config', {})
                old_temp = config.mainAmpereConfig['temperature']
                config.mainAmpereConfig.update({
                    "temperature": float(new_config.get('temperature', config.mainAmpereConfig['temperature']))
                })
                
                print("\nUpdated Main Configuration:")
                print("--------------------------------")
                print(json.dumps({
                    "temperature": config.mainAmpereConfig['temperature']
                }, indent=2))
                print("--------------------------------\n")
                
                print(f"\nDebug - Main Config Update:")
                print(f"Old temperature: {old_temp}")
                print(f"New temperature: {config.mainAmpereConfig['temperature']}")
                
                # Send UART message for config change
                print("Sending UART message due to config change...")
                uart.send_main_status(
                    config.mainTankState,
                    config.HGP1ACTIVE,
                    config.HGP2ACTIVE,
                    int(round(config.pressureConfig['pressure'])),
                    int(round(config.mainAmpereConfig['temperature']))
                )
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
                return

            elif self.path == '/updatepreinfusion':
                print("\n=== Processing Pre-Infusion Update ===")
                gh_id = params.get('gh_id', 'ghundefined')
                preinf_data = params.get('pre_infusion', {})
                
                if gh_id == 'gh1':
                    config.gh1_config['pre_infusion'] = preinf_data
                    # Send only pre-infusion flag (15)
                    preinf_value = int(preinf_data.get('time', 0)) if preinf_data.get('enabled', False) else 0
                    uart.send_preinfusion(1, preinf_value)
                elif gh_id == 'gh2':
                    config.gh2_config['pre_infusion'] = preinf_data
                    # Send only pre-infusion flag (16)
                    preinf_value = int(preinf_data.get('time', 0)) if preinf_data.get('enabled', False) else 0
                    uart.send_preinfusion(2, preinf_value)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
                return

            elif self.path == '/updatebackflush':
                print("\n=== Processing Backflush Update ===")
                gh_id = params.get('gh_id', 'ghundefined')
                backflush_enabled = params.get('enabled', False)
                
                if gh_id == 'gh1':
                    config.gh1_config['backflush'] = backflush_enabled
                    # Send only backflush flag (11)
                    uart.send_backflush(1, backflush_enabled)
                elif gh_id == 'gh2':
                    config.gh2_config['backflush'] = backflush_enabled
                    # Send only backflush flag (12)
                    uart.send_backflush(2, backflush_enabled)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
                return

            elif self.path == '/saveghconfig':
                print("\nReceived POST request to /saveghconfig")
                print("Request data:", json.dumps(params, indent=2))
                new_config = params.get('config', {})
                gh_id = params.get('gh_id', 'ghundefined')
                
                print(f"\n=== SAVING CONFIG FOR {gh_id} ===")
                print(f"DEBUG: Processing saveghconfig with gh_id={gh_id}")
                
                # Fix gh_id if it's undefined
                if gh_id == 'ghundefined':
                    query = parse_qs(self.path.split('?')[1] if '?' in self.path else '')
                    amper_id = query.get('amperId', ['1'])[0]
                    gh_id = f'gh{amper_id}'
                    print(f"DEBUG: Fixed gh_id to {gh_id}")
                
                # Keep existing pre-infusion and backflush data for config saves
                preinf = config.gh1_config['pre_infusion'] if gh_id == 'gh1' else config.gh2_config['pre_infusion']
                backflush = config.gh1_config['backflush'] if gh_id == 'gh1' else config.gh2_config['backflush']
                print("\nUsing existing pre-infusion data:", preinf)
                print("Using existing backflush data:", backflush)
                
                if gh_id == 'gh1':
                    print("\n=== UPDATING GH1 CONFIG ===")
                    # Handle null volume by using existing value
                    volume = new_config.get('volume')
                    if volume is None:
                        volume = config.gh1_config['extraction_volume']
                        print(f"Using existing volume value: {volume}")
                    
                    config.gh1_config.update({
                        "temperature": float(new_config.get('temperature', config.gh1_config['temperature'])),
                        "extraction_volume": int(volume),
                        "extraction_time": int(new_config.get('extraction_time', config.gh1_config['extraction_time'])),
                        "pre_infusion": preinf,
                        "purge": int(new_config.get('purge', config.gh1_config['purge'])),
                        "backflush": backflush
                    })
                    print("\n=== SENDING GH1 UART MESSAGE ===")
                    print("Sending main config only (flag 1) - no pre-infusion or backflush")
                    # Send only main config UART (flag 1) without pre-infusion or backflush
                    uart.send_gh_config(1, config.gh1_config)
                    print("=== GH1 CONFIG UPDATE COMPLETE ===\n")
                
                elif gh_id == 'gh2':
                    print("\n=== UPDATING GH2 CONFIG ===")
                    # Handle null volume by using existing value
                    volume = new_config.get('volume')
                    if volume is None:
                        volume = config.gh2_config['extraction_volume']
                        print(f"Using existing volume value: {volume}")
                    
                    config.gh2_config.update({
                        "temperature": float(new_config.get('temperature', config.gh2_config['temperature'])),
                        "extraction_volume": int(volume),
                        "extraction_time": int(new_config.get('extraction_time', config.gh2_config['extraction_time'])),
                        "pre_infusion": preinf,
                        "purge": int(new_config.get('purge', config.gh2_config['purge'])),
                        "backflush": backflush
                    })
                    print("\n=== SENDING GH2 UART MESSAGE ===")
                    print("Sending main config only (flag 2) - no pre-infusion or backflush")
                    # Send only main config UART (flag 2) without pre-infusion or backflush
                    uart.send_gh_config(2, config.gh2_config)
                    print("=== GH2 CONFIG UPDATE COMPLETE ===\n")

                print("\nUpdated Group Head Configurations:")
                print("--------------------------------")
                print("Group Head 1:")
                print(json.dumps({
                    "temperature": config.gh1_config['temperature'],
                    "pre_infusion": config.gh1_config['pre_infusion'],
                    "extraction_time": config.gh1_config['extraction_time'],
                    "volume": config.gh1_config['extraction_volume'],
                    "purge": config.gh1_config['purge'],
                    "backflush": config.gh1_config['backflush']
                }, indent=2))
                print("\nGroup Head 2:")
                print(json.dumps({
                    "temperature": config.gh2_config['temperature'],
                    "pre_infusion": config.gh2_config['pre_infusion'],
                    "extraction_time": config.gh2_config['extraction_time'],
                    "volume": config.gh2_config['extraction_volume'],
                    "purge": config.gh2_config['purge'],
                    "backflush": config.gh2_config['backflush']
                }, indent=2))
                print("--------------------------------\n")

            elif self.path == '/setsystemstatus':
                print("\n=== Processing System Status Update ===")
                print(f"Received data: {json.dumps(params, indent=2)}")
                
                # پردازش پارامترهای وضعیت سیستم
                eco_mode = params.get('eco_mode')
                barista_light_val = params.get('barista_light')
                cup_warmer_val = params.get('cup_warmer')
                sleep_time = params.get('sleep_time', {})  # دریافت زمان خواب
                
                # تبدیل مقادیر به اعداد صحیح
                mode_val = None
                if eco_mode is not None:
                    if isinstance(eco_mode, dict):
                        mode_val = 1 if eco_mode.get('enabled', False) else 0
                    else:
                        mode_val = int(eco_mode)
                
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
                
                # پردازش زمان خواب
                month_val = None
                day_val = None
                hour_val = None
                minute_val = None
                if sleep_time:
                    month_val = int(sleep_time.get('month', 1))
                    day_val = int(sleep_time.get('day', 1))
                    hour_val = int(sleep_time.get('hour', 0))
                    minute_val = int(sleep_time.get('minute', 0))
                
                if eco_mode is not None or barista_light_val is not None or cup_warmer_val is not None or sleep_time:
                    uart.send_system_status(
                        mode_val,
                        light_val,
                        cup_val,
                        month_val,
                        day_val,
                        hour_val,
                        minute_val
                    )
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
                return

            elif self.path == '/setdatetime':
                print("\n=== Processing Date & Time Update (Flag 19) ===")
                print(f"Received date/time: {json.dumps(params, indent=2)}")
                year = int(params.get('year', 0))
                month = int(params.get('month', 0))
                day = int(params.get('day', 0))
                hour = int(params.get('hour', 0))
                minute = int(params.get('minute', 0))
                second = int(params.get('second', 0))
                uart.send_datetime(year, month, day, hour, minute, second)
                print(f"=== Date & Time UART (Flag 19) Sent ===\n")
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
                return

            elif self.path == '/clearerrors':
                ERROR_HISTORY.clear()
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
                return

            elif self.path == '/setservicemode':
                print("\n=== Processing Service Mode Update ===")
                print(f"Request data: {json.dumps(params, indent=2)}")
                enabled = params.get('enabled', False)
                uart.send_service_mode(enabled)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
                return

            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
            self.wfile.write(b'POST request received!')
            
        except Exception as e:
            logging.error(f"Error in do_POST: {str(e)}")
            print(f"\nError in do_POST: {str(e)}")
            self.send_error(500, str(e))
            return

def run_server(port=8000):
    """Run the HTTP server with UART communication"""
    try:
        # Initialize UART
        uart = UARTCommunicator(port='/dev/ttyAMA0', baudrate=9600)
        uart.start()
        
        # Create server
        server_address = ('', port)
        httpd = HTTPServer(server_address, RequestHandler)
        
        # Set UART instance in RequestHandler
        RequestHandler.uart = uart
        
        print(f'Starting server on port {port}...')
        print(f'UART communication initialized on /dev/ttyAMA0')
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")
            uart.stop()
            httpd.server_close()
            
    except Exception as e:
        print(f"Error starting server: {str(e)}")
        logging.error(f"Error starting server: {str(e)}")
        if 'uart' in locals():
            uart.stop()
        sys.exit(1)

if __name__ == '__main__':
    run_server() 
