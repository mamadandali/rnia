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
import serial  # اضافه کردن ماژول serial برای ارتباط UART
import subprocess
import os

# Global state variables
main_boiler_state = 0
gh1_button_state = 0
gh2_button_state = 0
gh1_uart_active = False
gh2_uart_active = False
last_main_data = [0, 0, 0, 90, 1200]  # مقدار اولیه برای last_main_data
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
        message = record.getMessage()
        # فیلتر کردن درخواست‌های مکرر
        ignored_paths = ['GET /getdata', 'GET /getlockstatus', 'GET /getmainstatus']
        return not any(path in message for path in ignored_paths)

# Apply filter to all handlers
for handler in logger.handlers:
    handler.addFilter(GetDataFilter())

class Config:
    def __init__(self):
        # متغیرهای وضعیت دکمه‌ها
        self.main_boiler_state = 0
        self.gh1_button_state = 0
        self.gh2_button_state = 0
        self.gh1_uart_active = False
        self.gh2_uart_active = False
        self.last_main_data = [1, 1, 1, 90, 1200]  # مقدار اولیه برای last_main_data
        
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
        
        # اضافه کردن متغیرهای قفل
        self.lock_state = {
            "mode": 0,  # 0 = باز, 1 = قفل نوع 1, 2 = قفل نوع 2
            "code1": None,  # کد قفل نوع 1 - از UART دریافت می‌شود
            "code2": None   # کد قفل نوع 2 - از UART دریافت می‌شود
        }
        
        # اضافه کردن last_main_data به کلاس Config
        self.last_main_data = [0, 0, 0, 90, 1200]  # مقدار اولیه برای last_main_data
        
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

def simulate_uart_send(s: str):
    """Send UART message using the real UART port"""
    uart.send_string(s)

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
    s = f"3;{config.main_boiler_state};{config.gh1_button_state};{config.gh2_button_state};{pressure};{main_temp}"
    
    print("\nSending flag 3 UART message:")
    print("Format: 3;mainboiler button state;gh1 button state;gh2 b state;pressure;main boiler temp")
    print(f"Values: 3;{config.main_boiler_state};{config.gh1_button_state};{config.gh2_button_state};{pressure};{main_temp}")
    print("\nButton states:")
    print(f"- Main boiler button: {config.main_boiler_state}")
    print(f"- GH1 button: {config.gh1_button_state}")
    print(f"- GH2 button: {config.gh2_button_state}")
    print(f"\nOther values:")
    print(f"- Pressure: {pressure}")
    print(f"- Main boiler temp: {main_temp}")
    
    # ارسال پیام از طریق simulate_uart_send
    simulate_uart_send(s)

def send_test_config_uart():
    """Send UART message for test config activation"""
    print("\nSending test config UART messages...")
    # Send UART messages for test config activation
    if config.gh1_uart_active:
        s = f"13;{config.gh1_uart_active}"
        print(f"Activating GH1 test config (UART state: {config.gh1_uart_active})")
        simulate_uart_send(s)
        # Update HGP1ACTIVE only when UART message is sent
        config.HGP1ACTIVE = config.gh1_uart_active
    if config.gh2_uart_active:
        s = f"14;{config.gh2_uart_active}"
        print(f"Activating GH2 test config (UART state: {config.gh2_uart_active})")
        simulate_uart_send(s)
        # Update HGP2ACTIVE only when UART message is sent
        config.HGP2ACTIVE = config.gh2_uart_active

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
    # ارسال پیام از طریق simulate_uart_send
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

