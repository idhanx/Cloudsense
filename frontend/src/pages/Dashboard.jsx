import { useState, useEffect, lazy, Suspense } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Cloud, Thermometer, Ruler, TrendingUp, Loader2, Upload } from 'lucide-react';
import Sidebar from '@/components/dashboard/Sidebar';
import DashboardHeader from '@/components/dashboard/DashboardHeader';
import apiClient from '@/services/api';

const ClusterMap = lazy(() => import('@/components/dashboard/ClusterMap'));

export default function Dashboard() {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [recentAnalyses, setRecentAnalyses] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDashboard();
    const interval = setInterval(loadDashboard, 60000);
    return () => clearInterval(interval);
  }, []);

  const loadDashboard = async () => {
    try {
      const [statsData, analysesData] = await Promise.all([
        apiClient.getDashboardStats(),
        apiClient.getRecentAnalyses(6),
      ]);
      setStats(statsData);
      setRecentAnalyses(analysesData);
    } catch { /* silent */ }
    finally { setLoading(false); }
  };

  const kpis = [
    { icon: Cloud, label: 'Active TCCs', value: stats?.active_tccs ?? 0, color: 'text-cyan-400', border: 'border-cyan-700/50' },
    { icon: Thermometer, label: 'Min BT (K)', value: stats?.min_brightness_temp ? `${stats.min_brightness_temp.toFixed(1)}` : '—', color: 'text-red-400', border: 'border-red-700/50' },
    { icon: TrendingUp, label: 'Total Analyses', value: stats?.total_analyses ?? 0, color: 'text-green-400', border: 'border-green-700/50' },
    { icon: Ruler, label: 'Total Area (km²)', value: stats?.total_area_km2 ? `${(stats.total_area_km2 / 1000).toFixed(0)}k` : '—', color: 'text-purple-400', border: 'border-purple-700/50' },
  ];

  if (loading) {
    return (
      <div className="flex h-screen bg-[#010816]">
        <Sidebar />
        <div className="flex-1 flex items-center justify-center">
          <Loader2 className="w-8 h-8 animate-spin text-cyan-500" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-[#010816]">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <DashboardHeader />
        <div className="flex-1 overflow-auto p-5 space-y-5">

          {/* KPI row */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {kpis.map((k, i) => (
              <div key={i} className={`bg-slate-900 border ${k.border} rounded-xl p-4`}>
                <div className="flex items-center gap-2 mb-2">
                  <k.icon className={`w-4 h-4 ${k.color}`} />
                  <span className="text-xs text-slate-400">{k.label}</span>
                </div>
                <p className="text-2xl font-bold text-white">{k.value}</p>
              </div>
            ))}
          </div>

          {/* Two-column */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">

            {/* Recent Analyses */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-800 flex justify-between items-center">
                <h3 className="text-sm font-semibold text-slate-200">Recent Analyses</h3>
                <button
                  onClick={() => navigate('/analysis')}
                  className="text-xs text-cyan-400 hover:text-cyan-300"
                >
                  View all →
                </button>
              </div>
              <div className="divide-y divide-slate-800">
                {recentAnalyses.length === 0 ? (
                  <div className="p-8 text-center">
                    <Upload className="w-8 h-8 text-slate-600 mx-auto mb-2" />
                    <p className="text-sm text-slate-500">No analyses yet.</p>
                    <button
                      onClick={() => navigate('/dashboard/upload')}
                      className="mt-2 text-xs text-cyan-400 hover:underline"
                    >
                      Upload data →
                    </button>
                  </div>
                ) : (
                  recentAnalyses.map((a, i) => {
                    let tccCount = 0;
                    try {
                      const r = typeof a.results === 'string' ? JSON.parse(a.results) : a.results;
                      tccCount = r?.tcc_count || r?.detections?.length || 0;
                    } catch { /* ignore */ }
                    return (
                      <div key={i} className="px-4 py-3 hover:bg-slate-800/40 transition-colors flex justify-between items-center">
                        <div className="min-w-0">
                          <p className="text-sm text-slate-200 truncate">{a.filename}</p>
                          <p className="text-xs text-slate-500">{a.source || 'upload'}</p>
                        </div>
                        <span className={`ml-3 flex-shrink-0 px-2 py-0.5 rounded-full text-xs font-medium ${a.status === 'complete'
                          ? 'bg-green-900/30 text-green-400 border border-green-700/50'
                          : 'bg-yellow-900/30 text-yellow-400 border border-yellow-700/50'
                          }`}>
                          {tccCount > 0 ? `${tccCount} TCCs` : a.status}
                        </span>
                      </div>
                    );
                  })
                )}
              </div>
            </div>

            {/* System info */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
              <h3 className="text-sm font-semibold text-slate-200 mb-4">System Overview</h3>
              <div className="space-y-3">
                {[
                  ['Model', 'U-Net (MobileNetV2)'],
                  ['Data Source', 'INSAT-3D/3DR IRBT'],
                  ['Resolution', '4 km/pixel'],
                  ['BT Threshold', '< 218 K'],
                  ['Min Area', '34,800 km²'],
                ].map(([k, v]) => (
                  <div key={k} className="flex justify-between items-center py-2 border-b border-slate-800 last:border-0">
                    <span className="text-xs text-slate-400">{k}</span>
                    <span className="text-xs text-slate-200 font-mono">{v}</span>
                  </div>
                ))}
              </div>
              <Button
                onClick={() => navigate('/dashboard/upload')}
                className="w-full mt-5 bg-cyan-600 hover:bg-cyan-700 text-sm h-9"
              >
                Upload New Data
              </Button>
            </div>
          </div>

          {/* Cluster Map */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-800 flex justify-between items-center">
              <div>
                <h3 className="text-sm font-semibold text-slate-200">TCC Detection Map</h3>
                <p className="text-xs text-slate-500">Detected cluster locations — click markers for details</p>
              </div>
            </div>
            <div className="h-[420px]">
              <Suspense fallback={
                <div className="flex items-center justify-center h-full bg-[#0a0e1a]">
                  <Loader2 className="w-6 h-6 animate-spin text-cyan-500" />
                </div>
              }>
                <ClusterMap />
              </Suspense>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
