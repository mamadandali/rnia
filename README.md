import React from 'react';
import { motion } from 'framer-motion';
import { BLOCK_ANIMATIONS_VARIANTS } from '~/store/animationVars';
import { useTranslation } from 'react-i18next';
import { Modal } from '~/components/KIT';
import { Button } from '~/components/KIT';
import { useGeneralStore } from '~/store/general';
import { MACHINE_KEY } from '~/store/consts';
import { toast } from 'react-hot-toast';
import HoldableButton from '~/components/common/holdableButton';
import { MdArrowDropDown, MdArrowDropUp } from 'react-icons/md';
import { useConfigData } from '~/hooks/useConfigData';

interface PreInfusionModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSave?: (enabled: boolean, time: number) => void;
    currentConfig: any;
}

const getCustomCheckboxWrapperStyle = (language: string): React.CSSProperties => ({
    position: 'relative',
    display: 'inline-block',
    width: 28,
    height: 28,
    verticalAlign: 'middle',
    marginLeft: language === 'fa' || language === 'ar' ? 16 : 0,
    marginRight: language === 'fa' || language === 'ar' ? 0 : 16,
});

const customCheckboxBox = (checked: boolean): React.CSSProperties => ({
    width: 28,
    height: 28,
    background: checked ? '#4F5BD5' : '#222',
    border: `2.5px solid ${checked ? '#4F5BD5' : '#666'}`,
    borderRadius: 6,
    boxSizing: 'border-box',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    transition: 'background 0.15s, border-color 0.15s'
});

