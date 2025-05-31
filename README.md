import React, { useState, useEffect } from 'react'
import { MdArrowDropDown, MdArrowDropUp } from 'react-icons/md';
// import { } from 'react-router-dom';
import { Button } from '~/components/KIT';
// import { Amper } from '~/components/common';
import HoldableButton from '~/components/common/holdableButton';
import { motion } from 'framer-motion';
import { BLOCK_ANIMATIONS_VARIANTS, ROUTE_VARIANTS } from '~/store/animationVars';
import { useGeneralStore } from '~/store/general';
import { MACHINE_KEY } from '~/store/consts';
import { toast } from 'react-hot-toast';
import NewAmper from '~/components/common/newAmper';
import { useTranslation } from 'react-i18next';
import PreInfusionModal from '~/components/common/PreInfusionModal';
import { useConfigData } from '~/hooks/useConfigData';
import MyModal from '~/components/KIT/Modal';
// import { PRESURE } from '~/store/constants';
import axios from 'axios';


const headGroupTitle: {
    [key: number]: string
} = {
    1: '',
    2: ''
}

interface Props {
  onSave?: (config: any) => void;
  currentConfig?: any;
}

const GhAmperConfig = ({ onSave, currentConfig }: Props) => {
    const { t } = useTranslation();
    const { [MACHINE_KEY]: machine, changeAmperConfig, changeCurrentPage, CURRENT_PAGE } = useGeneralStore();
    const _amperId = CURRENT_PAGE.params.amperId || '1'
    // const navigate = useNavigate();
    // console.log(changeAmperConfig)
    // const params = useParams();
    const _selectedGh = _amperId === '1' ? machine.GH1 : machine.GH2
    const { saveGHConfig, fetchGHConfig, ghConfig } = useConfigData();
    const [currentPressure, setCurrentPressure] = useState(0);
    const [isPreInfusionModalOpen, setIsPreInfusionModalOpen] = React.useState(false);
    const [isBackflushModalOpen, setIsBackflushModalOpen] = React.useState(false);
    const [backflushValue, setBackflushValue] = React.useState(false);

    // Helper function to get pre-infusion data
    const getPreInfusionData = (config: any) => {
        console.log('getPreInfusionData input:', config);
        if (config?.pre_infusion) {
            const result = {
                enabled: config.pre_infusion.enabled || false,
                time: config.pre_infusion.time || 0
            };
            console.log('getPreInfusionData returning dict format:', result);
            return result;
        }
        // Fallback to legacy format
        const legacyPreInfusion = config?.preInfusion || _selectedGh.config.preInfusion || 0;
        const result = {
            enabled: legacyPreInfusion > 0,
            time: legacyPreInfusion
        };
        console.log('getPreInfusionData returning legacy format:', result);
        return result;
    };

    const [config, setConfig] = useState(() => {
        console.log('Initializing config with currentConfig:', currentConfig);
        const preInfusion = getPreInfusionData(currentConfig);
        const initialConfig = {
            temperature: currentConfig?.temperature || _selectedGh.config.boilerTemperator,
            preInfusionEnabled: preInfusion.enabled,
            preInfusionTime: preInfusion.time,
            extractionTime: currentConfig?.extraction_time || _selectedGh.config.extractionTime,
            volume: currentConfig?.volume || _selectedGh.config.volume,
            purge: currentConfig?.purge || 0,
            backflush: currentConfig?.backflush || false
        };
        console.log('Initial config state:', initialConfig);
        return initialConfig;
    });

    useEffect(() => {
        if (currentConfig) {
            console.log('currentConfig changed:', currentConfig);
            const preInfusion = getPreInfusionData(currentConfig);
            const newConfig = {
                temperature: currentConfig.temperature,
                preInfusionEnabled: preInfusion.enabled,
                preInfusionTime: preInfusion.time,
                extractionTime: currentConfig.extraction_time,
                volume: currentConfig.volume,
                purge: currentConfig.purge,
                backflush: currentConfig.backflush
            };
            console.log('Updating config with:', newConfig);
            setConfig(newConfig);
        }
    }, [currentConfig]);

    // Fetch pressure data from /getdata endpoint
    useEffect(() => {
        const fetchPressureData = async () => {
            try {
                const response = await axios.get('http://localhost:8000/getdata');
                const data = response.data;
                setCurrentPressure(_amperId === '1' ? data.PressureGPH1 : data.PressureGPH2);
            } catch (err) {
                console.error('Error fetching pressure data:', err);
            }
        };

        // Initial fetch
        fetchPressureData();

        // Set up polling every second
        const interval = setInterval(fetchPressureData, 1000);

        // Cleanup
        return () => clearInterval(interval);
    }, [_amperId]);

    function handleIncreaseTemp() {
        if (config.temperature >= 200) return // Assuming max temp is 200
        setConfig(prev => ({ ...prev, temperature: prev.temperature + 0.5 }));
    }
    function handleDecreaseTemp() {
        if (config.temperature <= 0) return // Assuming min temp is 0
        setConfig(prev => ({ ...prev, temperature: prev.temperature - 0.5 }));
    }
    // function handleIncreasePresure() {
    //     if (presure === PRESURE.MAX) return
    //     setPresure(prev => prev + 1);
    // }
    // function handleDecreasePresure() {
    //     if (presure === PRESURE.MIN) return
    //     setPresure(prev => prev - 1);
    // }

    function handleIncreaseVolume() {
        // if (temperature === 30) return
        setConfig(prev => ({ ...prev, volume: prev.volume + 1 }));
    }
    function handleDecreaseVolume() {
        if (config.volume === 0) return
        setConfig(prev => ({ ...prev, volume: prev.volume - 1 }));
    }
    function handleIncreaseTime() {
        // if (time === 200) return
        setConfig(prev => ({ ...prev, extractionTime: prev.extractionTime + 1 }));
    }
    function handleDecreaseTime() {
        if (config.extractionTime === 0) return
        setConfig(prev => ({ ...prev, extractionTime: prev.extractionTime - 1 }));
    }
    function handleIncreasePurge() {
        setConfig(prev => ({ ...prev, purge: prev.purge + 1 }));
    }
    function handleDecreasePurge() {
        if (config.purge === 0) return;
        setConfig(prev => ({ ...prev, purge: prev.purge - 1 }));
    }
    const handleSaveChanges = async () => {
        // First, fetch the latest config to ensure we have the most up-to-date pre-infusion data
        await fetchGHConfig();
        
        // Get the latest config for the current group head
        const ghId = `gh${_amperId}` as 'gh1' | 'gh2';
        const latestConfig = ghConfig?.[ghId];
        
        console.log('Saving changes with latest config:', {
            localConfig: config,
            latestConfig,
            ghConfig
        });

        // Build the save data using the latest config for pre-infusion and local state for other values
        const saveData = {
            temperature: Math.round(config.temperature * 10),  // Use local state
            pre_infusion: latestConfig?.pre_infusion || {
                enabled: false,
                time: 0
            },
            extraction_time: config.extractionTime,  // Use local state
            volume: config.volume,  // Use local state
            pressure: 9.0,
            flow: 2.5,
            backflush: config.backflush,  // Use local state
            purge: config.purge  // Use local state
        };

        console.log('Saving to backend with data:', saveData);
        await saveGHConfig(ghId, saveData);
        toast.success(t('configuration_saved_successfully'));
    };
    // useEffect(() => {
    //     if (machine) {
            

    //         setTemperature(_selectedGh.config.boilerTemperator)
    //         setVolume(_selectedGh.config.volume)
    //         setTime(_selectedGh.config.extractionTime)
    //     }
    // }, [machine])


    // listen to changes current page and if any changes happened, show message to user to save changes or not
    // useEffect(() => {
    //     return () => {
    //         // console.log(CURRENT_PAGE)
            
    //         const _TMP = useGeneralStore.getState().MACHINE_KEY[`GH${_amperId}`].config
    //         console.log('unmount', _TMP, temperature)
    //         // if(_TMP.params.amperId) return

    //         console.log(temperature, _selectedGh.config.boilerTemperator, volume, _selectedGh.config.extractionTime)
    //         if (temperature !== _selectedGh.config.boilerTemperator || volume !== _selectedGh.config.extractionTime) {
    //             toast.error('You have unsaved changes, do you want to save them?')
    //         }
    //     }
    // }, [CURRENT_PAGE])
    console.log('ghAmperConfig rendered', config.temperature)
    return (
        <>
            <motion.div
                variants={ROUTE_VARIANTS}
                initial="initial"
                animate="final"
                exit="exit"
                className="flex column alignCenter justifyCenter container sm" style={{
                    height: '100vh',
                    padding: 0,
                }}>
                <div className="grid col24 alignCenter gap-6 w100" style={{ maxHeight: '100%' }}>
                    <div className='span-12'>
                        {/* <Amper
                            titleSize='1.8em'
                            valueSize='6em'
                            title="Main Tank"
                            progressWidth={24}
                            axisLineWidth={24}
                            value={temperature}

                            secondTitleSize='1.8em'
                            thirdTitleSize='1.2em'
                        /> */}
                        {/* <Amper
                            progressWidth={24}
                            axisLineWidth={24}
                            titleSize='1.8em'
                            valueSize='6em'
                            title="GH 1"
                            value={temperature}
                            secondTitleSize='1.8em'
                            thirdTitleSize='1.2em'

                        /> */}

                        <NewAmper
                            titleSize='1em'
                            valueSize='3em'
                            title={`${t('temperature')} - ${_amperId}`}
                            secondTitle={t('volume')}
                            secondValue={config.volume}
                            value2={currentPressure}

                            thirdTitle={t('extraction_time')}
                            thirdValue={config.extractionTime}

                            progressWidth={24}
                            axisLineWidth={24}
                            value={config.temperature}

                            secondTitleSize='1.8em'
                            thirdTitleSize='1.2em'

                            axisLabelDistance={44}
                            axisTickLength={8}

                        />
                    </div>
                    <div className='span-12 flex column pr24 pb8' style={{ direction: 'rtl', overflowY: 'auto', maxHeight: '100%', paddingTop: '10em' }}>
                        {/* <motion.span
                            variants={BLOCK_ANIMATIONS_VARIANTS}
                            className='fs-lg '>
                            فشار هد گروپ {headGroupTitle[Number(params.amperId)]}
                        </motion.span>
                        <motion.div
                            variants={BLOCK_ANIMATIONS_VARIANTS}
                            className='flex alignCenter'>
                            <NumberInput
                                onDecrease={handleDecreasePresure}
                                onIncrease={handleIncreasePresure}
                                value={presure}
                                text='Bar'
                            />
                        </motion.div> */}


                        <motion.span
                            variants={BLOCK_ANIMATIONS_VARIANTS}
                            className='mt4 fs-lg '>
                            {`${t('temperature')} - ${_amperId}`}
                        </motion.span>
                        <motion.div
                            variants={BLOCK_ANIMATIONS_VARIANTS}
                            className='flex alignCenter'>
                            <NumberInput
                                onDecrease={handleDecreaseTemp}
                                onIncrease={handleIncreaseTemp}
                                value={config.temperature}
                                text={t('degrees_celsius')}
                            />
                        </motion.div>

                        <motion.span
                            variants={BLOCK_ANIMATIONS_VARIANTS}
                            className='mt4 fs-lg '>
                            {t('volume')}
                        </motion.span>
                        <motion.div
                            variants={BLOCK_ANIMATIONS_VARIANTS}
                            className='flex alignCenter'>
                            <NumberInput
                                onDecrease={handleDecreaseVolume}
                                onIncrease={handleIncreaseVolume}
                                value={config.volume}
                                text={t('milliliters')}
                            />
                        </motion.div>

                        {/* <div className='b bb1 w100 my3' /> */}
                        <motion.span variants={BLOCK_ANIMATIONS_VARIANTS} className='mt4 fs-lg '>
                            {t('extraction_time')}
                        </motion.span>
                        <motion.div variants={BLOCK_ANIMATIONS_VARIANTS} className='flex alignCenter'>
                            <NumberInput
                                onDecrease={handleDecreaseTime}
                                onIncrease={handleIncreaseTime}
                                value={config.extractionTime}
                                text={t('seconds')}
                            />
                        </motion.div>
                        <motion.span
                            variants={BLOCK_ANIMATIONS_VARIANTS}
                            className='mt4 fs-lg '>
                            {t('purge')}
                        </motion.span>
                        <motion.div
                            variants={BLOCK_ANIMATIONS_VARIANTS}
                            className='flex alignCenter'>
                            <NumberInput
                                onDecrease={handleDecreasePurge}
                                onIncrease={handleIncreasePurge}
                                value={config.purge}
                                text={t('seconds')}
                            />
                        </motion.div>
                        <motion.div variants={BLOCK_ANIMATIONS_VARIANTS}>
                            <Button 
                                className='outlined large mt4' 
                                style={{ width: '13em' }}
                                onClick={() => setIsPreInfusionModalOpen(true)}
                            >
                                {t('pre_infusion')}
                            </Button>
                        </motion.div>
                        <motion.div variants={BLOCK_ANIMATIONS_VARIANTS}>
                            <Button 
                                className='outlined large mt2' 
                                style={{ width: '13em' }}
                                onClick={() => setIsBackflushModalOpen(true)}
                            >
                                {t('backflush')}
                            </Button>
                        </motion.div>

                        {/* <Switch id='preInfusion' label='Activate Pre-Infusion' className='mt5' />
                        <Switch id='backflush' label='Activate Backflush' className='mt3' /> */}
                        <motion.div variants={BLOCK_ANIMATIONS_VARIANTS} className='mt6 flex gap-2 alignCenter'>
                            <Button onClick={handleSaveChanges} className='dialog-action' style={{ width: '8em' }}>
                                {t('confirm')}
                            </Button>
                            {/* <Link to={`/dashboard/home`}> */}
                                <Button
                                    onClick={() => {
                                        changeCurrentPage({ url: '/dashboard/home', params: {} })
                                    }}
                                    className='dialog-action' style={{ width: '8em' }}>
                                    {t('cancel')}
                                </Button>
                            {/* </Link> */}
                        </motion.div>
                    </div>

                </div>
            </motion.div>
            <PreInfusionModal
                isOpen={isPreInfusionModalOpen}
                onClose={() => setIsPreInfusionModalOpen(false)}
                currentConfig={config}
            />
            <MyModal
                open={isBackflushModalOpen}
                onClose={() => setIsBackflushModalOpen(false)}
                modalPaperStyle={{
                    width: '85%',
                    maxWidth: '450px',
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    borderRadius: '15px',
                    padding: '1rem',
                    position: 'relative',
                    overflow: 'hidden',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '1.5rem',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                    boxShadow: '0 4px 30px rgba(0, 0, 0, 0.1)',
                    backdropFilter: 'blur(5px)',
                }}
            >
                <div style={{ width: '100%' }}>
                    <span
                        style={{
                            fontSize: '1.2em',
                            fontFamily: 'Roboto, sans-serif',
                            color: 'white',
                            display: 'block',
                            marginTop: '1.5rem',
                            textAlign: 'center',
                            fontWeight: 600,
                            marginBottom: '2rem',
                            padding: '0 1rem'
                        }}
                    >
                        {t('portafilter_locked')}
                    </span>
                    <div style={{ display: 'flex', width: '100%', gap: 16, marginTop: 32 }}>
                        <button
                            style={{ flex: 1, padding: '0.75em', borderRadius: 8, background: '#b5b5b5', color: '#000', border: 'none', fontSize: '1.1em', fontWeight: 'bold', cursor: 'pointer' }}
                            onClick={() => setIsBackflushModalOpen(false)}
                        >
                            {t('cancel')}
                        </button>
                        <button
                            style={{ flex: 1, padding: '0.75em', borderRadius: 8, background: '#b5b5b5', color: '#000', border: 'none', fontSize: '1.1em', fontWeight: 'bold', cursor: 'pointer' }}
                            onClick={async () => {
                                // Save to backend with backflush: true
                                await saveGHConfig((`gh${_amperId}` as 'gh1' | 'gh2'), {
                                    temperature: Math.round(config.temperature * 10), // Multiply by 10 and round
                                    pre_infusion: {
                                        enabled: config.preInfusionEnabled,
                                        time: config.preInfusionTime
                                    },
                                    extraction_time: config.extractionTime,
                                    volume: config.volume,
                                    purge: config.purge,
                                    pressure: 9.0,
                                    flow: 2.5,
                                    backflush: true
                                });

                                toast.success(t('configuration_saved_successfully'));

                                // Set backflush to false after 4 seconds
                                setTimeout(async () => {
                                    await saveGHConfig((`gh${_amperId}` as 'gh1' | 'gh2'), {
                                        temperature: Math.round(config.temperature * 10), // Multiply by 10 and round
                                        pre_infusion: {
                                            enabled: config.preInfusionEnabled,
                                            time: config.preInfusionTime
                                        },
                                        extraction_time: config.extractionTime,
                                        volume: config.volume,
                                        purge: config.purge,
                                        pressure: 9.0,
                                        flow: 2.5,
                                        backflush: false
                                    });
                                }, 4000);

                                setIsBackflushModalOpen(false);
                            }}
                        >
                            {t('confirm')}
                        </button>
                    </div>
                </div>
            </MyModal>
        </>
    )
};

