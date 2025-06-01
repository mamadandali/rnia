import { useState, useCallback } from 'react';
import { toast } from 'react-hot-toast';
import { useTranslation } from 'react-i18next';
import axios from 'axios';

interface PreInfusionConfig {
  enabled: boolean;
  time: number;
}

export interface GHConfig {
  temperature: number;
  extraction_volume: number;
  extraction_time: number;
  pre_infusion: PreInfusionConfig;
  purge: number;
  backflush: boolean;
  volume?: number;
}

interface MainConfig {
  temperature: number;
  pressure: number;
}

interface ConfigDataHook {
  ghConfig: { gh1: GHConfig; gh2: GHConfig; } | null;
  mainConfig: MainConfig | null;
  fetchGHConfig: () => Promise<void>;
  fetchMainConfig: () => Promise<void>;
  saveGHConfig: (ghId: 'gh1' | 'gh2', config: any) => Promise<void>;
  saveMainConfig: (config: any) => Promise<void>;
  setMainAmpereConfig: (config: { temperature: number }) => Promise<void>;
  updatePreInfusion: (ghId: 'gh1' | 'gh2', preInfusion: PreInfusionConfig) => Promise<void>;
  updateBackflush: (ghId: 'gh1' | 'gh2', enabled: boolean) => Promise<void>;
  sendStatusUpdate: (target: string, status: boolean) => Promise<void>;
  saveMenuSettings: (settings: any) => Promise<void>;
  setBoilerDischarge: (discharge: 'none' | 'drain_refill' | 'drain_shutdown') => Promise<void>;
  error: string | null;
}

export const useConfigData = (): ConfigDataHook => {
  const [ghConfig, setGHConfig] = useState<{ gh1: GHConfig; gh2: GHConfig; } | null>(null);
  const [mainConfig, setMainConfig] = useState<MainConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { t } = useTranslation();

  const fetchGHConfig = useCallback(async () => {
    try {
      const response = await axios.get('http://localhost:8000/getghconfig');
      setGHConfig(response.data);
      setError(null);
    } catch (error) {
      console.error('Error fetching GH config:', error);
      setError(t('error_fetching_config'));
      toast.error(t('error_fetching_config'));
    }
  }, [t]);

  const fetchMainConfig = useCallback(async () => {
    try {
      const response = await axios.get('http://localhost:8000/getmainconfig');
      setMainConfig(response.data);
      setError(null);
    } catch (error) {
      console.error('Error fetching main config:', error);
      setError(t('error_fetching_config'));
      toast.error(t('error_fetching_config'));
    }
  }, [t]);

  const saveGHConfig = useCallback(async (ghId: 'gh1' | 'gh2', config: any) => {
    try {
      await axios.post('http://localhost:8000/saveghconfig', {
        gh_id: ghId,
        config: config
      });
      await fetchGHConfig();  // Refresh config after save
      setError(null);
    } catch (error) {
      console.error('Error saving GH config:', error);
      setError(t('error_saving_config'));
      toast.error(t('error_saving_config'));
    }
  }, [fetchGHConfig, t]);

  const setMainAmpereConfig = useCallback(async (config: { temperature: number }) => {
    try {
      await axios.post('http://localhost:8000/setmainconfig', {
        config: config
      });
      await fetchMainConfig();  // Refresh config after save
      setError(null);
    } catch (error) {
      console.error('Error setting main ampere config:', error);
      setError(t('error_saving_config'));
      toast.error(t('error_saving_config'));
    }
  }, [fetchMainConfig, t]);

  const saveMainConfig = useCallback(async (config: any) => {
    if (config.temperature !== undefined) {
      return setMainAmpereConfig({ temperature: config.temperature });
    }
    
    try {
      await axios.post('http://localhost:8000/savemainconfig', {
        config: config
      });
      await fetchMainConfig();  // Refresh config after save
      setError(null);
    } catch (error) {
      console.error('Error saving main config:', error);
      setError(t('error_saving_config'));
      toast.error(t('error_saving_config'));
    }
  }, [fetchMainConfig, setMainAmpereConfig, t]);

  const updatePreInfusion = useCallback(async (ghId: 'gh1' | 'gh2', preInfusion: PreInfusionConfig) => {
    try {
      await axios.post('http://localhost:8000/updatepreinfusion', {
        gh_id: ghId,
        pre_infusion: preInfusion
      });
      await fetchGHConfig();  // Refresh config after update
      setError(null);
    } catch (error) {
      console.error('Error updating pre-infusion:', error);
      setError(t('error_saving_config'));
      toast.error(t('error_saving_config'));
    }
  }, [fetchGHConfig, t]);

  const updateBackflush = useCallback(async (ghId: 'gh1' | 'gh2', enabled: boolean) => {
    try {
      await axios.post('http://localhost:8000/updatebackflush', {
        gh_id: ghId,
        backflush: enabled
      });
      await fetchGHConfig();  // Refresh config after update
      setError(null);
    } catch (error) {
      console.error('Error updating backflush:', error);
      setError(t('error_saving_config'));
      toast.error(t('error_saving_config'));
    }
  }, [fetchGHConfig, t]);

  const sendStatusUpdate = useCallback(async (target: string, status: boolean) => {
    try {
      await axios.post('http://localhost:8000/setstatusupdate', {
        target,
        status
      });
    } catch (error) {
      console.error('Error sending status update:', error);
      toast.error('Error updating status');
    }
  }, []);

  const setBoilerDischarge = useCallback(async (discharge: 'none' | 'drain_refill' | 'drain_shutdown') => {
    try {
      await axios.post('http://localhost:8000/setboilerdischarge', { discharge });
    } catch (error) {
      console.error('Error setting boiler discharge:', error);
      toast.error('Error setting boiler discharge');
    }
  }, []);

  const saveMenuSettings = useCallback(async (settings: any) => {
    const { boiler_discharge, ...rest } = settings;
    try {
      await saveMainConfig(rest);
    } catch (error) {
      console.error('Error saving menu settings:', error);
      toast.error('Error saving menu settings');
    }
  }, [saveMainConfig]);

  return {
    ghConfig,
    mainConfig,
    fetchGHConfig,
    fetchMainConfig,
    saveGHConfig,
    saveMainConfig,
    setMainAmpereConfig,
    updatePreInfusion,
    updateBackflush,
    sendStatusUpdate,
    saveMenuSettings,
    setBoilerDischarge,
    error
  };
}; 
