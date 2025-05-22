import serial
import threading
import time
import json
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class UARTCommunication:
    def __init__(self, port='/dev/ttyAMA0', baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.serial = None
        self.is_running = False
        self.data_callback = None
        self.lock = threading.Lock()

    def start(self):
        """Start UART communication"""
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )
            self.is_running = True
            # Start reading thread
            self.read_thread = threading.Thread(target=self._read_loop)
            self.read_thread.daemon = True
            self.read_thread.start()
            logger.info(f"UART communication started on {self.port}")
        except Exception as e:
            logger.error(f"Failed to start UART communication: {str(e)}")
            raise

    def stop(self):
        """Stop UART communication"""
        self.is_running = False
        if self.serial and self.serial.is_open:
            self.serial.close()
        logger.info("UART communication stopped")

    def set_data_callback(self, callback):
        """Set callback function for received data"""
        self.data_callback = callback

    def send_data(self, data):
        """Send data to MCU"""
        try:
            with self.lock:
                if self.serial and self.serial.is_open:
                    # Convert data to JSON string and add newline
                    message = json.dumps(data) + '\n'
                    self.serial.write(message.encode())
                    logger.debug(f"Sent data: {data}")
        except Exception as e:
            logger.error(f"Failed to send data: {str(e)}")

    def _read_loop(self):
        """Background thread for reading data from MCU"""
        buffer = ""
        while self.is_running:
            try:
                if self.serial and self.serial.is_open:
                    # Read available data
                    data = self.serial.readline().decode('utf-8').strip()
                    if data:
                        try:
                            # Parse JSON data
                            parsed_data = json.loads(data)
                            if self.data_callback:
                                self.data_callback(parsed_data)
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON data received: {data}")
            except Exception as e:
                logger.error(f"Error reading from UART: {str(e)}")
                time.sleep(0.1)  # Prevent tight loop on error

# Example usage:
"""
# Initialize UART communication
uart = UARTCommunication()

# Define callback function for received data
def handle_mcu_data(data):
    # Update Config.py variables with received data
    if 'sensors' in data:
        for sensor_id, value in data['sensors'].items():
            # Update corresponding sensor value in Config.py
            pass
    if 'states' in data:
        for state_id, value in data['states'].items():
            # Update corresponding state in Config.py
            pass

# Set callback and start communication
uart.set_data_callback(handle_mcu_data)
uart.start()

# Send data to MCU
uart.send_data({
    'command': 'set_temperature',
    'value': 92.5
})
""" 