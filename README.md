import json
import logging
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
import threading
import time
import random
from urllib.parse import parse_qs
from datetime import datetime
import serial  # اضافه کردن کتابخانه pyserial

# Global state variables
main_boiler_state = 0
gh1_button_state = 0
gh2_button_state = 0
gh1_uart_active = False
gh2_uart_active = False
last_main_data = None
last_gh1_data = None
last_gh2_data = None

# Configure logging to print to both file and console
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',  # Remove timestamp and level
    handlers=[
        logging.FileHandler('test_backend.log', mode='w'),  # Clear file on start
        logging.StreamHandler(sys.stdout)  # Print to console
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
        self.start()

    def start(self):
        """Initialize and open the UART port"""
        try:
            print(f"\n=== Initializing UART on {self.port} ===")
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )
            if not self.serial.is_open:
                self.serial.open()
            print(f"UART port {self.port} opened successfully")
            # Send a test message to verify communication
            self.send_string("0;0")  # Send a simple test message
            print("Test message sent to verify UART communication")
        except Exception as e:
            print(f"Error opening UART port: {str(e)}")
            logging.error(f"Error opening UART port: {str(e)}")
            raise

    def send_string(self, message: str):
        """Send a string message over UART"""
        try:
            if not self.serial or not self.serial.is_open:
                print("UART port not open, attempting to reopen...")
                self.start()
            
            # Add newline character to the message
            message = message + '\n'
            
            # Print the message being sent
            print("\n" + "="*80)
            print("UART MESSAGE SENT:")
            print("-"*80)
            print(f"FLAG: {message.split(';')[0]}")
            print(f"DATA: {message.strip()}")
            print("-"*80)
            print("="*80 + "\n")
            
            # Send the message
            bytes_written = self.serial.write(message.encode())
            self.serial.flush()  # Ensure all data is sent
            
            # Log the message
            logging.info(f"UART MESSAGE: {message.strip()}")
            print(f"Bytes written: {bytes_written}")
            
            # Small delay to ensure message is sent
            time.sleep(0.1)
            
        except Exception as e:
            print(f"Error sending UART message: {str(e)}")
            logging.error(f"Error sending UART message: {str(e)}")
            # Try to reopen the port
            try:
                self.start()
            except:
                print("Failed to reopen UART port")

    def read_line(self):
        """Read a line from UART"""
        try:
            if not self.serial or not self.serial.is_open:
                print("UART port not open, attempting to reopen...")
                self.start()
            
            if self.serial.in_waiting:
                line = self.serial.readline().decode().strip()
                if line:
                    print(f"\nReceived UART message: {line}")
                    logging.info(f"UART RECEIVED: {line}")
                return line
        except Exception as e:
            print(f"Error reading from UART: {str(e)}")
            logging.error(f"Error reading from UART: {str(e)}")
        return None

    def close(self):
        """Close the UART port"""
        if self.serial and self.serial.is_open:
            self.serial.close()
            print("UART port closed")

# Create UART communicator instance
uart = UARTCommunicator()

# Replace simulate_uart_send with uart.send_string
def simulate_uart_send(s: str):
    """Send UART message using the real UART port"""
    uart.send_string(s)

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
        
        print("Test Configuration initialized")

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

