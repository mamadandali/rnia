import serial
import threading
import time
import logging
from typing import Dict, Any, Optional, Callable

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class UARTCommunicator:
    def __init__(self, port='/dev/ttyAMA0', baudrate=9600):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.running = False
        self.data_lock = threading.Lock()
        
        # Callback for received messages
        self.message_callback: Optional[Callable[[int, list], None]] = None
        
        print(f"\n=== UART Communicator Initialized ===")
        print(f"Port: {self.port}")
        print(f"Baudrate: {self.baudrate}")
        print("====================================\n")
        
        # Current state data
        self.current_data = {
            "main_temperature": 110.0,  # Will be divided by 10 when used
            "gh1": {
                "temperature": 921.0,   # Will be divided by 10 when used
                "pressure": 5.0,
                "flow": 80.0
            },
            "gh2": {
                "temperature": 921.0,   # Will be divided by 10 when used
                "pressure": 5.0,
                "flow": 80.0
            }
        }

    def set_message_callback(self, callback: Callable[[int, list], None]):
        """Set callback for received messages"""
        self.message_callback = callback

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
            
            print(f"UART communication started on {self.port} at {self.baudrate} baud")
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

    def _process_received_data(self, data: str):
        """Process received data from UART"""
        try:
            parts = data.split(';')
            if len(parts) < 2:
                print(f"Invalid UART message format: {data}")
                return

            flag = int(parts[0])
            values = [float(x) if '.' in x else int(x) for x in parts[1:]]
            
            # Print received message
            print(f"\nUART IN: {data}")
            
            # Update current data based on flag
            with self.data_lock:
                if flag == 8:  # Main boiler temperature
                    self.current_data['main_temperature'] = values[0]
                elif flag == 9:  # GH1 status
                    self.current_data['gh1'].update({
                        'temperature': values[0],
                        'pressure': values[1],
                        'flow': values[2]
                    })
                elif flag == 10:  # GH2 status
                    self.current_data['gh2'].update({
                        'temperature': values[0],
                        'pressure': values[1],
                        'flow': values[2]
                    })
                elif flag == 13:  # GH1 extraction start
                    self.current_data['gh1']['activation'] = values[0]
                elif flag == 14:  # GH2 extraction start
                    self.current_data['gh2']['activation'] = values[0]

            # Call message callback if set
            if self.message_callback:
                self.message_callback(flag, values)

        except ValueError as e:
            print(f"Error parsing UART message: {e}")
        except Exception as e:
            print(f"Error processing UART message: {e}")

    def get_current_data(self) -> Dict[str, Any]:
        """Get current sensor data"""
        with self.data_lock:
            return self.current_data.copy()

    def send_string(self, s: str):
        """Send a UART message string"""
        try:
            if not self.ser:
                print(f"\n!!! UART ERROR: Serial port not initialized !!!")
                print(f"Attempted to send: {s}")
                return
                
            if not self.ser.is_open:
                print(f"\n!!! UART ERROR: Serial port not open !!!")
                print(f"Attempted to send: {s}")
                return
                
            # Format the message with newline
            message = s + '\n'
            encoded_message = message.encode()
            
            # Print before sending
            print(f"\n=== UART OUTGOING MESSAGE ===")
            print(f"Raw message: {s}")
            print(f"Encoded: {encoded_message}")
            
            # Send the message
            bytes_written = self.ser.write(encoded_message)
            self.ser.flush()  # Ensure message is sent
            
            # Print confirmation
            print(f"Bytes written: {bytes_written}")
            print(f"Message sent successfully")
            print("=============================\n")
            
        except Exception as e:
            print(f"\n!!! UART SEND ERROR !!!")
            print(f"Error type: {type(e).__name__}")
            print(f"Error message: {str(e)}")
            print(f"Failed message: {s}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            print("========================\n")

    def send_gh_config(self, gh_id: int, config: Dict[str, Any]):
        """Send group head configuration (flag 1 or 2)"""
        try:
            print(f"\n=== Sending GH{gh_id} Configuration ===")
            flag = 1 if gh_id == 1 else 2
            
            # Prepare values
            temp = int(round(config['temperature']))  # Temperature is already multiplied by 10
            ext_vol = int(round(config['extraction_volume']))
            ext_time = int(round(config['extraction_time']))
            purge = int(round(config.get('purge', 0)))
            
            # Handle pre-infusion consistently with backend
            preinf_data = config.get('pre_infusion', {})
            if isinstance(preinf_data, dict):
                # Always use the time value, regardless of enabled state
                preinf = int(round(preinf_data.get('time', 0)))
            else:
                # If it's just a number (backward compatibility), use it directly
                preinf = int(round(preinf_data))
            
            # Print configuration details
            print(f"Temperature: {temp/10}°C (raw: {temp})")
            print(f"Extraction Volume: {ext_vol}ml")
            print(f"Extraction Time: {ext_time}s")
            print(f"Purge: {purge}s")
            print(f"Pre-infusion: {preinf}s (enabled: {preinf_data.get('enabled', False) if isinstance(preinf_data, dict) else preinf > 0})")
            
            # Send main configuration
            message = f"{flag};{temp};{ext_vol};{ext_time};{purge};{preinf}"
            self.send_string(message)
            
            # Send backflush status
            backflush_flag = 11 if gh_id == 1 else 12
            backflush_value = 1 if config.get('backflush', False) else 0
            backflush_message = f"{backflush_flag};{backflush_value}"
            print(f"\nSending backflush status: {backflush_value}")
            self.send_string(backflush_message)
            
            print(f"=== GH{gh_id} Configuration Sent ===\n")
            
        except Exception as e:
            print(f"\n!!! GH Config Send Error !!!")
            print(f"Error type: {type(e).__name__}")
            print(f"Error message: {str(e)}")
            print(f"GH ID: {gh_id}")
            print(f"Config: {config}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            print("============================\n")

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

    def send_system_status(self, mode: int, discharge: int, light: int, cup_warmer: int):
        """Send system status (flag 4)"""
        try:
            print(f"\n=== Sending System Status ===")
            print(f"Mode: {mode}")
            print(f"Discharge: {discharge}")
            print(f"Light: {light}%")
            print(f"Cup warmer: {cup_warmer}%")
            
            message = f"4;{mode};{discharge};{light};{cup_warmer}"
            self.send_string(message)
            
            print("=== System Status Sent ===\n")
            
        except Exception as e:
            print(f"\n!!! System Status Send Error !!!")
            print(f"Error type: {type(e).__name__}")
            print(f"Error message: {str(e)}")
            print(f"Values: mode={mode}, discharge={discharge}, light={light}, cup_warmer={cup_warmer}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            print("=============================\n")

    def send_gh_activation(self, gh_id: int, is_active: bool):
        """Send GH activation status (flag 13 or 14)"""
        try:
            flag = 13 if gh_id == 1 else 14
            value = 1 if is_active else 0
            message = f"{flag};{value}"
            self.send_string(message)
        except Exception as e:
            print(f"Error sending GH activation: {e}")

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
