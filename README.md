import serial
import time
import sys

def test_uart():
    print("\n=== Starting UART Test ===")
    print("Port: /dev/ttyAMA0")
    print("Baudrate: 9600")
    print("========================\n")
    
    try:
        # Initialize serial port
        ser = serial.Serial(
            port='/dev/ttyAMA0',
            baudrate=9600,
            timeout=1
        )
        
        # Wait for serial connection to initialize
        time.sleep(2)
        
        print("UART port opened successfully")
        print("Starting message loop...")
        print("Press Ctrl+C to stop\n")
        
        counter = 0
        while True:
            try:
                # Create test message
                message = f"Hello World! Count: {counter}"
                encoded_message = (message + '\n').encode()
                
                # Print what we're sending
                print(f"\n=== Sending UART Message ===")
                print(f"Raw message: {message}")
                print(f"Encoded: {encoded_message}")
                
                # Send the message
                bytes_written = ser.write(encoded_message)
                ser.flush()  # Ensure message is sent
                
                # Print confirmation
                print(f"Bytes written: {bytes_written}")
                print(f"Message sent successfully")
                print("===========================\n")
                
                # Try to read any response
                if ser.in_waiting:
                    response = ser.readline().decode('utf-8').strip()
                    print(f"Received: {response}")
                
                # Increment counter and wait
                counter += 1
                time.sleep(2)  # Send message every 2 seconds
                
            except KeyboardInterrupt:
                print("\nStopping test...")
                break
            except Exception as e:
                print(f"\n!!! Error in message loop !!!")
                print(f"Error type: {type(e).__name__}")
                print(f"Error message: {str(e)}")
                import traceback
                print(f"Traceback: {traceback.format_exc()}")
                break
                
    except Exception as e:
        print(f"\n!!! UART INITIALIZATION ERROR !!!")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print("\nUART port closed")
        print("\n=== UART Test Ended ===\n")

if __name__ == "__main__":
    test_uart()