def send_gh_uart(flag, cfg, send_preinfusion=False, send_backflush=False):
    """Simulate sending group head configuration"""
    print(f"\nSending GH{flag} UART message...")
    # Get all values, using most recent ones
    temp = int(round(cfg['temperature'] * 10))  # Multiply by 10 as requested
    ext_vol = int(round(cfg['extraction_volume']))
    ext_time = int(round(cfg['extraction_time']))
    purge = int(round(cfg.get('purge', 0)))
    
    # Send main configuration only (flag 1 or 2)
    # Format: flag;temp;ext_vol;ext_time;purge
    s = f"{flag};{temp};{ext_vol};{ext_time};{purge}"
    print(f"GH{flag} main config - Temp: {temp/10}°C, Volume: {ext_vol}, Time: {ext_time}s, Purge: {purge}")
    simulate_uart_send(s)

    # Only send pre-infusion if explicitly requested (from pre-infusion modal)
    if send_preinfusion:
        preinf_data = cfg.get('pre_infusion', {})
        if isinstance(preinf_data, dict):
            preinf_value = int(round(preinf_data.get('time', 0))) if preinf_data.get('enabled', False) else 0
        else:
            preinf_value = int(round(preinf_data)) if preinf_data > 0 else 0
        preinf_flag = 15 if flag == 1 else 16
        preinf_s = f"{preinf_flag};{preinf_value}"
        print(f"Sending pre-infusion config for GH{flag}: {preinf_value}s")
        simulate_uart_send(preinf_s)

    # Only send backflush if explicitly requested (from backflush modal)
    if send_backflush:
        backflush_flag = 11 if flag == 1 else 12
        backflush_value = 1 if cfg.get('backflush', False) else 0
        backflush_s = f"{backflush_flag};{backflush_value}"
        print(f"Sending backflush status for GH{flag}: {backflush_value}")
        simulate_uart_send(backflush_s)

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

def send_test_config_uart():
    """Send UART message for test config activation"""
    print("\nSending test config UART messages...")
    # Send UART messages for test config activation
    if gh1_uart_active:
        s = f"13;{gh1_uart_active}"
        print(f"Activating GH1 test config (UART state: {gh1_uart_active})")
        simulate_uart_send(s)
        # Update HGP1ACTIVE only when UART message is sent
        config.HGP1ACTIVE = gh1_uart_active
    if gh2_uart_active:
        s = f"14;{gh2_uart_active}"
        print(f"Activating GH2 test config (UART state: {gh2_uart_active})")
        simulate_uart_send(s)
        # Update HGP2ACTIVE only when UART message is sent
        config.HGP2ACTIVE = gh2_uart_active

def send_system_status_uart(mode=None, light=None, cup=None, month=None, day=None, hour=None, minute=None):
    """Send system status UART message with flag 4 (NO discharge)"""
    global mode_state, barista_light, cup_warmer
    
    # استفاده از مقادیر پیش‌فرض اگر پارامترها ارائه نشده باشند
    mode = mode if mode is not None else mode_state
    light = light if light is not None else barista_light
    cup = cup if cup is not None else cup_warmer
    month = month if month is not None else 1
    day = day if day is not None else 1
    hour = hour if hour is not None else 0
    minute = minute if minute is not None else 0
    
    print("\nSending system status UART message...")
    print(f"Values - Mode: {mode}, Light: {light}, Cup: {cup}")
    print(f"Time - {month}/{day} {hour}:{minute}")
    
    s = f"4;{mode};{light};{cup};{month};{day};{hour};{minute}"
    simulate_uart_send(s)

def reset_boiler_discharge():
    """Reset boiler discharge state after 2 seconds"""
    global boiler_discharge, discharge_timer
    print("\n=== RESETTING BOILER DISCHARGE ===")
    print(f"Resetting from {boiler_discharge} to 0")
    boiler_discharge = 0
    discharge_timer = None
    send_system_status_uart()  # Send update after reset
    print("================================\n")

def update_system_status(mode=None, light=None, cup=None, month=None, day=None, hour=None, minute=None):
    """Update system status and send UART message if any value changes"""
    global mode_state, boiler_discharge, barista_light, cup_warmer
    print("\nUpdating system status...")
    print(f"Current values - mode: {mode_state}, light: {barista_light}, cup: {cup_warmer}")
    print(f"New values - mode: {mode}, light: {light}, cup: {cup}, time: {month}/{day} {hour}:{minute}")
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
    if changed or (month is not None and day is not None and hour is not None and minute is not None):
        print("Values changed, sending system status update")
        send_system_status_uart(mode=mode, light=light, cup=cup, month=month, day=day, hour=hour, minute=minute)
    else:
        print("No values changed, skipping UART update")

