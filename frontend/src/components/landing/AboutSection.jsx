import { Satellite, Brain, BarChart3, FileDown, Shield, Zap } from 'lucide-react';

const AboutSection = () => {
    return (
        <section className="py-20 bg-[#080c16]">
            <div className="max-w-7xl mx-auto px-6">

                {/* Section header */}
                <div className="text-center mb-14">
                    <span className="text-xs font-semibold text-cyan-400 uppercase tracking-widest">About the Project</span>
                    <h2 className="text-3xl md:text-4xl font-bold text-white mt-2 mb-4">
                        What is CloudSense?
                    </h2>
                    <p className="text-slate-400 max-w-2xl mx-auto text-lg">
                        A research-grade platform for automated detection and classification of
                        Tropical Cloud Clusters from INSAT-3D/3DR satellite imagery.
                    </p>
                </div>

                {/* Two-column: description + pipeline */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 mb-16 items-center">
                    <div>
                        <h3 className="text-xl font-semibold text-white mb-4">The Problem</h3>
                        <p className="text-slate-400 leading-relaxed mb-4">
                            Tropical Cloud Clusters (TCCs) are large convective systems that can develop into
                            tropical cyclones. Manual monitoring of INSAT-3DR imagery — updated every 30 minutes —
                            is time-consuming and inconsistent.
                        </p>
                        <p className="text-slate-400 leading-relaxed mb-4">
                            CloudSense automates this process using a <span className="text-cyan-400 font-medium">U-Net segmentation model</span> trained
                            on real INSAT-3DR data, combined with physics-based brightness temperature analysis
                            to classify detections by severity.
                        </p>
                        <p className="text-slate-400 leading-relaxed">
                            The system was trained on <span className="text-white font-medium">1,897 satellite images</span> from
                            Cyclone Michaung (Nov–Dec 2023), achieving a validation IoU of{' '}
                            <span className="text-cyan-400 font-medium">0.89</span>.
                        </p>
                    </div>

                    {/* Pipeline steps */}
                    <div className="space-y-3">
                        {[
                            { icon: Satellite, step: '01', title: 'Data Ingestion', desc: 'INSAT-3DR H5 files via MOSDAC API or manual upload' },
                            { icon: Brain, step: '02', title: 'U-Net Inference', desc: 'MobileNetV2 encoder segments cloud regions at 512×512' },
                            { icon: Shield, step: '03', title: 'BT Thresholding', desc: 'Physics-based filter: cloud tops < 218K = TCC candidate' },
                            { icon: BarChart3, step: '04', title: 'Classification', desc: 'Scoring system: Confirmed / Probable / Possible / Cloud Cluster' },
                            { icon: FileDown, step: '05', title: 'Export', desc: 'CF-compliant NetCDF, PNG overlay, binary mask (.npy)' },
                        ].map((s, i) => (
                            <div key={i} className="flex items-start gap-4 p-4 bg-slate-900/60 border border-slate-800 rounded-xl">
                                <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-cyan-500/10 flex items-center justify-center">
                                    <s.icon className="w-4 h-4 text-cyan-400" />
                                </div>
                                <div>
                                    <div className="flex items-center gap-2">
                                        <span className="text-xs text-cyan-600 font-mono">{s.step}</span>
                                        <span className="text-sm font-semibold text-white">{s.title}</span>
                                    </div>
                                    <p className="text-xs text-slate-500 mt-0.5">{s.desc}</p>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Classification guide */}
                <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-8">
                    <h3 className="text-lg font-semibold text-white mb-6 text-center">TCC Classification Criteria</h3>
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                        {[
                            { label: 'Confirmed TCC', color: 'bg-red-500', border: 'border-red-500/30', desc: 'Min BT < 200K, large area, dominant cold core. High confidence deep convection.' },
                            { label: 'Probable TCC', color: 'bg-amber-500', border: 'border-amber-500/30', desc: 'Min BT < 210K, moderate area. Likely convective system requiring monitoring.' },
                            { label: 'Possible TCC', color: 'bg-cyan-500', border: 'border-cyan-500/30', desc: 'Min BT < 235K, some cold core. Developing system, watch for intensification.' },
                            { label: 'Cloud Cluster', color: 'bg-slate-500', border: 'border-slate-500/30', desc: 'Warm or small cluster. Not yet meeting TCC criteria but tracked for development.' },
                        ].map((c, i) => (
                            <div key={i} className={`p-4 rounded-xl border ${c.border} bg-slate-900`}>
                                <div className="flex items-center gap-2 mb-2">
                                    <div className={`w-3 h-3 rounded-full ${c.color}`} />
                                    <span className="text-sm font-semibold text-white">{c.label}</span>
                                </div>
                                <p className="text-xs text-slate-500 leading-relaxed">{c.desc}</p>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Stats row */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mt-10">
                    {[
                        { value: '0.89', label: 'Validation IoU', sub: 'U-Net model accuracy' },
                        { value: '1,897', label: 'Training Samples', sub: 'H5 + IR1 images' },
                        { value: '30 min', label: 'Update Interval', sub: 'INSAT-3DR cadence' },
                        { value: '4 km', label: 'Spatial Resolution', sub: 'Per pixel' },
                    ].map((s, i) => (
                        <div key={i} className="text-center p-5 bg-slate-900/60 border border-slate-800 rounded-xl">
                            <p className="text-2xl font-bold text-cyan-400">{s.value}</p>
                            <p className="text-sm font-medium text-white mt-1">{s.label}</p>
                            <p className="text-xs text-slate-500 mt-0.5">{s.sub}</p>
                        </div>
                    ))}
                </div>

            </div>
        </section>
    );
};

export default AboutSection;
