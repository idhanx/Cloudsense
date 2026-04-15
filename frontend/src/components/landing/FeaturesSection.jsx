import { Cloud, Radar, TrendingUp, Database, Cpu, Download } from 'lucide-react';

const features = [
  {
    icon: Cloud,
    title: 'Cloud Detection',
    description: 'Automated detection of tropical cloud clusters using advanced infrared brightness temperature thresholding.',
  },
  {
    icon: Radar,
    title: 'Real-Time Tracking',
    description: 'Track cloud cluster movement, merging, and splitting events with half-hourly temporal resolution.',
  },
  {
    icon: TrendingUp,
    title: 'AI Analysis',
    description: 'Machine learning algorithms for cluster segmentation, classification, and lifecycle prediction.',
  },
  {
    icon: Database,
    title: 'Statistical Insights',
    description: 'Comprehensive metrics including brightness temperature, radius, area, and cloud-top height estimates.',
  },
  {
    icon: Cpu,
    title: 'Data Ingestion',
    description: 'Support for HDF5 satellite data with automatic preprocessing, validation, and quality control.',
  },
  {
    icon: Download,
    title: 'NetCDF Export',
    description: 'Export analysis results in standardized NetCDF format for integration with other research tools.',
  },
];

const FeaturesSection = () => {
  return (
    <section className="py-20 bg-gray-900">
      <div className="max-w-7xl mx-auto px-4">
        <div className="text-center mb-16">
          <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">
            Mission-Critical Capabilities
          </h2>
          <p className="text-xl text-gray-400 max-w-2xl mx-auto">
            Enterprise-grade tools for atmospheric research and climate monitoring
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {features.map((feature, index) => (
            <div
              key={index}
              className="bg-gray-800 rounded-xl p-6 border border-gray-700 hover:border-cyan-400/50 transition-colors"
            >
              <feature.icon className="h-10 w-10 text-cyan-400 mb-4" />
              <h3 className="text-xl font-semibold text-white mb-2">{feature.title}</h3>
              <p className="text-gray-400">{feature.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default FeaturesSection;

