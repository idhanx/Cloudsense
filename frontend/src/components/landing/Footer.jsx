import { Satellite, Github, ExternalLink, Mail, Shield, Zap, Globe } from 'lucide-react';
import { Link } from 'react-router-dom';

const Footer = () => {
  return (
    <footer className="bg-[#060a14] border-t border-slate-800 text-slate-300">
      <div className="max-w-7xl mx-auto px-6 py-14">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-10 mb-10">

          {/* Brand */}
          <div className="md:col-span-2">
            <div className="flex items-center gap-2 mb-4">
              <div className="p-1.5 rounded-lg bg-cyan-500/10">
                <Satellite className="h-5 w-5 text-cyan-400" />
              </div>
              <span className="text-xl font-bold text-white">CloudSense</span>
            </div>
            <p className="text-sm text-slate-400 leading-relaxed mb-5 max-w-sm">
              AI-powered Tropical Cloud Cluster detection using INSAT-3D/3DR satellite imagery,
              U-Net deep learning, and physics-based brightness temperature analysis.
            </p>
            <div className="flex gap-3">
              <a href="https://github.com" target="_blank" rel="noopener noreferrer"
                className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition-colors">
                <Github className="w-4 h-4" />
              </a>
              <a href="https://mosdac.gov.in" target="_blank" rel="noopener noreferrer"
                className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition-colors">
                <Globe className="w-4 h-4" />
              </a>
            </div>
          </div>

          {/* Platform */}
          <div>
            <h4 className="text-xs font-semibold text-white uppercase tracking-wider mb-4">Platform</h4>
            <ul className="space-y-2.5 text-sm text-slate-400">
              <li><Link to="/dashboard" className="hover:text-cyan-400 transition-colors">Dashboard</Link></li>
              <li><Link to="/dashboard/upload" className="hover:text-cyan-400 transition-colors">Data Upload</Link></li>
              <li><Link to="/analysis" className="hover:text-cyan-400 transition-colors">Analysis</Link></li>
              <li><Link to="/exports" className="hover:text-cyan-400 transition-colors">Exports</Link></li>
              <li><Link to="/settings" className="hover:text-cyan-400 transition-colors">Settings</Link></li>
            </ul>
          </div>

          {/* Tech & Data */}
          <div>
            <h4 className="text-xs font-semibold text-white uppercase tracking-wider mb-4">Data Sources</h4>
            <ul className="space-y-2.5 text-sm text-slate-400">
              <li>
                <a href="https://mosdac.gov.in" target="_blank" rel="noopener noreferrer"
                  className="hover:text-cyan-400 transition-colors flex items-center gap-1">
                  MOSDAC <ExternalLink className="w-3 h-3" />
                </a>
              </li>
              <li className="text-slate-500">INSAT-3D / 3DR</li>
              <li className="text-slate-500">IR Brightness Temp</li>
              <li className="text-slate-500">30-min intervals</li>
            </ul>

            <h4 className="text-xs font-semibold text-white uppercase tracking-wider mt-6 mb-3">Stack</h4>
            <div className="flex flex-wrap gap-1.5">
              {['React', 'FastAPI', 'PyTorch', 'U-Net', 'Neon DB'].map(t => (
                <span key={t} className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700">
                  {t}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Feature highlights */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-10 py-8 border-y border-slate-800">
          {[
            { icon: Zap, title: 'Real-time Detection', desc: 'Processes INSAT-3DR data every 30 minutes' },
            { icon: Shield, title: 'Physics-based', desc: 'BT threshold < 218K for confirmed TCCs' },
            { icon: Globe, title: 'INSAT Coverage', desc: 'Full Asia-Pacific satellite coverage' },
          ].map((f, i) => (
            <div key={i} className="flex items-start gap-3">
              <div className="p-2 rounded-lg bg-cyan-500/10 flex-shrink-0">
                <f.icon className="w-4 h-4 text-cyan-400" />
              </div>
              <div>
                <p className="text-sm font-medium text-white">{f.title}</p>
                <p className="text-xs text-slate-500 mt-0.5">{f.desc}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Bottom bar */}
        <div className="flex flex-col md:flex-row items-center justify-between gap-3">
          <p className="text-xs text-slate-500">
            © {new Date().getFullYear()} CloudSense — AI-Powered Satellite Intelligence. Built for INSAT-3D/3DR data.
          </p>
          <div className="flex items-center gap-4 text-xs text-slate-600">
            <span>Model: U-Net + MobileNetV2</span>
            <span>·</span>
            <span>Val IoU: 0.89</span>
            <span>·</span>
            <span>1897 training samples</span>
          </div>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
