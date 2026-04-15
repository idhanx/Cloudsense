import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, Upload, Activity, Download, Settings, Cloud, LogOut, User, Home
} from 'lucide-react';
import { cn } from '@/lib/utils';
import apiClient from '@/services/api';

const menuItems = [
  { icon: LayoutDashboard, label: 'Dashboard', path: '/dashboard' },
  { icon: Upload, label: 'Data Upload', path: '/dashboard/upload' },
  { icon: Activity, label: 'Analysis', path: '/analysis' },
  { icon: Download, label: 'Exports', path: '/exports' },
  { icon: Settings, label: 'Settings', path: '/settings' },
];

const Sidebar = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const user = apiClient.getUser();

  const handleLogout = () => {
    apiClient.logout();
    navigate('/');
  };

  return (
    <aside className="w-56 bg-[#0a0f1e] border-r border-slate-800 h-screen flex flex-col flex-shrink-0">
      {/* Brand */}
      <div className="flex items-center gap-2 px-5 py-4 border-b border-slate-800">
        <div className="p-1.5 rounded-lg bg-cyan-500/10">
          <Cloud className="w-5 h-5 text-cyan-400" />
        </div>
        <div>
          <p className="text-sm font-bold text-white leading-none">CloudSense</p>
          <p className="text-[10px] text-slate-500 mt-0.5">TCC Detection</p>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
        {menuItems.map((item) => {
          const Icon = item.icon;
          const isActive =
            location.pathname === item.path ||
            (item.path !== '/dashboard' && location.pathname.startsWith(item.path));
          return (
            <Link
              key={item.path}
              to={item.path}
              className={cn(
                'flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors',
                isActive
                  ? 'bg-cyan-600 text-white font-medium'
                  : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800'
              )}
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-3 py-3 border-t border-slate-800 space-y-1">
        {/* Home */}
        <Link
          to="/"
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors"
        >
          <Home className="w-3.5 h-3.5" />
          Home
        </Link>
        {/* User */}
        {user && (
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-800/50">
            <div className="w-6 h-6 rounded-full bg-cyan-600 flex items-center justify-center flex-shrink-0">
              <User className="w-3 h-3 text-white" />
            </div>
            <span className="text-xs text-slate-300 truncate">{user.name || user.email}</span>
          </div>
        )}
        {/* Status */}
        <div className="flex items-center gap-2 px-3 py-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-green-500 flex-shrink-0" />
          <span className="text-xs text-slate-500">System Operational</span>
        </div>
        {/* Logout */}
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-slate-500 hover:text-red-400 hover:bg-slate-800 transition-colors"
        >
          <LogOut className="w-3.5 h-3.5" />
          Sign out
        </button>
      </div>
    </aside>
  );
};

export default Sidebar;