const PreInfusionModal: React.FC<PreInfusionModalProps> = ({ isOpen, onClose, onSave, currentConfig }) => {
    const { t, i18n } = useTranslation();
    const { [MACHINE_KEY]: machine, changeAmperConfig, CURRENT_PAGE } = useGeneralStore();
    const { saveGHConfig } = useConfigData();
    const _amperId = CURRENT_PAGE.params.amperId || '1';
    const _selectedGh = _amperId === '1' ? machine.GH1 : machine.GH2;

    // Helper function to get pre-infusion data
    const getPreInfusionData = (config: any) => {
        console.log('PreInfusionModal getPreInfusionData input:', config);
        if (config?.pre_infusion) {
            const result = {
                enabled: config.pre_infusion.enabled || false,
                time: config.pre_infusion.time || 0
            };
            console.log('PreInfusionModal getPreInfusionData returning dict format:', result);
            return result;
        }
        // Fallback to legacy format
        const legacyPreInfusion = config?.preInfusion || _selectedGh.config.preInfusion || 0;
        const result = {
            enabled: legacyPreInfusion > 0,
            time: legacyPreInfusion
        };
        console.log('PreInfusionModal getPreInfusionData returning legacy format:', result);
        return result;
    };

    const [preInfusionTime, setPreInfusionTime] = React.useState(() => {
        const preInfusion = getPreInfusionData(currentConfig);
        console.log('PreInfusionModal initializing preInfusionTime with:', preInfusion);
        return preInfusion.time;
    });

    const [preInfusionEnabled, setPreInfusionEnabled] = React.useState(() => {
        const preInfusion = getPreInfusionData(currentConfig);
        console.log('PreInfusionModal initializing preInfusionEnabled with:', preInfusion);
        return preInfusion.enabled;
    });

    // Update state when currentConfig changes
    React.useEffect(() => {
        if (currentConfig) {
            console.log('PreInfusionModal currentConfig changed:', currentConfig);
            const preInfusion = getPreInfusionData(currentConfig);
            console.log('PreInfusionModal updating state with:', preInfusion);
            setPreInfusionTime(preInfusion.time);
            setPreInfusionEnabled(preInfusion.enabled);
        }
    }, [currentConfig]);

    const handleIncreaseTime = () => {
        if (preInfusionTime >= 30) return;
        setPreInfusionTime((prev: number) => prev + 1);
    };

    const handleDecreaseTime = () => {
        if (preInfusionTime <= 0) return;
        setPreInfusionTime((prev: number) => prev - 1);
    };

    const handleSaveChanges = async () => {
        console.log('PreInfusionModal saving changes:', { enabled: preInfusionEnabled, time: preInfusionTime });
        // Build the config object using the passed currentConfig and the modal's state
        const ghId = `gh${_amperId}` as 'gh1' | 'gh2';
        const saveData = {
            temperature: Math.round(currentConfig?.temperature * 10),
            pre_infusion: {
                enabled: preInfusionEnabled,
                time: preInfusionTime
            },
            extraction_time: currentConfig?.extraction_time,
            volume: currentConfig?.volume,
            pressure: 9.0,
            flow: 2.5,
            backflush: currentConfig?.backflush || false,
            purge: currentConfig?.purge || 0
        };
        console.log('PreInfusionModal saving to backend with data:', saveData);
        await saveGHConfig(ghId, saveData);

        toast.success(t('configuration_saved_successfully'));
        onClose();
    };

    const isRTL = i18n.language === 'fa';

    return (
        <Modal
            open={isOpen}
            onClose={onClose}
            title={t('pre_infusion')}
            className="pre-infusion-modal"
            modalPaperStyle={{
                width: '80%',
                maxWidth: '400px',
                height: 'auto',
                maxHeight: '80vh',
                backgroundColor: 'rgba(0, 0, 0, 0.8)',
                borderRadius: '15px',
                padding: '1rem',
                position: 'relative',
                overflow: 'hidden',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '1rem',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                boxShadow: '0 4px 30px rgba(0, 0, 0, 0.1)',
                backdropFilter: 'blur(5px)',
            }}
            style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
            }}
        >
            <motion.div
                variants={BLOCK_ANIMATIONS_VARIANTS}
                className="flex column alignCenter"
                style={{
                    width: '100%',
                    gap: '1rem',
                    position: 'relative',
                    zIndex: 2,
                }}
            >
                <motion.span
                    variants={BLOCK_ANIMATIONS_VARIANTS}
                    className="fs-lg"
                    style={{
                        fontSize: '1.8em',
                        fontFamily: 'Roboto, sans-serif',
                        color: 'white',
                        display: 'block',
                        marginTop: '1.5rem',
                        textAlign: 'center',
                        position: 'relative',
                        zIndex: 2,
                    }}
                >
                    {t('pre_infusion')}
                </motion.span>
                <div className='flex row justifyCenter alignCenter' style={{ gap: 12, marginBottom: 16 }}>
                    <div
                        className='flex alignCenter justifyCenter'
                        style={{
                            border: preInfusionEnabled ? '3px solid #666' : '3px solid #4F5BD5',
                            borderColor: preInfusionEnabled ? '#666' : '#4F5BD5',
                            background: 'rgba(0,0,0,0.2)',
                            cursor: 'pointer',
                            minWidth: 100,
                            minHeight: 50,
                            padding: '0 12px',
                            transition: 'border-color 0.2s',
                            boxSizing: 'border-box',
                            borderRadius: 12,
                            alignItems: 'center',
                            justifyContent: 'center',
                            display: 'flex',
                            fontWeight: 400,
                            fontSize: '1.1em'
                        }}
                        onClick={() => setPreInfusionEnabled(false)}
                    >
                        <label style={getCustomCheckboxWrapperStyle(i18n.language)}>
                            <input
                                type="checkbox"
                                checked={!preInfusionEnabled}
                                readOnly
                                tabIndex={-1}
                                style={{
                                    opacity: 0,
                                    width: 28,
                                    height: 28,
                                    margin: 0,
                                    position: 'absolute',
                                    left: 0,
                                    top: 0,
                                    cursor: 'pointer'
                                }}
                            />
                            <span style={customCheckboxBox(!preInfusionEnabled)}>
                                {!preInfusionEnabled && (
                                    <svg width="18" height="18" viewBox="0 0 18 18">
                                        <polyline
                                            points="4,10 8,14 14,6"
                                            style={{
                                                fill: 'none',
                                                stroke: '#fff',
                                                strokeWidth: 2.5,
                                                strokeLinecap: 'round',
                                                strokeLinejoin: 'round',
                                                strokeDasharray: 16,
                                                strokeDashoffset: 0,
                                                animation: 'checkmark-draw 0.45s cubic-bezier(0.65, 0, 0.45, 1) forwards'
                                            }}
                                        />
                                    </svg>
                                )}
                            </span>
                        </label>
                        <span style={{ color: '#fff', fontWeight: 400 }}>
                            {t('off')}
                        </span>
                    </div>
                    <div
                        className='flex alignCenter justifyCenter'
                        style={{
                            border: preInfusionEnabled ? '3px solid #4F5BD5' : '3px solid #666',
                            borderColor: preInfusionEnabled ? '#4F5BD5' : '#666',
                            background: 'rgba(0,0,0,0.2)',
                            cursor: 'pointer',
                            minWidth: 100,
                            minHeight: 50,
                            padding: '0 12px',
                            transition: 'border-color 0.2s',
                            boxSizing: 'border-box',
                            borderRadius: 12,
                            alignItems: 'center',
                            justifyContent: 'center',
                            display: 'flex',
                            fontWeight: 400,
                            fontSize: '1.1em'
                        }}
                        onClick={() => setPreInfusionEnabled(true)}
                    >
                        <label style={getCustomCheckboxWrapperStyle(i18n.language)}>
                            <input
                                type="checkbox"
                                checked={preInfusionEnabled}
                                readOnly
                                tabIndex={-1}
                                style={{
                                    opacity: 0,
                                    width: 28,
                                    height: 28,
                                    margin: 0,
                                    position: 'absolute',
                                    left: 0,
                                    top: 0,
                                    cursor: 'pointer'
                                }}
                            />
                            <span style={customCheckboxBox(preInfusionEnabled)}>
                                {preInfusionEnabled && (
                                    <svg width="18" height="18" viewBox="0 0 18 18">
                                        <polyline
                                            points="4,10 8,14 14,6"
                                            style={{
                                                fill: 'none',
                                                stroke: '#fff',
                                                strokeWidth: 2.5,
                                                strokeLinecap: 'round',
                                                strokeLinejoin: 'round',
                                                strokeDasharray: 16,
                                                strokeDashoffset: 0,
                                                animation: 'checkmark-draw 0.45s cubic-bezier(0.65, 0, 0.45, 1) forwards'
                                            }}
                                        />
                                    </svg>
                                )}
                            </span>
                        </label>
                        <span style={{ color: '#fff', fontWeight: 400 }}>
                            {t('on')}
                        </span>
                    </div>
                </div>

                <motion.div
                    variants={BLOCK_ANIMATIONS_VARIANTS}
                    className="flex alignCenter"
                    style={{
                        width: '100%',
                        justifyContent: 'center',
                        gap: '2rem',
                        position: 'relative',
                        zIndex: 2,
                        direction: isRTL ? 'rtl' : 'ltr',
                    }}
                >
                    <div className='flex alignCenter' style={{ gap: '2rem' }}>
                        <div className='flex column' style={{ 
                            marginRight: isRTL ? '3rem' : 0, 
                            marginLeft: isRTL ? 0 : '3rem' 
                        }}>
                            <span className='font-bold' style={{ lineHeight: 1, fontSize: '4.5em', paddingBottom: '0.1em' }}>
                                {preInfusionTime}
                            </span>
                            <span className='fs-md'>
                                {t('seconds')}
                            </span>
                        </div>
                        <div style={{ display: 'flex', gap: '1rem' }}>
                            <HoldableButton 
                                className='py3 px0 outlined'
                                onClick={handleDecreaseTime}
                                longPressThreshold={200}
                                onLongPress={handleDecreaseTime}
                            >
                                <MdArrowDropDown size="4em" />
                            </HoldableButton>
                            <HoldableButton 
                                className='py3 px0 outlined'
                                onClick={handleIncreaseTime}
                                longPressThreshold={200}
                                onLongPress={handleIncreaseTime}
                            >
                                <MdArrowDropUp size="4em" />
                            </HoldableButton>
                        </div>
                    </div>
                </motion.div>

                <motion.div
                    variants={BLOCK_ANIMATIONS_VARIANTS}
                    className="mt6 flex gap-2 alignCenter"
                    style={{
                        width: '100%',
                        justifyContent: 'center',
                        gap: '1rem',
                        marginTop: '2rem',
                        position: 'relative',
                        zIndex: 2,
                    }}
                >
                    <Button
                        onClick={onClose}
                        className="dialog-action"
                        style={{
                            width: '8em',
                        }}
                    >
                        {t('cancel')}
                    </Button>
                    <Button
                        onClick={handleSaveChanges}
                        className="dialog-action"
                        style={{
                            width: '8em',
                        }}
                    >
                        {t('confirm')}
                    </Button>
                </motion.div>
            </motion.div>
        </Modal>
    );
};

export default PreInfusionModal; 
