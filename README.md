import React from 'react'
import { MdArrowDropDown, MdArrowDropUp } from 'react-icons/md';
import { Button } from '~/components/KIT';
import HoldableButton from '~/components/common/holdableButton';
import { motion } from 'framer-motion';
import { ROUTE_VARIANTS, BLOCK_ANIMATIONS_VARIANTS } from '~/store/animationVars';
import { useGeneralStore } from '~/store/general';
import { MACHINE_KEY } from '~/store/consts';
import { toast } from 'react-hot-toast';
import NewMainAmper from '~/components/common/newMainAmper';
import { useTranslation } from 'react-i18next';
import { NumberInput } from '../amperConfig/ghAmperConfig';
import { useConfigData } from '~/hooks/useConfigData';

const MainTemperatureConfig = () => {
    const { t } = useTranslation();
    const { [MACHINE_KEY]: machine, changeAmperConfig, changeCurrentPage } = useGeneralStore();
    const { setMainAmpereConfig, mainConfig, fetchMainConfig } = useConfigData();
    
    const [temperature, setTemperature] = React.useState((mainConfig?.temperature ?? 111) / 10);

    React.useEffect(() => {
        fetchMainConfig();
    }, []);

    React.useEffect(() => {
        if (mainConfig?.temperature !== undefined) {
            setTemperature(mainConfig.temperature / 10);
        }
    }, [mainConfig?.temperature]);

    function handleIncreaseTemp() {
        if (temperature >= 200) return;
        setTemperature((prev: number) => prev + 0.5);
    }
    function handleDecreaseTemp() {
        if (temperature <= 0) return;
        setTemperature((prev: number) => prev - 0.5);
    }

    async function handleSaveChanges() {
        try {
            await setMainAmpereConfig({ temperature: Math.round(temperature * 10) });
            changeAmperConfig('mainTank', 'boilerTemperator', temperature * 10);
            toast.success(t('configuration_saved_successfully'));
            changeCurrentPage({ url: '/dashboard/home', params: {} });
        } catch (error) {
            console.error('Error saving temperature config:', error);
            toast.error(t('error_saving_configuration'));
        }
    }
    
    return (
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
                    <NewMainAmper
                        titleSize='1.2em'
                        valueSize='2.5em'
                        title={t('steam_boiler_temperature')}
                        progressWidth={24}
                        axisLineWidth={24}
                        value={temperature}
                        secondTitle={t('degrees_celsius')}
                        secondTitleSize='1em'
                    />
                </div>
                <div 
                    className='span-12 flex column pr24 pb8' 
                    style={{ 
                        direction: 'rtl', 
                        maxHeight: '100%', 
                        paddingTop: '-20',
                        overflowY: 'auto'
                    }}
                >
                    <motion.span
                        variants={BLOCK_ANIMATIONS_VARIANTS}
                        className='mt4 fs-lg' 
                        style={{
                            fontSize: '1.8em',
                            fontFamily: 'Roboto, sans-serif',
                            color: 'white',
                            display: 'block',
                            marginTop: '1.5rem',
                        }}
                        >
                        {t('steam_boiler_temperature')}
                    </motion.span>
                    <motion.div
                        variants={BLOCK_ANIMATIONS_VARIANTS}
                        className='flex alignCenter'>
                        <NumberInput
                            onDecrease={handleDecreaseTemp}
                            onIncrease={handleIncreaseTemp}
                            value={temperature}
                            text={t('degrees_celsius')}
                        />
                    </motion.div>
                    
                    <motion.div 
                        variants={BLOCK_ANIMATIONS_VARIANTS} 
                        className='mt6 flex gap-2 alignCenter'
                        >
                        <Button
                            onClick={() => {
                                changeCurrentPage({ url: '/dashboard/home', params: {} });
                            }}
                            className='dialog-action'
                            style={{
                                width: '8em',
                            }}
                            >
                            {t('cancel')}
                        </Button>
                        <Button 
                            onClick={handleSaveChanges} 
                            className='dialog-action'
                            style={{
                                width: '8em',
                            }}
                            >
                            {t('confirm')}
                        </Button>
                    </motion.div>
                </div>
            </div>
        </motion.div>
    );
};

export default MainTemperatureConfig; 