def update_display_power_settings(eco_mode: int):
    """
    تنظیم رفتار صفحه نمایش بر اساس حالت اکو
    eco_mode: 0 = خاموش (صفحه همیشه روشن), 1 = حالت اکو (خواب بعد از 900 ثانیه)
    """
    try:
        if eco_mode == 0:  # حالت خاموش - صفحه همیشه روشن
            # غیرفعال کردن DPMS و جلوگیری از خواب رفتن صفحه
            subprocess.run(['xset', 's', 'off'], check=True)  # غیرفعال کردن محافظ صفحه
            subprocess.run(['xset', 's', 'noblank'], check=True)  # جلوگیری از سیاه شدن صفحه
            subprocess.run(['xset', 'dpms', '0', '0', '0'], check=True)  # غیرفعال کردن DPMS
            subprocess.run(['xset', '-dpms'], check=True)  # غیرفعال کردن کامل DPMS
            logging.info("Display power settings: Always ON (Eco mode OFF)")
            print("Display power settings: Always ON (Eco mode OFF)")
        else:  # حالت اکو - خواب بعد از 900 ثانیه (15 دقیقه)
            # فعال کردن DPMS با تایمر 900 ثانیه
            subprocess.run(['xset', 's', 'on'], check=True)  # فعال کردن محافظ صفحه
            subprocess.run(['xset', 's', 'blank'], check=True)  # اجازه سیاه شدن صفحه
            subprocess.run(['xset', 'dpms', '900', '900', '900'], check=True)  # تنظیم تایمر 900 ثانیه
            subprocess.run(['xset', '+dpms'], check=True)  # فعال کردن DPMS
            logging.info("Display power settings: Sleep after 900s (15 minutes) (Eco mode ON)")
            print("Display power settings: Sleep after 900s (15 minutes) (Eco mode ON)")
    except subprocess.CalledProcessError as e:
        logging.error(f"Error updating display power settings: {str(e)}")
        print(f"Error updating display power settings: {str(e)}")
    except Exception as e:
        logging.error(f"Unexpected error in update_display_power_settings: {str(e)}")
        print(f"Unexpected error in update_display_power_settings: {str(e)}")

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
        # به‌روزرسانی تنظیمات صفحه نمایش بر اساس حالت اکو
        update_display_power_settings(mode)
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
        
        # ارسال پیام از طریق simulate_uart_send
        simulate_uart_send(s)
        
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
    print(f"\nSending actuator {flag} {'ENABLED' if enabled else 'DISABLED'}")
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
        if flag == 20:  # پیام خطا
            print("\nProcessing error message (flag 20)")
            error_code = int(values[0])
            if 0 <= error_code < len(ERROR_LIST):
                error_info = ERROR_LIST[error_code]
                # استفاده از زمان مرکزی سیستم برای ثبت زمان خطا
                current_time = config.current_time
                date_str = f"{current_time['year']}-{current_time['month']:02d}-{current_time['day']:02d} {current_time['hour']:02d}:{current_time['minute']:02d}:{current_time['second']:02d}"
                error_entry = {
                    "row": error_code,  # اضافه کردن شماره ردیف
                    "code": error_info["code"],
                    "description": error_info["description"],
                    "date": date_str
                }
                ERROR_HISTORY.append(error_entry)
                print(f"Added error to history: {error_entry}")
            else:
                print(f"Invalid error code: {error_code}")
            return
            
        elif flag == 7:  # پیام قفل
            print("\n=== Processing Lock Message (flag 7) ===")
            lock_type = int(values[0])
            lock_code = str(values[1]) if len(values) > 1 else None
            
            if lock_type in [0, 1, 2]:
                print(f"Setting lock mode to {lock_type}")
                config.lock_state["mode"] = lock_type
                if lock_code and lock_type > 0:
                    if lock_type == 1:
                        config.lock_state["code1"] = lock_code
                        print("Updated lock code for type 1")
                    else:
                        config.lock_state["code2"] = lock_code
                        print("Updated lock code for type 2")
                elif lock_type == 0:
                    print("Lock is being unlocked")
            else:
                print(f"Invalid lock type: {lock_type}")
            return
            
        elif flag == 19:  # تنظیم تاریخ و زمان
            print(f"\nReceived date/time update (flag 19) with values: {values}")
            if len(values) >= 6:
                year = 2000 + int(values[0])  # Convert 2-digit year to 4-digit
                month, day, hour, minute, second = [int(x) for x in values[1:6]]
                config.current_time.update({
                    "year": year,
                    "month": month,
                    "day": day,
                    "hour": hour,
                    "minute": minute,
                    "second": second
                })
                print(f"Updated system time to: {year}/{month}/{day} {hour}:{minute}:{second}")
            return
            
        elif flag == 21:  # حالت سرویس
            print("\nProcessing service mode message (flag 21)")
            enabled = bool(int(values[0]))
            print(f"Service mode {'enabled' if enabled else 'disabled'}")
            # به‌روزرسانی وضعیت در config اگر نیاز باشد
            return
            
        elif flag >= 22 and flag <= 44:  # کنترل actuator ها
            print(f"\nProcessing actuator message (flag {flag})")
            enabled = bool(int(values[0]))
            print(f"Actuator {flag} {'enabled' if enabled else 'disabled'}")
            # به‌روزرسانی وضعیت actuator در config اگر نیاز باشد
            return
            
        elif flag == 50:  # Update system time
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
        elif flag == 11:  # GH1 backflush
            print(f"\nProcessing GH1 backflush (flag 11)")
            enabled = bool(int(values[0]))
            config.gh1_config['backflush'] = enabled
            print(f"GH1 backflush {'enabled' if enabled else 'disabled'}")
        elif flag == 12:  # GH2 backflush
            print(f"\nProcessing GH2 backflush (flag 12)")
            enabled = bool(int(values[0]))
            config.gh2_config['backflush'] = enabled
            print(f"GH2 backflush {'enabled' if enabled else 'disabled'}")
        elif flag == 15:  # GH1 pre-infusion
            print(f"\nProcessing GH1 pre-infusion (flag 15)")
            preinf_time = int(values[0])
            config.gh1_config['pre_infusion'] = {
                "enabled": preinf_time > 0,
                "time": preinf_time
            }
            print(f"GH1 pre-infusion time set to {preinf_time}s")
        elif flag == 16:  # GH2 pre-infusion
            print(f"\nProcessing GH2 pre-infusion (flag 16)")
            preinf_time = int(values[0])
            config.gh2_config['pre_infusion'] = {
                "enabled": preinf_time > 0,
                "time": preinf_time
            }
            print(f"GH2 pre-infusion time set to {preinf_time}s")
        elif flag == 17:  # Boiler discharge
            print(f"\nProcessing boiler discharge (flag 17)")
            discharge_type = int(values[0])
            discharge_map = {0: "none", 1: "drain_refill", 2: "drain_shutdown"}
            print(f"Boiler discharge set to {discharge_map.get(discharge_type, 'unknown')}")
    except Exception as e:
        print(f"Error handling UART message: {str(e)}")
        logging.error(f"Error handling UART message: {str(e)}")