def send_service_uart(enabled: bool):
    """Send UART message for service mode (flag 21)"""
    global last_service_mode_state
    
    # فقط در صورت تغییر وضعیت، پیام را ارسال کن
    if enabled != last_service_mode_state:
        print("\n" + "="*80)
        print("SERVICE MODE UART MESSAGE:")
        print("-"*80)
        print(f"Service mode: {'ENABLED' if enabled else 'DISABLED'}")
        s = f"21;{1 if enabled else 0}"
        print(f"FLAG: 21")
        print(f"DATA: {s}")
        print("-"*80)
        print("="*80 + "\n")
        
        # Log to file and force flush
        logging.info(f"SERVICE MODE UART: {s}")
        sys.stdout.flush()
        sys.stderr.flush()
        
        # به‌روزرسانی آخرین وضعیت
        last_service_mode_state = enabled
    else:
        print(f"\nService mode unchanged ({'enabled' if enabled else 'disabled'}), skipping UART message")

def send_actuator_uart(flag: int, enabled: bool):
    """
    ارسال پیام UART برای کنترل actuator ها
    flag: شماره فلگ actuator (22 تا 44)
    enabled: وضعیت فعال/غیرفعال
    """
    global last_actuator_states
    
    # بررسی تغییر وضعیت
    if last_actuator_states[flag] == enabled:
        print(f"\nActuator {flag} status unchanged ({'ENABLED' if enabled else 'DISABLED'}), skipping UART message")
        return
        
    # به‌روزرسانی وضعیت
    last_actuator_states[flag] = enabled
    
    # ساخت و ارسال پیام UART
    message = f"{flag};{1 if enabled else 0}"
    print("\n" + "="*80)
    print(f"ACTUATOR UART MESSAGE:")
    print("-"*80)
    print(f"Actuator flag: {flag}")
    print(f"Status: {'ENABLED' if enabled else 'DISABLED'}")
    print(f"UART Message: {message}")
    print("-"*80)
    print("="*80 + "\n")
    
    # ارسال پیام UART
    simulate_uart_send(message)
    
    # لاگ کردن
    logging.info(f"Actuator {flag} {'enabled' if enabled else 'disabled'}")
    logging.info(f"UART message sent: {message}")

