// import { Link } from "react-router-dom";
// import Amper from "~/components/common/amper";
import { motion } from 'framer-motion'
import { BLOCK_ANIMATIONS_VARIANTS, ROUTE_VARIANTS } from "~/store/animationVars";
import { useState, useEffect } from "react";
import { Button, Modal } from "~/components/KIT";
import { useGeneralStore } from "~/store/general";
import { useTranslation } from 'react-i18next';
// import { MACHINE_KEY } from "~/store/consts";
import NewAmper from "~/components/common/newAmper";
import NewMainAmper from "~/components/common/newMainAmper";
// import { MdPower } from "react-icons/md";
import { FaPowerOff } from "react-icons/fa6";
import splashGif from '~/assets/gifs/splash.gif';
import { ECO_MODE_KEY } from "~/store/consts";
import { TestGhConfigReplica } from '~/containers/amperConfig/TestGhConfigReplica';
import { useGaugeData } from '~/hooks/useGaugeData';
import { useConfigData } from '~/hooks/useConfigData';
import axios from 'axios';

type Props = {};


function Home({ }: Props) {
  const { t } = useTranslation();
  const { gaugeData: gh1GaugeData, error: gh1GaugeError } = useGaugeData('1');
  const { gaugeData: gh2GaugeData, error: gh2GaugeError } = useGaugeData('2');
  const { saveGHConfig, saveMainConfig, error: configError, sendStatusUpdate } = useConfigData();
  const _changeCurrentPage = useGeneralStore((_state: any) => _state.changeCurrentPage)
  const initialSplashDone = useGeneralStore((_state: any) => _state.initialSplashDone ?? false);
  const setInitialSplashDone = useGeneralStore((_state: any) => _state.setInitialSplashDone);
  const ecoMode = useGeneralStore((_state: any) => _state[ECO_MODE_KEY] || 'off');
  const [status, setStatus] = useState<number[]>([])
  const [showSplash, setShowSplash] = useState(!initialSplashDone);
  const [testMode, setTestMode] = useState<'gh1' | 'gh2' | 'dual' | null>(null);
  const [mainBoilerOn, setMainBoilerOn] = useState(false);
  const [mainBoilerTemp, setMainBoilerTemp] = useState(0);
  const [gh1Active, setGh1Active] = useState(false);
  const [gh2Active, setGh2Active] = useState(false);
  // const { [MACHINE_KEY]: machine } = useGeneralStore();
  // console.log(machine)
  // const { t } = useTranslation("dashboard");

  const resetTestStates = () => {
    console.log('Resetting test states');
    setTestMode(null);
    setStatus([]);
    _changeCurrentPage({ url: '/dashboard/home', params: {} });
  };

  // Add effect to fetch all data and handle activation flags
  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await axios.get('http://localhost:8000/getdata');
        const data = response.data;
        setMainBoilerTemp(data.MainTankTemp);
        
        // If both GHs are active, switch to dual mode
        if (data.HGP1ACTIVE === 1 && data.HGP2ACTIVE === 1) {
          console.log('Both GHs active, switching to dual mode');
          setTestMode('dual');
          setStatus([1, 2]);
          return; // Exit early to prevent single GH activation
        }

        // Handle GH1 activation (only if not in dual mode)
        if (data.HGP1ACTIVE === 1 && testMode !== 'dual') {
          console.log('Activating GH1 mode');
          setTestMode('gh1');
          setStatus(prev => [...prev, 1]);
        }

        // Handle GH2 activation (only if not in dual mode)
        if (data.HGP2ACTIVE === 1 && testMode !== 'dual') {
          console.log('Activating GH2 mode');
          setTestMode('gh2');
          setStatus(prev => [...prev, 2]);
        }
      } catch (err) {
        console.error('Error fetching data:', err);
      }
    };

    // Initial fetch
    fetchData();

    // Set up polling every second
    const interval = setInterval(fetchData, 1000);

    // Cleanup
    return () => clearInterval(interval);
  }, [testMode]);

  // Add debug logging for test states
  useEffect(() => {
    console.log('Test mode updated:', { testMode, status });
  }, [testMode, status]);

  const isBothActive = status.length === 2
  const isOneActive = status.length === 1

  useEffect(() => {
    if (!initialSplashDone) {
      const timer = setTimeout(() => {
        setShowSplash(false);
        if (setInitialSplashDone) setInitialSplashDone();
      }, 7000); // 7 seconds
      return () => clearTimeout(timer);
    }
  }, [initialSplashDone, setInitialSplashDone]);

  // Add debug logging for gauge data
  useEffect(() => {
    if (gh1GaugeData) {
      console.log('GH1 Gauge Data:', {
        temperature: gh1GaugeData.temperature.value,
        pressure: gh1GaugeData.pressure.value,
        flow: gh1GaugeData.flow.value,
        isActive: gh1GaugeData.isActive
      });
    }
    if (gh2GaugeData) {
      console.log('GH2 Gauge Data:', {
        temperature: gh2GaugeData.temperature.value,
        pressure: gh2GaugeData.pressure.value,
        flow: gh2GaugeData.flow.value,
        isActive: gh2GaugeData.isActive
      });
    }
  }, [gh1GaugeData, gh2GaugeData]);

  // Update local state when gauge data changes
  useEffect(() => {
    if (gh1GaugeData?.isActive !== undefined) {
      setGh1Active(gh1GaugeData.isActive);
    }
  }, [gh1GaugeData?.isActive]);

  useEffect(() => {
    if (gh2GaugeData?.isActive !== undefined) {
      setGh2Active(gh2GaugeData.isActive);
    }
  }, [gh2GaugeData?.isActive]);

  // Add error handling
  if (gh1GaugeError) {
    console.error('GH1 Gauge data error:', gh1GaugeError);
  }
  if (gh2GaugeError) {
    console.error('GH2 Gauge data error:', gh2GaugeError);
  }

  if (showSplash) {
    return (
      <div style={{
        width: '100vw',
        height: '100vh',
        background: '#181818',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 9999,
        position: 'fixed',
        top: 0,
        left: 0,
      }}>
        <img src={splashGif} alt="Splash" style={{ width: '100vw', height: '100vh', objectFit: 'cover' }} />
      </div>
    );
  }

  // console.log(_changeCurrentPage)
  if (testMode) {
    return <TestGhConfigReplica onClose={resetTestStates} initialMode={testMode} />;
  }

  return (
    <>
      <motion.div
        variants={ROUTE_VARIANTS}
        initial="initial"
        animate="final"
        className="relative flex column alignCenter justifyCenter container pt4" style={{
          height: '100vh'
        }}>
        {/* Temporary Test Buttons */}
        <div style={{ position: 'absolute', top: 10, left: 10, zIndex: 1000 }}>
          <Button className="outlined" style={{ background: '#fff', color: '#222' }} onClick={() => {
            setTestMode('gh1');
          }}>Test 1</Button>
        </div>
        <div style={{ position: 'absolute', top: 10, left: '50%', transform: 'translateX(-50%)', zIndex: 1000 }}>
          <Button className="outlined" style={{ background: '#fff', color: '#222' }} onClick={() => {
            setTestMode('dual');
          }}>Test 3</Button>
        </div>
        <div style={{ position: 'absolute', top: 10, right: 10, zIndex: 1000 }}>
          <Button className="outlined" style={{ background: '#fff', color: '#222' }} onClick={() => {
            setTestMode('gh2');
          }}>Test 2</Button>
        </div>
        {/* Mode indicator moved to header */}
        <div className="flex justifyBetween alignCenter absolute" style={{
          bottom: 8,
          left: 16,
          right: 16
        }}>
          <div className="flex alignCenter">
            <Button className="outlined-2 radius-3 px4 py3" style={{ borderColor: '#2196f3', fontSize: '1.1em', color: '#ffffff', borderWidth: '2px' }}
              onClick={() => { sendStatusUpdate('main_boiler', !mainBoilerOn); setMainBoilerOn(prev => !prev); }}>
              {t('main_boiler')}
              <FaPowerOff size="1.2em" className="mr2" />
            </Button>
            <Button className="mx2 outlined-2 radius-3 px4 py3" style={{ borderColor: '#2196f3', fontSize: '1.1em', color: '#ffffff', borderWidth: '2px' }}
              onClick={() => { 
                sendStatusUpdate('gh1', !gh1Active);
                setGh1Active(prev => !prev);
              }}>
              {t('head_group_1')}
              <FaPowerOff size="1.2em" className="mr2" />
            </Button>
            <Button className="outlined-2 radius-3 px4 py3" style={{ borderColor: '#2196f3', fontSize: '1.1em', color: '#ffffff', borderWidth: '2px' }}
              onClick={() => { 
                sendStatusUpdate('gh2', !gh2Active);
                setGh2Active(prev => !prev);
              }}>
              {t('head_group_2')}
              <FaPowerOff size="1.2em" className="mr2" />
            </Button>
          </div>
          <div>
            <Button onClick={() => {
              if (status.includes(1)) {
                setStatus(prev => prev.filter(_n => _n !== 1))
                return
              }
              setStatus(prev => ([...prev, 1]))
            }} className={`radius-3 ${status.includes(1) ? 'filled primary' : 'outlined-2'} ml1`} style={{ display: 'none' }}>
              {t('active_gh1')}
            </Button>
            <Button onClick={() => {
              if (status.includes(2)) {
                setStatus(prev => prev.filter(_n => _n !== 2))
                return
              }
              setStatus(prev => ([...prev, 2]))
            }} className={`radius-3 ${status.includes(2) ? 'filled primary' : 'outlined-2'}`} style={{ display: 'none' }}>
              {t('active_gh2')}
            </Button>
          </div>
          {/* <Link to={`/dashboard/presureConfig`}> */}
          <Button className="outlined-2 radius-3 px4 py3" style={{ borderColor: '#2196f3', fontSize: '1.1em', color: '#ffffff', borderWidth: '2px' }} onClick={() => {
            _changeCurrentPage({
              url: '/dashboard/presureConfig',
              params: {}
            })
          }}>
            {t('pressure')}
          </Button>
          {/* </Link> */}

        </div>
        {testMode ? (
          <div style={{ position: 'fixed', top:0, left: 0, width: '100vw', height: '100vh', background: 'rgba(0,0,0,0.02)', zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <motion.div layout animate={{ scale: 1.2 }} transition={{ type: 'spring', stiffness: 120 }}>
              <NewAmper
                value2={5}
                value={92.5}
                title={`${t('temperature')} - 1`}
                axisLabelDistance={54}
                axisTickLength={10}
                progressWidth={32}
                axisLineWidth={32}
                titleSize={'2em'}
                valueSize={'3em'}
                secondTitleSize={'2em'}
                thirdTitleSize={'1.5em'}
                secondTitle={t('volume')}
                secondValue={55}
                thirdTitle={t('extraction_time')}
                thirdValue={64}
              />
            </motion.div>
          </div>
        ) : (
          <div className={`grid col24 gap-6 w100 alignCenter ${status.length > 0 ? 'px24' : ''}`} style={{ overflow: 'hidden', direction: 'ltr' }}>
            {(status.length === 0 || status.includes(1)) ?
              <motion.div
                variants={BLOCK_ANIMATIONS_VARIANTS}
                className={`relative ${isBothActive ? 'span-12' : (isOneActive && status.includes(1)) ? 'span-24' : 'span-7'}`}
                style={{ height: '500px' }}>
                <div 
                onClick={() => {
                  _changeCurrentPage({
                    url: '/dashboard/amperConfig',
                    params: {
                      amperId: 1
                    }
                  });
                }}
                  style={{ 
                    height: '300px', 
                    width: '100%', 
                    position: 'absolute', 
                    top: 0, 
                    left: 0, 
                    zIndex: 2,
                    cursor: 'pointer'
                  }}
                />
                <div style={{ position: 'relative', zIndex: 1 }}>
                <NewAmper
                  value2={gh1GaugeData?.pressure?.value ?? 0}
                  value={gh1GaugeData?.temperature?.value ?? 92.5}
                  title={`${t('temperature')} - 1`}
                  axisLabelDistance={isBothActive ? 44 : (isOneActive && status.includes(1)) ? 54 : 32}
                  axisTickLength={isBothActive ? 8 : (isOneActive && status.includes(1)) ? 10 : 6}
                  progressWidth={isBothActive ? 24 : (isOneActive && status.includes(1)) ? 32 : 18}
                  axisLineWidth={isBothActive ? 24 : (isOneActive && status.includes(1)) ? 32 : 18}
                  titleSize={isBothActive ? '1.1em' : (isOneActive && status.includes(2)) ? '1.1em' : '0.6em'}
                  valueSize={isBothActive ? '2em' : (isOneActive && status.includes(2)) ? '2em' : '1em'}
                  secondTitleSize={isBothActive ? '1.5em' : (isOneActive && status.includes(1)) ? '2em' : '1em'}
                  thirdTitleSize={isBothActive ? '1em' : (isOneActive && status.includes(1)) ? '1.5em' : '0.8em'}
                  secondTitle={t('volume')}
                  secondValue={0}
                  thirdTitle={t('extraction_time')}
                  thirdValue={0}
                />
                </div>
              </motion.div>
              : ''}

            {status.length === 0 ? (
              <motion.div 
                layout 
                variants={BLOCK_ANIMATIONS_VARIANTS} 
                className={`relative ${isOneActive ? 'span-0' : 'span-10'}`}
                style={{ marginTop: '1.5rem' }}>
                <div 
                onClick={() => {
                  _changeCurrentPage({
                    url: '/dashboard/temperatureConfig',
                    params: {}
                  });
                }}
                  style={{ 
                    height: '300px', 
                    width: '100%',
                    position: 'absolute', 
                    top: 0, 
                    left: 0, 
                    zIndex: 2,
                    cursor: 'pointer'
                  }}
                />
                <div style={{ position: 'relative', zIndex: 1 }}>
                <NewMainAmper
                  titleSize='1.3em'
                  valueSize='3em'
                  title={t('steam_boiler_temperature')}
                  progressWidth={24}
                  axisLineWidth={24}
                  value={mainBoilerTemp}
                  secondTitle={t('degrees_celsius')}
                  secondTitleSize='1.8em'
                  thirdTitleSize='1.2em'
                />
                </div>
              </motion.div>
            ) : ''}

            {(status.length === 0 || status.includes(2)) ?
              <motion.div
                variants={BLOCK_ANIMATIONS_VARIANTS} 
                className={`relative ${isBothActive ? 'span-12' : (isOneActive && status.includes(2)) ? 'span-24' : 'span-7'}`}
                style={{ height: '500px' }}>
                <div 
                onClick={() => {
                  _changeCurrentPage({
                    url: '/dashboard/amperConfig',
                    params: {
                      amperId: 2
                    }
                  });
                }}
                  style={{ 
                    height: '300px', 
                    width: '100%', 
                    position: 'absolute', 
                    top: 0, 
                    left: 0, 
                    zIndex: 2,
                    cursor: 'pointer'
                  }}
                />
                <div style={{ position: 'relative', zIndex: 1 }}>
                <NewAmper
                  value2={gh2GaugeData?.pressure?.value ?? 0}
                  value={gh2GaugeData?.temperature?.value ?? 92.5}
                  title={`${t('temperature')} - 2`}
                  axisLabelDistance={isBothActive ? 44 : (isOneActive && status.includes(2)) ? 54 : 32}
                  axisTickLength={isBothActive ? 8 : (isOneActive && status.includes(2)) ? 10 : 6}
                  progressWidth={isBothActive ? 24 : (isOneActive && status.includes(2)) ? 32 : 18}
                  axisLineWidth={isBothActive ? 24 : (isOneActive && status.includes(2)) ? 32 : 18}
                  titleSize={isBothActive ? '1.1em' : (isOneActive && status.includes(2)) ? '1.1em' : '0.6em'}
                  valueSize={isBothActive ? '2em' : (isOneActive && status.includes(2)) ? '2em' : '1em'}
                  secondTitleSize={isBothActive ? '1.5em' : (isOneActive && status.includes(2)) ? '2em' : '1em'}
                  thirdTitleSize={isBothActive ? '1em' : (isOneActive && status.includes(2)) ? '1.5em' : '0.8em'}
                  secondTitle={t('volume')}
                  secondValue={0}
                  thirdTitle={t('extraction_time')}
                  thirdValue={0}
                />
                </div>
              </motion.div>
              : ''}
          </div>
        )}
      </motion.div>
    </>
  );
}

export default Home;