export const NumberInput = ({ value, onIncrease, onDecrease, text }: {
    value: any;
    onIncrease: () => void;
    onDecrease: () => void;
    text: any
}) => {
    return (
        <div className='flex alignCenter'>
            <HoldableButton className=' py3 px0 outlined'
                onClick={() => {
                    onDecrease()
                    // if (e.detail === 2) {
                    //     console.log("double click")
                    // } else if (e.detail === 3) {
                    //     console.log("triple click")
                    // }
                }}
                longPressThreshold={200}
                onLongPress={() => {
                    onDecrease()
                }}
            >
                <MdArrowDropDown size="4em" />
            </HoldableButton>
            <HoldableButton className='py3 px0 ml2 outlined'
                onClick={() => {
                    onIncrease()
                    // if (e.detail === 2) {
                    //     console.log("double click")
                    // } else if (e.detail === 3) {
                    //     console.log("triple click")
                    // }
                }}
                // longPressOnce
                longPressThreshold={200}
                onLongPress={() => {
                    onIncrease()
                }}
            >
                <MdArrowDropUp size="4em" />
            </HoldableButton>
            <div className='flex column ml4'>
                <span className='font-bold' style={{ lineHeight: 1, fontSize: '4.5em', paddingBottom: '0.1em' }}>
                    {value}
                </span>
                <span className='fs-md'>
                    {text}
                </span>
            </div>
        </div>
    )
}

{/* <div className='flex alignCenter p2 b b1 radius-1'>
            <HoldableButton className=' py3 px4'
                onClick={e => {
                    onDecrease()
                    // if (e.detail === 2) {
                    //     console.log("double click")
                    // } else if (e.detail === 3) {
                    //     console.log("triple click")
                    // }
                }}
                longPressThreshold={200}
                onLongPress={(e, pressDuration) => {
                    onDecrease()
                }}
            >
                <MdRemove size="2em" />
            </HoldableButton>
            <span className='font-bold mx1 textAlign center' style={{ lineHeight: 1, fontSize: '3.5em', minWidth: '3ch', paddingBottom: '0.1em' }}>
                {value}
            </span>
            <HoldableButton className=' py3 px4'
                onClick={e => {
                    onIncrease()
                    // if (e.detail === 2) {
                    //     console.log("double click")
                    // } else if (e.detail === 3) {
                    //     console.log("triple click")
                    // }
                }}
                // longPressOnce
                longPressThreshold={200}
                onLongPress={(e, pressDuration) => {
                    onIncrease()
                }}
            >
                <MdAdd size="2em" />
            </HoldableButton>
        </div> */}
export default GhAmperConfig