def handle_uart_message(flag: int, values: list):
    global last_gh1_start, last_gh2_start, config
    print(f"\n=== UART Message Received ===")
    print(f"Flag: {flag}")
    print(f"Values: {values}")
    
    try:
        if flag == 50:  # Update system time
            print(f"\nReceived time update (flag 50) with values: {values}")
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
                print(f"Updated system time to: {year}/{month}/{day} {hour}:{minute}:{second}")
        elif flag == 46:  # Service sensors - part 1
            print("\nProcessing flag 46 - Service sensors part 1")
            print("Before update:")
            for key, value in config.service_sensors.items():
                if key in ["voltage", "current", "main_flow", "group1_flow", "group2_flow", "main_tank_temp", "group1_upper_temp"]:
                    print(f"{key}: {value}")
            
            config.service_sensors["voltage"] = values[0] / 10
            config.service_sensors["current"] = values[1] / 10
            config.service_sensors["main_flow"] = values[2] / 10
            config.service_sensors["group1_flow"] = values[3] / 10
            config.service_sensors["group2_flow"] = values[4] / 10
            config.service_sensors["main_tank_temp"] = values[5] / 10
            config.service_sensors["group1_upper_temp"] = values[6] / 10
            
            print("\nAfter update:")
            for key, value in config.service_sensors.items():
                if key in ["voltage", "current", "main_flow", "group1_flow", "group2_flow", "main_tank_temp", "group1_upper_temp"]:
                    print(f"{key}: {value}")
            return

        elif flag == 47:  # Service sensors - part 2
            print("\nProcessing flag 47 - Service sensors part 2")
            print("Before update:")
            for key, value in config.service_sensors.items():
                if key in ["group1_lower_temp", "group2_upper_temp", "group2_lower_temp", "pressure"]:
                    print(f"{key}: {value}")
            
            config.service_sensors["group1_lower_temp"] = values[0] / 10
            config.service_sensors["group2_upper_temp"] = values[1] / 10
            config.service_sensors["group2_lower_temp"] = values[2] / 10
            config.service_sensors["pressure"] = values[3] / 10
            
            print("\nAfter update:")
            for key, value in config.service_sensors.items():
                if key in ["group1_lower_temp", "group2_upper_temp", "group2_lower_temp", "pressure"]:
                    print(f"{key}: {value}")
            return

        elif flag == 48:  # Service sensors - tank levels
            print("\nProcessing flag 48 - Service tank levels")
            print("Before update:")
            for key, value in config.service_sensors.items():
                if key in ["steam_tank_level", "group1_tank_level", "group2_tank_level"]:
                    print(f"{key}: {value}")
            
            config.service_sensors["steam_tank_level"] = values[0]
            config.service_sensors["group1_tank_level"] = values[1]
            config.service_sensors["group2_tank_level"] = values[2]
            
            print("\nAfter update:")
            for key, value in config.service_sensors.items():
                if key in ["steam_tank_level", "group1_tank_level", "group2_tank_level"]:
                    print(f"{key}: {value}")
            return

        # Handle other flags
        if flag == 8:  # Main boiler temperature
            temp_value = values[0] / 10
            config.sensors["MainTankTemp"] = temp_value
            config.uart_data['main_boiler_temp'] = values[0]  # ذخیره در uart_data هم
            print(f"\nUpdated main boiler temperature:")
            print(f"New value: {temp_value}°C")
            print(f"Raw UART value: {values[0]}")
            print(f"Stored in sensors: {config.sensors['MainTankTemp']}")
            print(f"Stored in uart_data: {config.uart_data['main_boiler_temp']}")
        elif flag == 1:  # GH1 config
            temp_value = values[0] / 10
            config.gh1_config.update({
                "temperature": temp_value,
                "extraction_volume": values[1],
                "extraction_time": values[2],
                "purge": values[3]
            })
            config.uart_data['gh1'].update({
                "temperature": values[0],  # ذخیره مقدار خام
                "pressure": values[1] / 10,  # تبدیل به بار
                "flow": values[2]  # مقدار جریان
            })
            print(f"\nUpdated GH1 configuration:")
            print(f"Temperature: {temp_value}°C")
            print(f"Extraction volume: {values[1]}")
            print(f"Extraction time: {values[2]}s")
            print(f"Purge: {values[3]}")
            print(f"Stored in gh1_config: {config.gh1_config}")
            print(f"Stored in uart_data: {config.uart_data['gh1']}")
        elif flag == 2:  # GH2 config
            temp_value = values[0] / 10
            config.gh2_config.update({
                "temperature": temp_value,
                "extraction_volume": values[1],
                "extraction_time": values[2],
                "purge": values[3]
            })
            config.uart_data['gh2'].update({
                "temperature": values[0],  # ذخیره مقدار خام
                "pressure": values[1] / 10,  # تبدیل به بار
                "flow": values[2]  # مقدار جریان
            })
            print(f"\nUpdated GH2 configuration:")
            print(f"Temperature: {temp_value}°C")
            print(f"Extraction volume: {values[1]}")
            print(f"Extraction time: {values[2]}s")
            print(f"Purge: {values[3]}")
            print(f"Stored in gh2_config: {config.gh2_config}")
            print(f"Stored in uart_data: {config.uart_data['gh2']}")
        elif flag == 9:  # GH1 status
            config.sensors["HeadGP1TopTemp"] = values[0] / 10
            config.Pressure1 = values[1] / 10
            config.FLOWGPH1CGF = values[2]
            # به‌روزرسانی uart_data برای API
            config.uart_data['gh1'].update({
                "temperature": values[0],  # ذخیره مقدار خام
                "pressure": values[1] / 10,  # تبدیل به بار
                "flow": values[2]  # مقدار جریان
            })
            print(f"\nUpdated GH1 status:")
            print(f"Temperature: {values[0]/10}°C")
            print(f"Pressure: {values[1]/10} bar")
            print(f"Flow: {values[2]}")
            print(f"Stored in uart_data: {config.uart_data['gh1']}")
        elif flag == 10:  # GH2 status
            config.sensors["HeadGP2TopTemp"] = values[0] / 10
            config.Pressure2 = values[1] / 10
            config.FLOWGPH2CGF = values[2]
            # به‌روزرسانی uart_data برای API
            config.uart_data['gh2'].update({
                "temperature": values[0],  # ذخیره مقدار خام
                "pressure": values[1] / 10,  # تبدیل به بار
                "flow": values[2]  # مقدار جریان
            })
            print(f"\nUpdated GH2 status:")
            print(f"Temperature: {values[0]/10}°C")
            print(f"Pressure: {values[1]/10} bar")
            print(f"Flow: {values[2]}")
            print(f"Stored in uart_data: {config.uart_data['gh2']}")
        elif flag == 13:  # GH1 extraction start/stop
            now = time.time()
            print(f"Received flag 13 with values: {values} at {now}")
            if int(values[0]) == 1:
                if not config.gh1_extraction_in_progress:
                    print("Starting GH1 extraction")
                    config.HGP1ACTIVE = 1
                    config.gh1_extraction_in_progress = True
                    last_gh1_start = now
                else:
                    print("GH1 extraction already in progress, ignoring repeated start")
            elif int(values[0]) == 0:
                print("Received GH1 extraction stop (13;0), setting HGP1ACTIVE=0")
                config.HGP1ACTIVE = 0
                config.gh1_extraction_in_progress = False
        elif flag == 14:  # GH2 extraction start/stop
            now = time.time()
            print(f"Received flag 14 with values: {values} at {now}")
            if int(values[0]) == 1:
                if not config.gh2_extraction_in_progress:
                    print("Starting GH2 extraction")
                    config.HGP2ACTIVE = 1
                    config.gh2_extraction_in_progress = True
                    last_gh2_start = now
                else:
                    print("GH2 extraction already in progress, ignoring repeated start")
            elif int(values[0]) == 0:
                print("Received GH2 extraction stop (14;0), setting HGP2ACTIVE=0")
                config.HGP2ACTIVE = 0
                config.gh2_extraction_in_progress = False
    except Exception as e:
        print(f"Error handling UART message: {str(e)}")
        logging.error(f"Error handling UART message: {str(e)}")

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
            
            # Simulate sensor data
            data = config.sensors.copy()
            
            # Add UART data
            data.update({
                "MainTankTemp": config.uart_data['main_boiler_temp'] / 10,  # Convert back to decimal
                "HeadGP1TopTemp": config.uart_data['gh1']['temperature'] / 10,
                "HeadGP2TopTemp": config.uart_data['gh2']['temperature'] / 10,
                "PressureGPH1": config.uart_data['gh1']['pressure'],
                "PressureGPH2": config.uart_data['gh2']['pressure'],
                "HeadGP1WaterFlow": config.uart_data['gh1']['flow'],
                "HeadGP2WaterFlow": config.uart_data['gh2']['flow']
            })
            
            # Add additional data
            data["MainTankWaterLevel"] = 100  # Fixed value since we don't have UART data for this
            data["HeadGP1WaterLevel"] = 100   # Fixed value since we don't have UART data for this
            data["HeadGP2WaterLevel"] = 100   # Fixed value since we don't have UART data for this
            data["Current"] = 10              # Fixed value since we don't have UART data for this
            data["Voltage"] = 230             # Fixed value since we don't have UART data for this
            # Use button states for activation flags
            data["GH1_ACTIVATION_FLAG"] = gh1_button_state
            data["GH2_ACTIVATION_FLAG"] = gh2_button_state
            # Use UART activation states for HGP1ACTIVE/HGP2ACTIVE
            data["HGP1ACTIVE"] = config.HGP1ACTIVE
            data["HGP2ACTIVE"] = config.HGP2ACTIVE
            data["mainTankState"] = main_boiler_state  # استفاده از main_boiler_state به جای config.mainTankState
            
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
            print(f"DEBUG: Current uart_data state: {json.dumps(config.uart_data, indent=2)}")
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            # Get the group head ID from query parameters
            query = parse_qs(self.path.split('?')[1] if '?' in self.path else '')
            gh_id = query.get('gh_id', ['1'])[0]
            
            # Select the appropriate group head data
            gh_data = config.uart_data['gh1'] if gh_id == '1' else config.uart_data['gh2']
            
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
        global main_boiler_state, gh1_button_state, gh2_button_state, gh1_uart_active, gh2_uart_active, last_main_data, last_gh1_data, last_gh2_data
        
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8')
            params = json.loads(post_data)
            
            if self.path == '/simulate_uart':
                print("\n=== Processing Simulated UART Message ===")
                message = params.get('message', '')
                print(f"Received UART message: {message}")
                
                try:
                    # Parse the message
                    parts = message.split(';')
                    if len(parts) < 2:
                        raise ValueError("Invalid message format")
                        
                    flag = int(parts[0])
                    values = [float(x) if '.' in x else int(x) for x in parts[1:]]
                    
                    # Process the message using handle_uart_message
                    handle_uart_message(flag, values)
                    
                    print("UART message processed successfully")
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': True}).encode())
                    return
                except Exception as e:
                    print(f"Error processing UART message: {e}")
                    self.send_error(400, str(e))
                    return
                    
            elif self.path == '/setstatusupdate':
                print("\nReceived button state update request")
                print("Request data:", json.dumps(params, indent=2))
                target = params.get('target')
                status = params.get('status')
                state_changed = False
                
                print("\nCurrent states:")
                print("Button states:")
                print(f"- Main boiler button: {main_boiler_state}")
                print(f"- GH1 button: {gh1_button_state}")
                print(f"- GH2 button: {gh2_button_state}")
                print("\nUART states (for test config):")
                print(f"- GH1 UART: {gh1_uart_active}")
                print(f"- GH2 UART: {gh2_uart_active}")
                
                # Only update button states, not UART states
                if target == 'main_boiler':
                    new_state = 1 if status else 0
                    if new_state != main_boiler_state:
                        print(f"\nUpdating main boiler button state:")
                        print(f"Old state: {main_boiler_state}")
                        print(f"New state: {new_state}")
                        main_boiler_state = new_state
                        config.mainTankState = new_state  # همگام‌سازی با config.mainTankState
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
                
                # Always send and log UART message for button state changes
                print("\nSending flag 3 UART message...")
                print("Format: 3;main_boiler;gh1_button;gh2_button;pressure;temp")
                new_main = [main_boiler_state, gh1_button_state, gh2_button_state,
                          int(round(config.pressureConfig['pressure'])), 
                          int(round(config.mainAmpereConfig['temperature']))]
                send_main_uart()
                last_main_data = new_main
                
                # Log the UART message
                logging.info(f"Flag 3 UART message sent: 3;{main_boiler_state};{gh1_button_state};{gh2_button_state};{int(round(config.pressureConfig['pressure']))};{int(round(config.mainAmpereConfig['temperature']))}")
                
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
                    
                    logging.info(f"Calling send_actuator_uart with flag={flag}, enabled={enabled}")
                    print(f"\nCalling send_actuator_uart with flag={flag}, enabled={enabled}")
                    
                    send_actuator_uart(flag, enabled)
                    
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
                    new_main = [main_boiler_state, gh1_button_state, gh2_button_state,
                              int(round(config.pressureConfig['pressure'])), 
                              int(round(config.mainAmpereConfig['temperature']))]
                    send_main_uart()
                    last_main_data = new_main
                    
                    # لاگ کردن پیام UART
                    logging.info(f"Flag 3 UART message sent after pressure config update: 3;{main_boiler_state};{gh1_button_state};{gh2_button_state};{int(round(config.pressureConfig['pressure']))};{int(round(config.mainAmpereConfig['temperature']))}")
                    
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
                # Print UART message for flag 17 using simulate_uart_send
                s = f"17;{discharge_flag_value}"
                simulate_uart_send(s)
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
                    update_system_status(mode=mode_val, light=light_val, cup=cup_val, month=month, day=day, hour=hour, minute=minute)
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
                
                new_main = [main_boiler_state, gh1_button_state, gh2_button_state, 
                          int(round(config.pressureConfig['pressure'])), 
                          int(round(config.mainAmpereConfig['temperature']))]
                print(f"\nDebug - Main Config Update:")
                print(f"Old temperature: {old_temp}")
                print(f"New temperature: {config.mainAmpereConfig['temperature']}")
                print(f"Last main data: {last_main_data}")
                print(f"New main data: {new_main}")
                print(f"Are they different? {last_main_data != new_main}")
                
                if last_main_data != new_main:
                    print("Sending UART message due to config change...")
                    send_main_uart()
                    last_main_data = new_main
                else:
                    print("No change detected, skipping UART message")
                
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
                    send_gh_uart(1, config.gh1_config, send_preinfusion=True, send_backflush=False)
                elif gh_id == 'gh2':
                    config.gh2_config['pre_infusion'] = preinf_data
                    # Send only pre-infusion flag (16)
                    preinf_value = int(preinf_data.get('time', 0)) if preinf_data.get('enabled', False) else 0
                    send_gh_uart(2, config.gh2_config, send_preinfusion=True, send_backflush=False)
                
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
                    send_gh_uart(1, config.gh1_config, send_preinfusion=False, send_backflush=True)
                elif gh_id == 'gh2':
                    config.gh2_config['backflush'] = backflush_enabled
                    # Send only backflush flag (12)
                    send_gh_uart(2, config.gh2_config, send_preinfusion=False, send_backflush=True)
                
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
                    send_gh_uart(1, config.gh1_config, send_preinfusion=False, send_backflush=False)
                    last_gh1_data = [
                        int(round(config.gh1_config['temperature'])),
                        int(round(config.gh1_config['extraction_volume'])),
                        int(round(config.gh1_config['extraction_time'])),
                        int(round(config.gh1_config['purge']))
                    ]
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
                    send_gh_uart(2, config.gh2_config, send_preinfusion=False, send_backflush=False)
                    last_gh2_data = [
                        int(round(config.gh2_config['temperature'])),
                        int(round(config.gh2_config['extraction_volume'])),
                        int(round(config.gh2_config['extraction_time'])),
                        int(round(config.gh2_config['purge']))
                    ]
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
                    update_system_status(
                        mode=mode_val,
                        light=light_val,
                        cup=cup_val,
                        month=month_val,
                        day=day_val,
                        hour=hour_val,
                        minute=minute_val
                    )
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
                return

            # Add new endpoint for setting date and time (flag 19)
            if self.path == '/setdatetime':
                print("\n=== Processing Date & Time Update (Flag 19) ===")
                print(f"Received date/time: {json.dumps(params, indent=2)}")
                year = int(params.get('year', 0))
                month = int(params.get('month', 0))
                day = int(params.get('day', 0))
                hour = int(params.get('hour', 0))
                minute = int(params.get('minute', 0))
                second = int(params.get('second', 0))
                last_two_digits = year % 100
                uart_message = f"19;{last_two_digits:02d};{month:02d};{day:02d};{hour:02d};{minute:02d};{second:02d}"
                print(f"Sending UART message for date/time update: {uart_message}")
                simulate_uart_send(uart_message)
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

            # Add new endpoint for service mode (flag 21)
            elif self.path == '/setservicemode':
                print("\n=== Processing Service Mode Update ===")
                print(f"Request data: {json.dumps(params, indent=2)}")
                enabled = params.get('enabled', False)
                send_service_uart(enabled)
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
    server_address = ('', port)
    httpd = HTTPServer(server_address, RequestHandler)
    print(f'Starting server on port {port}...')
    
    # Start UART reading thread
    def uart_reader():
        while True:
            try:
                line = uart.read_line()
                if line:
                    try:
                        # Parse the message
                        parts = line.split(';')
                        if len(parts) < 2:
                            continue
                            
                        flag = int(parts[0])
                        values = [float(x) if '.' in x else int(x) for x in parts[1:]]
                        
                        # Process the message
                        handle_uart_message(flag, values)
                    except Exception as e:
                        print(f"Error processing UART message: {str(e)}")
                        logging.error(f"Error processing UART message: {str(e)}")
            except Exception as e:
                print(f"Error in UART reader thread: {str(e)}")
                logging.error(f"Error in UART reader thread: {str(e)}")
            time.sleep(0.1)  # Small delay to prevent CPU overuse
    
    # Start UART reader thread
    uart_thread = threading.Thread(target=uart_reader, daemon=True)
    uart_thread.start()
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down server...")
        uart.close()  # Close UART port
        httpd.server_close()

if __name__ == '__main__':
    run_server()
