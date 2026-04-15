import { useLocation } from 'react-router-dom';

const PAGE_TITLES = {
  '/dashboard': { title: 'Dashboard', sub: 'Overview & recent detections' },
  '/dashboard/upload': { title: 'Data Input', sub: 'Upload satellite data or fetch from MOSDAC' },
  '/analysis': { title: 'Analysis', sub: 'TCC detection results & visualisation' },
  '/exports': { title: 'Exports', sub: 'Download inference outputs' },
  '/settings': { title: 'Settings', sub: 'Configure system preferences' },
};

const DashboardHeader = () => {
  const { pathname } = useLocation();
  const info = PAGE_TITLES[pathname] || { title: 'CloudSense', sub: '' };

  return (
    <header className="bg-[#0a0f1e] border-b border-slate-800 px-6 py-3 flex-shrink-0">
      <h2 className="text-base font-semibold text-slate-100">{info.title}</h2>
      {info.sub && <p className="text-xs text-slate-500 mt-0.5">{info.sub}</p>}
    </header>
  );
};

export default DashboardHeader;
