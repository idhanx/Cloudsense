import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Loader2, Upload, CloudRain, Clock, Satellite, Download, CheckCircle, AlertCircle } from 'lucide-react';
import Sidebar from '@/components/dashboard/Sidebar';
import DashboardHeader from '@/components/dashboard/DashboardHeader';
import apiClient from '@/services/api';

export default function DataUpload() {
  const navigate = useNavigate();
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [uploadError, setUploadError] = useState(null);
  const [mosdacCreds, setMosdacCreds] = useState({ username: '', password: '' });
  const [hoursBack, setHoursBack] = useState(0.5);
  const [downloading, setDownloading] = useState(false);
  const [mosdacLogs, setMosdacLogs] = useState([]);
  const [mosdacResult, setMosdacResult] = useState(null);
  const [mosdacError, setMosdacError] = useState(null);
  const [activeTab, setActiveTab] = useState('upload');

  const timeOptions = [];
  for (let h = 0.5; h <= 12; h += 0.5) {
    timeOptions.push({ value: h, label: h < 1 ? '30 min' : h === 1 ? '1 hour' : `${h} hours` });
  }

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    setUploadResult(null);
    try {
      const result = await apiClient.uploadFile(file);
      setUploadResult(result);
    } catch (err) {
      setUploadError(err.message);
    } finally {
      setUploading(false);
    }
  };

  const handleMosdacDownload = async () => {
    if (!mosdacCreds.username || !mosdacCreds.password) {
      setMosdacError('Please enter MOSDAC credentials');
      return;
    }
    setDownloading(true);
    setMosdacError(null);
    setMosdacResult(null);
    setMosdacLogs([]);
    try {
      const response = await apiClient.startMosdacDownload(mosdacCreds.username, mosdacCreds.password, hoursBack);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();
        let eventType = '';
        for (const line of lines) {
          if (line.startsWith('event: ')) eventType = line.replace('event: ', '').trim();
          else if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.replace('data: ', ''));
              if (eventType === 'progress') setMosdacLogs(p => [...p.slice(-60), data.message]);
              else if (eventType === 'done') setMosdacResult(data);
              else if (eventType === 'error') setMosdacError(data.message);
            } catch { /* skip */ }
          }
        }
      }
    } catch (err) {
      setMosdacError(err.message);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="flex h-screen bg-[#010816]">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <DashboardHeader />
        <div className="flex-1 overflow-auto p-5">

          {/* Tabs */}
          <div className="flex gap-1 mb-5 bg-slate-900 border border-slate-800 rounded-lg p-1 w-fit">
            {[
              { id: 'upload', icon: Upload, label: 'File Upload' },
              { id: 'mosdac', icon: Satellite, label: 'MOSDAC Download' },
            ].map(t => (
              <button
                key={t.id}
                onClick={() => setActiveTab(t.id)}
                className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${activeTab === t.id
                    ? 'bg-cyan-600 text-white'
                    : 'text-slate-400 hover:text-slate-200'
                  }`}
              >
                <t.icon className="w-4 h-4" />
                {t.label}
              </button>
            ))}
          </div>

          {/* ── UPLOAD TAB ── */}
          {activeTab === 'upload' && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              {/* Left: dropzone */}
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                <h3 className="text-sm font-semibold text-slate-200 mb-4">Select File</h3>
                <div
                  className={`border-2 border-dashed rounded-xl p-10 text-center transition-colors cursor-pointer ${file ? 'border-cyan-500 bg-cyan-900/10' : 'border-slate-700 hover:border-slate-500'
                    }`}
                  onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) { setFile(f); setUploadResult(null); setUploadError(null); } }}
                  onDragOver={(e) => e.preventDefault()}
                  onClick={() => !file && document.getElementById('file-input').click()}
                >
                  {file ? (
                    <>
                      <CheckCircle className="w-10 h-10 text-cyan-400 mx-auto mb-3" />
                      <p className="text-white font-medium">{file.name}</p>
                      <p className="text-slate-400 text-sm mt-1">{(file.size / 1024 / 1024).toFixed(1)} MB</p>
                      <button
                        className="mt-3 text-xs text-slate-400 hover:text-white"
                        onClick={(e) => { e.stopPropagation(); setFile(null); setUploadResult(null); setUploadError(null); }}
                      >
                        Change file
                      </button>
                    </>
                  ) : (
                    <>
                      <Upload className="w-10 h-10 text-slate-600 mx-auto mb-3" />
                      <p className="text-slate-300 font-medium mb-1">Drop file here or click to browse</p>
                      <p className="text-slate-500 text-xs">Supports .h5, .hdf5, .png, .jpg</p>
                    </>
                  )}
                  <input id="file-input" type="file" accept=".h5,.hdf5,.png,.jpg,.jpeg" className="hidden"
                    onChange={(e) => { if (e.target.files[0]) { setFile(e.target.files[0]); setUploadResult(null); setUploadError(null); } }} />
                </div>

                <Button
                  onClick={handleUpload}
                  disabled={!file || uploading}
                  className="w-full mt-4 bg-cyan-600 hover:bg-cyan-700 h-10"
                >
                  {uploading
                    ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Processing...</>
                    : <><CloudRain className="w-4 h-4 mr-2" />Run TCC Detection</>}
                </Button>

                {uploadError && (
                  <div className="mt-4 p-3 bg-red-900/20 border border-red-800 rounded-lg flex gap-2">
                    <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
                    <p className="text-sm text-red-300">{uploadError}</p>
                  </div>
                )}
              </div>

              {/* Right: result */}
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                <h3 className="text-sm font-semibold text-slate-200 mb-4">Result</h3>
                {!uploadResult ? (
                  <div className="flex flex-col items-center justify-center h-48 text-slate-600">
                    <CloudRain className="w-10 h-10 mb-2" />
                    <p className="text-sm">Upload a file to see results</p>
                  </div>
                ) : (
                  <>
                    <div className="flex items-center gap-2 mb-5">
                      <CheckCircle className="w-5 h-5 text-green-400" />
                      <span className="text-sm font-semibold text-white">Analysis Complete</span>
                    </div>
                    <div className="grid grid-cols-3 gap-3 mb-5">
                      <div className="bg-slate-800 rounded-lg p-3 text-center">
                        <p className="text-2xl font-bold text-cyan-400">{uploadResult.tcc_count || 0}</p>
                        <p className="text-xs text-slate-400 mt-1">TCC Detected</p>
                      </div>
                      <div className="bg-slate-800 rounded-lg p-3 text-center">
                        <p className="text-2xl font-bold text-green-400">{uploadResult.tcc_pixels?.toLocaleString() || 0}</p>
                        <p className="text-xs text-slate-400 mt-1">TCC Pixels</p>
                      </div>
                      <div className="bg-slate-800 rounded-lg p-3 text-center">
                        <p className="text-2xl font-bold text-orange-400">
                          {uploadResult.total_area_km2 > 0 ? `${(uploadResult.total_area_km2 / 1000).toFixed(0)}k` : '0'}
                        </p>
                        <p className="text-xs text-slate-400 mt-1">Area (km²)</p>
                      </div>
                    </div>
                    <Button onClick={() => navigate('/analysis')} className="w-full bg-cyan-700 hover:bg-cyan-800 h-9 text-sm">
                      View Analysis Results →
                    </Button>
                  </>
                )}
              </div>
            </div>
          )}

          {/* ── MOSDAC TAB ── */}
          {activeTab === 'mosdac' && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              {/* Left: form */}
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-5">
                <h3 className="text-sm font-semibold text-slate-200">MOSDAC Credentials</h3>
                <p className="text-xs text-slate-500">
                  Register at{' '}
                  <a href="https://mosdac.gov.in" target="_blank" rel="noopener noreferrer" className="text-cyan-400 hover:underline">
                    mosdac.gov.in
                  </a>
                </p>

                <div className="space-y-3">
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Username / Email</label>
                    <input
                      type="text"
                      value={mosdacCreds.username}
                      onChange={(e) => setMosdacCreds(p => ({ ...p, username: e.target.value }))}
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-500"
                      placeholder="your@email.com"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Password</label>
                    <input
                      type="password"
                      value={mosdacCreds.password}
                      onChange={(e) => setMosdacCreds(p => ({ ...p, password: e.target.value }))}
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">
                      <Clock className="w-3 h-3 inline mr-1" />Time Range
                    </label>
                    <select
                      value={hoursBack}
                      onChange={(e) => setHoursBack(parseFloat(e.target.value))}
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-500"
                    >
                      {timeOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                    <p className="text-xs text-slate-600 mt-1">INSAT-3DR files at 30-min intervals</p>
                  </div>
                </div>

                <Button
                  onClick={handleMosdacDownload}
                  disabled={downloading || !mosdacCreds.username || !mosdacCreds.password}
                  className="w-full bg-cyan-600 hover:bg-cyan-700 h-10"
                >
                  {downloading
                    ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Downloading...</>
                    : <><Download className="w-4 h-4 mr-2" />Download & Analyze</>}
                </Button>

                {mosdacError && (
                  <div className="p-3 bg-red-900/20 border border-red-800 rounded-lg flex gap-2">
                    <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
                    <p className="text-sm text-red-300">{mosdacError}</p>
                  </div>
                )}
              </div>

              {/* Right: logs + result */}
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 flex flex-col gap-4">
                <h3 className="text-sm font-semibold text-slate-200">Live Output</h3>

                <div className="flex-1 bg-slate-950 border border-slate-800 rounded-lg p-3 min-h-[200px] max-h-72 overflow-y-auto font-mono text-xs text-slate-300 space-y-0.5">
                  {mosdacLogs.length === 0
                    ? <p className="text-slate-600">Waiting for download to start...</p>
                    : mosdacLogs.map((log, i) => <p key={i}>{log}</p>)
                  }
                </div>

                {mosdacResult && (
                  <div className="bg-slate-800 border border-cyan-700/40 rounded-lg p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <CheckCircle className="w-4 h-4 text-green-400" />
                      <span className="text-sm font-semibold text-white">{mosdacResult.message}</span>
                    </div>
                    <p className="text-xs text-slate-400 mb-3">{mosdacResult.files_downloaded} file(s) processed</p>
                    {mosdacResult.results?.length > 0 && (
                      <Button onClick={() => navigate('/analysis')} className="w-full bg-cyan-700 hover:bg-cyan-800 h-9 text-sm">
                        View Analysis →
                      </Button>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
