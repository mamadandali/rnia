from Filler import SensorFloat, WaterLevel, Button
import threading
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Sensor definitions
sensors = [
    WaterLevel("MainTankWaterLevel"),
    WaterLevel("HeadGP1WaterLevel"),
    WaterLevel("HeadGP2WaterLevel"),
    SensorFloat("MainTankTemp"),
    SensorFloat("HeadGP1TopTemp"),
    SensorFloat("HeadGP1BottomTemp"),
    SensorFloat("HeadGP2TopTemp"),
    SensorFloat("HeadGP2BottomTemp"),
    SensorFloat("Pressure"),
    SensorFloat("MainTankWaterFlow"),
    SensorFloat("HeadGP1WaterFlow"),
    SensorFloat("HeadGP2WaterFlow"),
    SensorFloat("Current"),
    SensorFloat("Voltage"),
]

# Create a dictionary for easy sensor access
sensor_dict = {sensor.ID: sensor for sensor in sensors}

# System states
FLOWGPH1CGF = 0.0 
FLOWGPH2CGF = 0.0 

tempMainTankFlag = True
tempHeadGP1Flag = True
tempHeadGP2Flag = True

enableHeadGP1 = True
enableHeadGP2 = True
enableMainTank = True

Pressure1 = 0.0 
Pressure2 = 0.0

# UI settings
HGP1FlowVolume = 0 
HGP2FlowVolume = 0 
HGP1PreInfusion = 0 
HGP2PreInfusion = 0 
HGP1ExtractionTime = 20 
HGP2ExtractionTime = 20 
HDGP1WASHKkACTIVETIMEcfg = 5
HDGP2WASHKkACTIVETIMEcfg = 5
tempMainTankSetPoint = 120.0
tempHeadGP1SetPoint = 91.0
tempHeadGP2SetPoint = 92.0

# Additional features
tempCupFlag = False
cup = 0
baristaLight = False
light = 0
ecomode = 0 
dischargeMode = 0 

# Timing parameters
timeHGP1 = 0.0
timeHGP2 = 0.0
timeWaterLevelMainTank = 8
timeTempMainTank = 0
timeWaterLevelHG = 8
timeTempHG = 10

# System states
mainTankState = 1
HGP1State = 1 
HGP2State = 1 
HGP1ACTIVE = 0
HGP2ACTIVE = 0
HGP12MFlag = 4 
sebar = 0
HGPCheckStatus = False
backflush1 = 4 
backflush2 = 4

# Thread lock for thread-safe updates
update_lock = threading.Lock()

def update_sensor_value(sensor_id, value):
    """Update sensor value thread-safely"""
    with update_lock:
        if sensor_id in sensor_dict:
            sensor_dict[sensor_id].value = value
            logger.debug(f"Updated sensor {sensor_id} to {value}")

def update_system_state(state_id, value):
    """Update system state thread-safely"""
    with update_lock:
        global FLOWGPH1CGF, FLOWGPH2CGF, tempMainTankFlag, tempHeadGP1Flag, tempHeadGP2Flag
        global enableHeadGP1, enableHeadGP2, enableMainTank, Pressure1, Pressure2
        global mainTankState, HGP1State, HGP2State, HGP1ACTIVE, HGP2ACTIVE
        
        if state_id == 'FLOWGPH1CGF':
            FLOWGPH1CGF = value
        elif state_id == 'FLOWGPH2CGF':
            FLOWGPH2CGF = value
        elif state_id == 'tempMainTankFlag':
            tempMainTankFlag = value
        elif state_id == 'tempHeadGP1Flag':
            tempHeadGP1Flag = value
        elif state_id == 'tempHeadGP2Flag':
            tempHeadGP2Flag = value
        elif state_id == 'enableHeadGP1':
            enableHeadGP1 = value
        elif state_id == 'enableHeadGP2':
            enableHeadGP2 = value
        elif state_id == 'enableMainTank':
            enableMainTank = value
        elif state_id == 'Pressure1':
            Pressure1 = value
        elif state_id == 'Pressure2':
            Pressure2 = value
        elif state_id == 'mainTankState':
            mainTankState = value
        elif state_id == 'HGP1State':
            HGP1State = value
        elif state_id == 'HGP2State':
            HGP2State = value
        elif state_id == 'HGP1ACTIVE':
            HGP1ACTIVE = value
        elif state_id == 'HGP2ACTIVE':
            HGP2ACTIVE = value
        
        logger.debug(f"Updated state {state_id} to {value}")

def get_system_state():
    """Get current system state for UART transmission"""
    with update_lock:
        return {
            'sensors': {sensor.ID: sensor.value for sensor in sensors},
            'states': {
                'FLOWGPH1CGF': FLOWGPH1CGF,
                'FLOWGPH2CGF': FLOWGPH2CGF,
                'tempMainTankFlag': tempMainTankFlag,
                'tempHeadGP1Flag': tempHeadGP1Flag,
                'tempHeadGP2Flag': tempHeadGP2Flag,
                'enableHeadGP1': enableHeadGP1,
                'enableHeadGP2': enableHeadGP2,
                'enableMainTank': enableMainTank,
                'Pressure1': Pressure1,
                'Pressure2': Pressure2,
                'mainTankState': mainTankState,
                'HGP1State': HGP1State,
                'HGP2State': HGP2State,
                'HGP1ACTIVE': HGP1ACTIVE,
                'HGP2ACTIVE': HGP2ACTIVE
            }
        } 