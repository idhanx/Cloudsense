import { ArrowRight, Satellite, LayoutDashboard } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Link } from 'react-router-dom';
import apiClient from '@/services/api';

const HeroSection = () => {
  const isLoggedIn = apiClient.isLoggedIn();
  const user = apiClient.getUser();

  return (
    <section className="min-h-screen flex flex-col items-center justify-center px-4 py-24 text-center">
      {/* Status badge */}
      <div className="mb-8">
        <div className="inline-flex items-center gap-2 px-4 py-2 bg-gray-800/80 backdrop-blur-sm rounded-full border border-gray-700">
          <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
          <span className="text-sm font-medium text-gray-300">SYSTEM OPERATIONAL</span>
        </div>
      </div>

      {/* Heading */}
      <div className="flex items-center justify-center gap-3 mb-4">
        <Satellite className="h-10 w-10 text-cyan-400" />
        <h1 className="text-5xl md:text-7xl font-bold text-white tracking-tight">
          Cloud<span className="text-cyan-400">Sense</span>
        </h1>
      </div>

      <p className="text-xl md:text-2xl font-medium text-gray-300 mb-4">
        AI-powered tropical cloud intelligence
      </p>

      <p className="text-base text-gray-400 max-w-xl mx-auto mb-10">
        Detect, track, and analyze Tropical Cloud Clusters using INSAT-3D/3DR satellite data
        with U-Net deep learning and physics-based brightness temperature analysis.
      </p>

      {/* CTA */}
      {isLoggedIn ? (
        <div className="flex flex-col sm:flex-row gap-4 items-center justify-center mb-14">
          <Link to="/dashboard">
            <Button size="lg" className="bg-cyan-500 hover:bg-cyan-600 text-black font-semibold">
              <LayoutDashboard className="mr-2 h-5 w-5" />
              Go to Dashboard
            </Button>
          </Link>
          <span className="text-sm text-gray-500">
            Signed in as <span className="text-gray-300">{user?.name || user?.email}</span>
          </span>
        </div>
      ) : (
        <div className="flex flex-col sm:flex-row gap-4 justify-center mb-14">
          <Link to="/signup">
            <Button size="lg" className="bg-cyan-500 hover:bg-cyan-600 text-black font-semibold">
              Get Started <ArrowRight className="ml-2 h-5 w-5" />
            </Button>
          </Link>
          <Link to="/login">
            <Button size="lg" variant="outline" className="border-gray-600 text-white hover:bg-gray-800">
              Sign In
            </Button>
          </Link>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-8 max-w-3xl mx-auto">
        {[
          { value: '48', suffix: '', label: 'Updates/Day' },
          { value: '0.5', suffix: 'hr', label: 'Hour Intervals' },
          { value: 'U-Net', suffix: '', label: 'Segmentation Model' },
          { value: 'INSAT', suffix: '', label: '3D/3DR Satellite' },
        ].map((s, i) => (
          <div key={i} className="text-center">
            <div className="text-3xl md:text-4xl font-bold text-white mb-1">
              {s.value}<span className="text-cyan-400 text-lg">{s.suffix}</span>
            </div>
            <div className="text-sm text-gray-500">{s.label}</div>
          </div>
        ))}
      </div>
    </section>
  );
};

export default HeroSection;
