import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import Navbar from "./components/Navbar";
import Footer from "./components/landing/Footer";
import Index from "./pages/Index";
import Dashboard from "./pages/Dashboard";
import DataUpload from "./pages/DataUpload";
import Exports from "./pages/Exports";
import Settings from "./pages/Settings";
import Analysis from "./pages/Analysis";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import NotFound from "./pages/NotFound";

// Pages that have their own Sidebar layout — no global Navbar
const DASHBOARD_PATHS = ['/dashboard', '/analysis', '/exports', '/settings'];

const AppLayout = () => {
  const location = useLocation();
  const isDashboardPage = DASHBOARD_PATHS.some(p => location.pathname.startsWith(p));
  const isLandingPage = location.pathname === "/";

  return (
    <div className="min-h-screen w-full bg-[#010816] text-slate-50 antialiased flex flex-col">
      {/* Only show global Navbar on public pages (landing, login, signup) */}
      {!isDashboardPage && <Navbar />}
      <main className="w-full flex-1">
        <Routes>
          <Route path="/" element={<Index />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/dashboard/upload" element={<DataUpload />} />
          <Route path="/analysis" element={<Analysis />} />
          <Route path="/exports" element={<Exports />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
      {!isDashboardPage && !isLandingPage && <Footer />}
    </div>
  );
};

const App = () => (
  <TooltipProvider>
    <Toaster />
    <Sonner />
    <BrowserRouter>
      <AppLayout />
    </BrowserRouter>
  </TooltipProvider>
);

export default App;
