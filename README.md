import { useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useConfigData } from '~/hooks/useConfigData';
import GhAmperConfig from "./ghAmperConfig";
// import MainAmperConfig from "./mainAmperConfig";

const AmperConfig = () => {
    const { amperId } = useParams<{ amperId: string }>();
    const { ghConfig, fetchGHConfig, saveGHConfig, error } = useConfigData();
    
    useEffect(() => {
        fetchGHConfig();
    }, [fetchGHConfig]);

    const handleSave = async (config: any) => {
        const ghId = amperId === '2' ? 'gh2' : 'gh1';
        await saveGHConfig(ghId, {
            temperature: config.temperature || 92.5,
            pre_infusion: {
                enabled: config.preInfusionEnabled || false,
                time: config.preInfusionTime || 0
            },
            extraction_time: config.extractionTime || 20,
            volume: config.volume || 55,
            pressure: config.pressure || 9.0,
            flow: config.flow || 2.5,
            backflush: config.backflush || false,
            purge: config.purge || 0
        });
    };

    // Get current config for this amper
    const currentConfig = ghConfig ? ghConfig[`gh${amperId}` as 'gh1' | 'gh2'] : null;

    if (error) {
        console.error('Configuration error:', error);
    }

    return (
        <div>
            <GhAmperConfig 
                currentConfig={currentConfig}
            />
        </div>
    );
};

export default AmperConfig
