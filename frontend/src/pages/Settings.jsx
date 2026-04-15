import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Save, RotateCcw } from 'lucide-react';
import Sidebar from '@/components/dashboard/Sidebar';
import DashboardHeader from '@/components/dashboard/DashboardHeader';

const DEFAULT_SETTINGS = {
    inference: { threshold: 0.5, overlayEnabled: true },
    mosdac: { datasetId: '3RIMG_L1C_ASIA_MER', hoursBack: 1, autoDownload: false },
    output: { directory: './outputs', overwritePrevious: true },
    system: { device: 'auto' },
};

function loadSettings() {
    try {
        const s = localStorage.getItem('cloudsense_settings');
        if (s) return { ...DEFAULT_SETTINGS, ...JSON.parse(s) };
    } catch { /* ignore */ }
    return DEFAULT_SETTINGS;
}

export default function Settings() {
    const [settings, setSettings] = useState(loadSettings);
    const [saved, setSaved] = useState(false);

    const update = (cat, key, val) => {
        setSettings(p => ({ ...p, [cat]: { ...p[cat], [key]: val } }));
        setSaved(false);
    };

    const handleSave = () => {
        localStorage.setItem('cloudsense_settings', JSON.stringify(settings));
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
    };

    const handleReset = () => {
        setSettings(DEFAULT_SETTINGS);
        localStorage.setItem('cloudsense_settings', JSON.stringify(DEFAULT_SETTINGS));
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
    };

    const Toggle = ({ value, onChange }) => (
        <button
            onClick={() => onChange(!value)}
            className={`w-10 h-5 rounded-full transition-colors flex-shrink-0 relative ${value ? 'bg-cyan-500' : 'bg-slate-600'}`}
        >
            <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-all ${value ? 'left-5' : 'left-0.5'}`} />
        </button>
    );

    const Row = ({ label, desc, children }) => (
        <div className="flex items-center justify-between py-3 border-b border-slate-800 last:border-0">
            <div>
                <p className="text-sm text-slate-200">{label}</p>
                {desc && <p className="text-xs text-slate-500 mt-0.5">{desc}</p>}
            </div>
            <div className="ml-4 flex-shrink-0">{children}</div>
        </div>
    );

    const Section = ({ title, children }) => (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
            <p className="text-xs font-semibold text-cyan-400 uppercase tracking-wider mb-1">{title}</p>
            {children}
        </div>
    );

    return (
        <div className="flex h-screen bg-[#010816]">
            <Sidebar />
            <div className="flex-1 flex flex-col overflow-hidden">
                <DashboardHeader />
                <div className="flex-1 overflow-auto p-5">
                    <div className="flex justify-end gap-2 mb-5">
                        <Button onClick={handleReset} variant="outline" className="border-slate-700 text-slate-300 hover:bg-slate-800 h-9 text-sm">
                            <RotateCcw className="w-3.5 h-3.5 mr-2" />Reset
                        </Button>
                        <Button onClick={handleSave} className="bg-cyan-600 hover:bg-cyan-700 h-9 text-sm">
                            <Save className="w-3.5 h-3.5 mr-2" />{saved ? 'Saved!' : 'Save'}
                        </Button>
                    </div>

                    <div className="space-y-4 max-w-2xl">
                        <Section title="Inference">
                            <Row label="Probability Threshold" desc="Minimum confidence for TCC detection">
                                <div className="flex items-center gap-3">
                                    <input type="range" min="0.1" max="0.9" step="0.05"
                                        value={settings.inference.threshold}
                                        onChange={(e) => update('inference', 'threshold', parseFloat(e.target.value))}
                                        className="w-28 accent-cyan-500"
                                    />
                                    <span className="text-xs text-slate-300 w-10 text-center bg-slate-800 px-2 py-1 rounded">
                                        {settings.inference.threshold.toFixed(2)}
                                    </span>
                                </div>
                            </Row>
                            <Row label="Overlay Mask" desc="Show TCC mask on satellite image">
                                <Toggle value={settings.inference.overlayEnabled} onChange={(v) => update('inference', 'overlayEnabled', v)} />
                            </Row>
                        </Section>

                        <Section title="MOSDAC">
                            <Row label="Dataset ID" desc="INSAT-3D product identifier">
                                <select value={settings.mosdac.datasetId} onChange={(e) => update('mosdac', 'datasetId', e.target.value)}
                                    className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-white">
                                    <option value="3RIMG_L1C_ASIA_MER">3RIMG_L1C_ASIA_MER</option>
                                    <option value="3RIMG_L1C_INDIA">3RIMG_L1C_INDIA</option>
                                </select>
                            </Row>
                            <Row label="Default Hours Back" desc="Time range for data download">
                                <input type="number" min="0.5" max="12" step="0.5"
                                    value={settings.mosdac.hoursBack}
                                    onChange={(e) => update('mosdac', 'hoursBack', parseFloat(e.target.value))}
                                    className="w-20 bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-white text-center"
                                />
                            </Row>
                            <Row label="Auto-Download" desc="Fetch latest data on page load">
                                <Toggle value={settings.mosdac.autoDownload} onChange={(v) => update('mosdac', 'autoDownload', v)} />
                            </Row>
                        </Section>

                        <Section title="Output">
                            <Row label="Output Directory" desc="Where to save inference results">
                                <input type="text" value={settings.output.directory}
                                    onChange={(e) => update('output', 'directory', e.target.value)}
                                    className="w-40 bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-white"
                                />
                            </Row>
                            <Row label="Overwrite Previous" desc="Replace existing output files">
                                <Toggle value={settings.output.overwritePrevious} onChange={(v) => update('output', 'overwritePrevious', v)} />
                            </Row>
                        </Section>

                        <Section title="System">
                            <Row label="Compute Device" desc="Hardware for model inference">
                                <select value={settings.system.device} onChange={(e) => update('system', 'device', e.target.value)}
                                    className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-white">
                                    <option value="auto">Auto (Recommended)</option>
                                    <option value="cpu">CPU Only</option>
                                    <option value="gpu">GPU (MPS/CUDA)</option>
                                </select>
                            </Row>
                        </Section>
                    </div>
                </div>
            </div>
        </div>
    );
}