def send_gh_main_config(flag, cfg):
    """Send only main group head configuration (flag 1 or 2) without pre-infusion or backflush"""
    print(f"\nSending GH{flag} main config only...")
    temp = int(round(cfg['temperature'] * 10))  # Multiply by 10 as requested
    ext_vol = int(round(cfg['extraction_volume']))
    ext_time = int(round(cfg['extraction_time']))
    purge = int(round(cfg.get('purge', 0)))
    
    # Send main configuration only (flag 1 or 2)
    # Format: flag;temp;ext_vol;ext_time;purge
    s = f"{flag};{temp};{ext_vol};{ext_time};{purge}"
    print(f"GH{flag} main config - Temp: {temp/10}°C, Volume: {ext_vol}, Time: {ext_time}s, Purge: {purge}")
    simulate_uart_send(s)
    print(f"=== GH{flag} Main Config Sent ===\n")

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
        if self.path == '/getlockstatus':
            print("\n=== Processing Lock Status Request ===")
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            lock_data = {
                "mode": config.lock_state["mode"],
                "is_locked": config.lock_state["mode"] > 0,
                "code1": config.lock_state["code1"],
                "code2": config.lock_state["code2"]
            }
            
            # فقط وضعیت قفل را لاگ می‌کنیم، نه کدها را
            print(f"Lock status: mode={lock_data['mode']}, is_locked={lock_data['is_locked']}")
            self.wfile.write(json.dumps(lock_data).encode())
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
            data["GH1_ACTIVATION_FLAG"] = config.gh1_button_state
            data["GH2_ACTIVATION_FLAG"] = config.gh2_button_state
            # Use UART activation states for HGP1ACTIVE/HGP2ACTIVE
            data["HGP1ACTIVE"] = config.HGP1ACTIVE
            data["HGP2ACTIVE"] = config.HGP2ACTIVE
            data["mainTankState"] = config.main_boiler_state  # استفاده از main_boiler_state به جای config.mainTankState
            
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
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        return

    def do_POST(self):
        print(f"\nReceived POST request to: {self.path}")
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            params = json.loads(post_data.decode('utf-8'))
            
            if self.path == '/setstatusupdate':
                print("\n=== Processing Button State Update ===")
                print(f"Request data: {json.dumps(params, indent=2)}")
                target = params.get('target')
                status = params.get('status')
                state_changed = False
                
                print("\nCurrent states:")
                print("Button states:")
                print(f"- Main boiler button: {config.main_boiler_state}")
                print(f"- GH1 button: {config.gh1_button_state}")
                print(f"- GH2 button: {config.gh2_button_state}")
                
                # به‌روزرسانی وضعیت دکمه‌ها
                if target == 'main_boiler':
                    new_state = 1 if status else 0
                    if new_state != config.main_boiler_state:
                        print(f"\nUpdating main boiler button state:")
                        print(f"Old state: {config.main_boiler_state}")
                        print(f"New state: {new_state}")
                        config.main_boiler_state = new_state
                        config.mainTankState = new_state  # همگام‌سازی با config.mainTankState
                        state_changed = True
                elif target == 'gh1':
                    new_state = 1 if status else 0
                    if new_state != config.gh1_button_state:
                        print(f"\nUpdating GH1 button state:")
                        print(f"Old state: {config.gh1_button_state}")
                        print(f"New state: {new_state}")
                        config.gh1_button_state = new_state
                        state_changed = True
                elif target == 'gh2':
                    new_state = 1 if status else 0
                    if new_state != config.gh2_button_state:
                        print(f"\nUpdating GH2 button state:")
                        print(f"Old state: {config.gh2_button_state}")
                        print(f"New state: {new_state}")
                        config.gh2_button_state = new_state
                        state_changed = True
                
                # ارسال پیام UART برای تغییر وضعیت دکمه‌ها
                if state_changed:
                    print("\nSending flag 3 UART message...")
                    print("Format: 3;main_boiler;gh1_button;gh2_button;pressure;temp")
                    new_main = [config.main_boiler_state, config.gh1_button_state, config.gh2_button_state,
                              int(round(config.pressureConfig['pressure'])), 
                              int(round(config.mainAmpereConfig['temperature']))]
                    send_main_uart()
                    config.last_main_data = new_main.copy()  # استفاده از copy برای جلوگیری از تغییر مستقیم
                    
                    # ثبت پیام UART در لاگ
                    logging.info(f"Flag 3 UART message sent: 3;{config.main_boiler_state};{config.gh1_button_state};{config.gh2_button_state};{int(round(config.pressureConfig['pressure']))};{int(round(config.mainAmpereConfig['temperature']))}")
                else:
                    print("\nNo button state changes, skipping UART message")
                
                # ارسال پاسخ موفقیت
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success"}).encode())
                return
                
            elif self.path == '/simulate_uart':
                print(f"\nSimulating UART message:")
                print(f"Flag: {params.get('flag')}")
                print(f"Values: {params.get('values')}")
                
                # پردازش پیام UART
                handle_uart_message(params.get('flag'), params.get('values'))
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success"}).encode())
                return
                
            elif self.path == '/setservicemode':
                print("\n=== Processing Service Mode Update ===")
                enabled = params.get('enabled', False)
                print(f"Service mode: {'ENABLED' if enabled else 'DISABLED'}")
                
                # ارسال پیام UART برای تغییر حالت سرویس
                send_service_uart(enabled)
                
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
                
                new_main = [config.main_boiler_state, config.gh1_button_state, config.gh2_button_state, 
                          int(round(config.pressureConfig['pressure'])), 
                          int(round(config.mainAmpereConfig['temperature']))]
                print(f"\nDebug - Main Config Update:")
                print(f"Old temperature: {old_temp}")
                print(f"New temperature: {config.mainAmpereConfig['temperature']}")
                print(f"Last main data: {config.last_main_data}")
                print(f"New main data: {new_main}")
                print(f"Are they different? {config.last_main_data != new_main}")
                
                if config.last_main_data != new_main:
                    print("Sending UART message due to config change...")
                    send_main_uart()
                    config.last_main_data = new_main.copy()
                else:
                    print("No change detected, skipping UART message")
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
                return

            elif self.path == '/setpressureconfig':
                print("\n=== Processing Pressure Config Update ===")
                print(f"Config: {json.dumps(params.get('config', {}), indent=2)}")
                new_config = params.get('config', {})
                old_pressure = config.pressureConfig['pressure']
                
                # به‌روزرسانی تنظیمات فشار
                config.pressureConfig.update({
                    "pressure": float(new_config.get('pressure', config.pressureConfig['pressure'])),
                    "max_pressure": float(new_config.get('max_pressure', config.pressureConfig['max_pressure'])),
                    "min_pressure": float(new_config.get('min_pressure', config.pressureConfig['min_pressure']))
                })
                
                print("\nUpdated Pressure Configuration:")
                print("--------------------------------")
                print(json.dumps(config.pressureConfig, indent=2))
                print("--------------------------------\n")
                
                # بررسی تغییر فشار و ارسال پیام UART در صورت نیاز
                new_main = [config.main_boiler_state, config.gh1_button_state, config.gh2_button_state, 
                          int(round(config.pressureConfig['pressure'])), 
                          int(round(config.mainAmpereConfig['temperature']))]
                
                print(f"\nDebug - Pressure Config Update:")
                print(f"Old pressure: {old_pressure}")
                print(f"New pressure: {config.pressureConfig['pressure']}")
                print(f"Last main data: {config.last_main_data}")
                print(f"New main data: {new_main}")
                print(f"Are they different? {config.last_main_data != new_main}")
                
                if config.last_main_data != new_main:
                    print("Sending UART message due to pressure change...")
                    send_main_uart()
                    config.last_main_data = new_main.copy()
                else:
                    print("No change detected, skipping UART message")
                
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
                
                # پردازش حالت اکو
                eco_mode = new_config.get('eco_mode')
                barista_light_val = new_config.get('barista_light')
                cup_warmer_val = new_config.get('cup_warmer')
                sleep_time = new_config.get('sleep_time')
                
                # نگاشت حالت‌ها به اعداد - فقط اگر eco_mode مشخص شده باشد
                mode_map = {'off': 0, 'eco': 1, 'sleep': 2}
                mode_val = None  # مقدار پیش‌فرض None
                if eco_mode is not None:
                    mode_val = mode_map.get(eco_mode, 0)
                
                # پردازش نور بارستا
                light_val = None
                if barista_light_val is not None:
                    if isinstance(barista_light_val, dict):
                        light_val = int(barista_light_val.get('percentage', 0)) if barista_light_val.get('enabled', False) else 0
                    else:
                        light_val = int(barista_light_val)
                
                # پردازش گرمکن فنجان
                cup_val = None
                if cup_warmer_val is not None:
                    if isinstance(cup_warmer_val, dict):
                        cup_val = int(cup_warmer_val.get('percentage', 0)) if cup_warmer_val.get('enabled', False) else 0
                    else:
                        cup_val = int(cup_warmer_val)
                
                # پردازش زمان خواب
                month = None
                day = None
                hour = None
                minute = None
                if sleep_time:
                    month = sleep_time.get('month')
                    day = sleep_time.get('day')
                    hour = sleep_time.get('hour')
                    minute = sleep_time.get('minute')
                
                print(f"Processed values:")
                print(f"- Mode: {eco_mode} -> {mode_val}")
                print(f"- Light: {light_val}")
                print(f"- Cup warmer: {cup_val}")
                print(f"- Sleep time: {month}/{day} {hour}:{minute}")
                
                # ارسال وضعیت سیستم
                update_system_status(
                    mode=mode_val,  # اگر None باشد، مقدار فعلی حفظ می‌شود
                    light=light_val,
                    cup=cup_val,
                    month=month,
                    day=day,
                    hour=hour,
                    minute=minute
                )
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
                return

            elif self.path == '/saveghconfig':
                print("\n=== Processing GH Config Update ===")
                gh_id = params.get('gh_id', 'ghundefined')
                new_config = params.get('config', {})
                preinf = new_config.get('pre_infusion', {})
                backflush = new_config.get('backflush', False)
                
                if gh_id == 'gh1':
                    print("\n=== UPDATING GH1 CONFIG ===")
                    # استفاده از extraction_volume به جای volume
                    extraction_volume = new_config.get('extraction_volume')
                    if extraction_volume is None:
                        extraction_volume = config.gh1_config['extraction_volume']
                        print(f"Using existing extraction_volume value: {extraction_volume}")
                    
                    config.gh1_config.update({
                        "temperature": float(new_config.get('temperature', config.gh1_config['temperature'])),
                        "extraction_volume": int(extraction_volume),
                        "extraction_time": int(new_config.get('extraction_time', config.gh1_config['extraction_time'])),
                        "pre_infusion": preinf,
                        "purge": int(new_config.get('purge', config.gh1_config['purge'])),
                        "backflush": backflush
                    })
                    print("\n=== SENDING GH1 UART MESSAGE ===")
                    print("Sending main config only (flag 1)")
                    print(f"Config values - Temp: {config.gh1_config['temperature']}, Volume: {config.gh1_config['extraction_volume']}, Time: {config.gh1_config['extraction_time']}")
                    # Send only main config UART (flag 1)
                    send_gh_main_config(1, config.gh1_config)
                    print("=== GH1 CONFIG UPDATE COMPLETE ===\n")
                    
                elif gh_id == 'gh2':
                    print("\n=== UPDATING GH2 CONFIG ===")
                    # استفاده از extraction_volume به جای volume
                    extraction_volume = new_config.get('extraction_volume')
                    if extraction_volume is None:
                        extraction_volume = config.gh2_config['extraction_volume']
                        print(f"Using existing extraction_volume value: {extraction_volume}")
                    
                    config.gh2_config.update({
                        "temperature": float(new_config.get('temperature', config.gh2_config['temperature'])),
                        "extraction_volume": int(extraction_volume),
                        "extraction_time": int(new_config.get('extraction_time', config.gh2_config['extraction_time'])),
                        "pre_infusion": preinf,
                        "purge": int(new_config.get('purge', config.gh2_config['purge'])),
                        "backflush": backflush
                    })
                    print("\n=== SENDING GH2 UART MESSAGE ===")
                    print("Sending main config only (flag 2)")
                    print(f"Config values - Temp: {config.gh2_config['temperature']}, Volume: {config.gh2_config['extraction_volume']}, Time: {config.gh2_config['extraction_time']}")
                    # Send only main config UART (flag 2)
                    send_gh_main_config(2, config.gh2_config)
                    print("=== GH2 CONFIG UPDATE COMPLETE ===\n")

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
                    preinf_flag = 15
                    preinf_s = f"{preinf_flag};{preinf_value}"
                    print(f"Sending pre-infusion config for GH1: {preinf_value}s")
                    simulate_uart_send(preinf_s)
                elif gh_id == 'gh2':
                    config.gh2_config['pre_infusion'] = preinf_data
                    # Send only pre-infusion flag (16)
                    preinf_value = int(preinf_data.get('time', 0)) if preinf_data.get('enabled', False) else 0
                    preinf_flag = 16
                    preinf_s = f"{preinf_flag};{preinf_value}"
                    print(f"Sending pre-infusion config for GH2: {preinf_value}s")
                    simulate_uart_send(preinf_s)
                
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
                    backflush_flag = 11
                    backflush_value = 1 if backflush_enabled else 0
                    backflush_s = f"{backflush_flag};{backflush_value}"
                    print(f"Sending backflush status for GH1: {backflush_value}")
                    simulate_uart_send(backflush_s)
                elif gh_id == 'gh2':
                    config.gh2_config['backflush'] = backflush_enabled
                    # Send only backflush flag (12)
                    backflush_flag = 12
                    backflush_value = 1 if backflush_enabled else 0
                    backflush_s = f"{backflush_flag};{backflush_value}"
                    print(f"Sending backflush status for GH2: {backflush_value}")
                    simulate_uart_send(backflush_s)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
                return

            elif self.path == '/setbackflush':
                print("\n=== Processing Backflush Update ===")
                print(f"Request data: {json.dumps(params, indent=2)}")
                gh_id = params.get('gh_id')
                backflush_data = params.get('backflush')
                
                if isinstance(backflush_data, dict):
                    # اگر داده به صورت آبجکت است، از enabled استفاده کن
                    new_value = 1 if backflush_data.get('enabled', False) else 0
                else:
                    # اگر داده به صورت مستقیم بولین است، از همان استفاده کن
                    new_value = 1 if backflush_data else 0
                
                # به‌روزرسانی تنظیمات backflush
                if gh_id == 1:
                    config.gh1Config['backflush'] = bool(new_value)
                    send_gh_uart(1, config.gh1Config, send_backflush=True)
                elif gh_id == 2:
                    config.gh2Config['backflush'] = bool(new_value)
                    send_gh_uart(2, config.gh2Config, send_backflush=True)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
                return

            elif self.path == '/setpreinfusion':
                print("\n=== Processing Pre-infusion Update ===")
                print(f"Request data: {json.dumps(params, indent=2)}")
                gh_id = params.get('gh_id')
                preinfusion_data = params.get('pre_infusion')
                
                if isinstance(preinfusion_data, dict):
                    # اگر داده به صورت آبجکت است، از time و enabled استفاده کن
                    new_value = int(round(preinfusion_data.get('time', 0))) if preinfusion_data.get('enabled', False) else 0
                else:
                    # اگر داده به صورت مستقیم عدد است، از همان استفاده کن
                    new_value = int(round(preinfusion_data)) if preinfusion_data > 0 else 0
                
                # به‌روزرسانی تنظیمات pre-infusion
                if gh_id == 1:
                    config.gh1Config['pre_infusion'] = {'enabled': new_value > 0, 'time': new_value}
                    send_gh_uart(1, config.gh1Config, send_preinfusion=True)
                elif gh_id == 2:
                    config.gh2Config['pre_infusion'] = {'enabled': new_value > 0, 'time': new_value}
                    send_gh_uart(2, config.gh2Config, send_preinfusion=True)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
                return

            elif self.path == '/settestconfig':
                print("\n=== Processing Test Config Update ===")
                print(f"Request data: {json.dumps(params, indent=2)}")
                gh_id = params.get('gh_id')
                test_data = params.get('test_config')
                
                if isinstance(test_data, dict):
                    # اگر داده به صورت آبجکت است، از enabled استفاده کن
                    new_value = 1 if test_data.get('enabled', False) else 0
                else:
                    # اگر داده به صورت مستقیم بولین است، از همان استفاده کن
                    new_value = 1 if test_data else 0
                
                # به‌روزرسانی تنظیمات تست
                if gh_id == 1:
                    config.gh1_uart_active = bool(new_value)
                    send_test_config_uart()
                elif gh_id == 2:
                    config.gh2_uart_active = bool(new_value)
                    send_test_config_uart()
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
                return

            elif self.path == '/setboilerdischarge':
                print("\n=== Processing Boiler Discharge Update ===")
                print(f"Request data: {json.dumps(params, indent=2)}")
                discharge_map = {'none': 0, 'drain_refill': 1, 'drain_shutdown': 2}
                discharge_value = params.get('discharge', 'none')
                discharge_flag_value = discharge_map.get(discharge_value, 0)
                print(f"Received discharge: {discharge_value} (flag value: {discharge_flag_value})")
                
                # ارسال پیام UART برای تخلیه بویلر
                s = f"17;{discharge_flag_value}"
                simulate_uart_send(s)
                print(f"=== Boiler Discharge (Flag 17) Sent ===\n")
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
                return

            elif self.path == '/setdatetime':
                try:
                    print("\n=== Processing DateTime Update ===")
                    print(f"Request data: {json.dumps(params, indent=2)}")
                    
                    # خواندن مستقیم مقادیر از params
                    year = int(params.get('year', 2024))
                    month = int(params.get('month', 1))
                    day = int(params.get('day', 1))
                    hour = int(params.get('hour', 0))
                    minute = int(params.get('minute', 0))
                    second = int(params.get('second', 0))
                    
                    # ارسال پیام UART برای تنظیم تاریخ و زمان
                    last_two_digits = year % 100
                    s = f"19;{last_two_digits:02d};{month:02d};{day:02d};{hour:02d};{minute:02d};{second:02d}"
                    print(f"Sending UART message for date/time update: {s}")
                    simulate_uart_send(s)
                    print(f"=== Date & Time UART (Flag 19) Sent ===\n")
                    
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': True}).encode())
                    return
                    
                except Exception as e:
                    logging.error(f"Error processing datetime update: {str(e)}")
                    print(f"\nError processing datetime update: {str(e)}")
                    self.send_error(500, str(e))
                    return

            elif self.path == '/setactuator':
                try:
                    data = json.loads(post_data)
                    print(f"\nReceived actuator data: {data}")
                    
                    flag = data.get('flag')
                    enabled = data.get('enabled')
                    
                    if flag is None or enabled is None:
                        print("\nMissing required parameters")
                        self.send_error(400, "Missing required parameters")
                        return
                        
                    if not isinstance(flag, int) or not isinstance(enabled, bool):
                        print("\nInvalid parameter types")
                        self.send_error(400, "Invalid parameter types")
                        return
                        
                    if flag < 22 or flag > 44:
                        print(f"\nInvalid actuator flag: {flag}")
                        self.send_error(400, "Invalid actuator flag")
                        return
                    
                    print(f"\nCalling send_actuator_uart with flag={flag}, enabled={enabled}")
                    send_actuator_uart(flag, enabled)
                    
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': True}).encode())
                    print("\nActuator request handled successfully")
                    
                except Exception as e:
                    print(f"\nError handling actuator request: {str(e)}")
                    self.send_error(500, str(e))
                    return

            elif self.path == '/setsystemstatus':
                print("\n=== Processing System Status Update ===")
                print(f"Received data: {json.dumps(params, indent=2)}")
                
                # پردازش پارامترهای وضعیت سیستم
                eco_mode = params.get('eco_mode')
                barista_light_val = params.get('barista_light')
                cup_warmer_val = params.get('cup_warmer')
                sleep_time = params.get('sleep_time', {})  # دریافت زمان خواب
                
                # تبدیل مقادیر به اعداد صحیح
                mode_val = mode_state  # استفاده از مقدار فعلی به عنوان پیش‌فرض
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
                
                update_system_status(
                    mode=mode_val,
                    light=light_val,
                    cup=cup_val,
                    month=1,
                    day=1,
                    hour=0,
                    minute=0
                )
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
                return

            else:
                self.send_response(404)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Endpoint not found'}).encode())
                return
                
        except Exception as e:
            print(f"Error processing POST request: {str(e)}")
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            error_response = json.dumps({"status": "error", "message": str(e)})
            self.wfile.write(error_response.encode())
            return

def run_server(port=8000):
    """Start the HTTP server"""
    global uart
    server_address = ('', port)
    httpd = HTTPServer(server_address, RequestHandler)
    print(f"Starting server on port {port}...")
    
    # تنظیم اولیه صفحه نمایش در زمان راه‌اندازی
    try:
        # بررسی وضعیت اولیه حالت اکو و اعمال تنظیمات صفحه نمایش
        update_display_power_settings(mode_state)
    except Exception as e:
        logging.error(f"Error setting initial display power settings: {str(e)}")
        print(f"Error setting initial display power settings: {str(e)}")
    
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
