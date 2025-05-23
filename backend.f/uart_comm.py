import serial
import threading
import time
import json
import logging
from typing import Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class UARTCommunicator:
    def __init__(self, port='/dev/ttyS0', baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.running = False
        self.data_lock = threading.Lock()
        self.current_data = {
            "main_temperature": 110.0,
            "gh1": {
                "temperature": 114.0,
                "pressure": 0.0
            },
            "gh2": {
                "temperature": 92.0,
                "pressure": 0.0
            }
        }
        self.config_data = {
            "main_config": {
                "temperature": 110.0,
                "pressure": 9.0
            },
            "gh1_config": {
                "temperature": 114.0,
                "extraction_volume": 0,
                "extraction_time": 20,
                "pre_infusion": 0,
                "purge": 0,
                "backflush": False
            },
            "gh2_config": {
                "temperature": 92.0,
                "extraction_volume": 0,
                "extraction_time": 20,
                "pre_infusion": 0,
                "purge": 0,
                "backflush": False
            }
        }

    def start(self):
        """Start the UART communication"""
        try:
            self.ser = serial.Serial(self.port, self.baudrate)
            time.sleep(2)  # Wait for serial connection to initialize
            self.running = True
            
            # Start reading thread
            self.read_thread = threading.Thread(target=self._read_loop)
            self.read_thread.daemon = True
            self.read_thread.start()
            
            # Start writing thread
            self.write_thread = threading.Thread(target=self._write_loop)
            self.write_thread.daemon = True
            self.write_thread.start()
            
            print(f"UART communication started on {self.port}")
        except Exception as e:
            print(f"Error starting UART communication: {e}")
            self.stop()

    def stop(self):
        """Stop the UART communication"""
        self.running = False
        if self.ser and self.ser.is_open:
            self.ser.close()
        print("UART communication stopped")

    def _read_loop(self):
        """Continuously read data from UART"""
        while self.running:
            try:
                if self.ser.in_waiting:
                    data = self.ser.readline().decode('utf-8').strip()
                    self._process_received_data(data)
            except Exception as e:
                print(f"Error reading from UART: {e}")
                time.sleep(1)

    def _write_loop(self):
        """Continuously write data to UART"""
        while self.running:
            try:
                # Prepare data to send
                data_to_send = {
                    "type": "status",
                    "data": self.current_data
                }
                
                # Send the data
                self.ser.write((json.dumps(data_to_send) + '\n').encode())
                time.sleep(0.1)  # Small delay between writes
            except Exception as e:
                print(f"Error writing to UART: {e}")
                time.sleep(1)

    def _process_received_data(self, data: str):
        """Process received data from UART"""
        try:
            received_data = json.loads(data)
            data_type = received_data.get('type')
            
            if data_type == 'sensor_data':
                # Update current data with sensor readings
                with self.data_lock:
                    sensor_data = received_data.get('data', {})
                    if 'main_temperature' in sensor_data:
                        self.current_data['main_temperature'] = sensor_data['main_temperature']
                    if 'gh1' in sensor_data:
                        self.current_data['gh1'].update(sensor_data['gh1'])
                    if 'gh2' in sensor_data:
                        self.current_data['gh2'].update(sensor_data['gh2'])
                        
            elif data_type == 'config_update':
                # Update configuration data
                config_data = received_data.get('data', {})
                if 'main_config' in config_data:
                    self.config_data['main_config'].update(config_data['main_config'])
                if 'gh1_config' in config_data:
                    self.config_data['gh1_config'].update(config_data['gh1_config'])
                if 'gh2_config' in config_data:
                    self.config_data['gh2_config'].update(config_data['gh2_config'])
                    
        except json.JSONDecodeError:
            print(f"Invalid JSON data received: {data}")
        except Exception as e:
            print(f"Error processing received data: {e}")

    def get_current_data(self) -> Dict[str, Any]:
        """Get current sensor data"""
        with self.data_lock:
            return self.current_data.copy()

    def get_config_data(self) -> Dict[str, Any]:
        """Get current configuration data"""
        return self.config_data.copy()

    def update_config(self, config_type: str, config_data: Dict[str, Any]):
        """Update configuration data"""
        if config_type in self.config_data:
            self.config_data[config_type].update(config_data)
            # Send updated config to UART
            try:
                data_to_send = {
                    "type": "config_update",
                    "data": {config_type: config_data}
                }
                self.ser.write((json.dumps(data_to_send) + '\n').encode())
            except Exception as e:
                print(f"Error sending config update: {e}")

# Example usage
if __name__ == "__main__":
    uart = UARTCommunicator()
    try:
        uart.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping UART communication...")
    finally:
        uart.stop() 