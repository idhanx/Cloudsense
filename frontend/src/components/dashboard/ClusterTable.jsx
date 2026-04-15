import { cn } from '@/lib/utils';
import { useQuery } from '@tanstack/react-query';
import apiClient from '@/services/api';

const fetchClusters = async () => {
  try {
    const response = await fetch(`${apiClient.baseURL}/api/analysis/clusters`, {
      headers: { 'Authorization': `Bearer ${apiClient.getToken()}` }
    });
    if (response.ok) return response.json();
    return [];
  } catch (error) {
    console.error("Failed to fetch clusters", error);
    return [];
  }
};

const ClusterTable = () => {
  const { data: clusters = [], isLoading } = useQuery({
    queryKey: ['clusters'],
    queryFn: fetchClusters,
    refetchInterval: 10000
  });

  if (isLoading) return <div className="p-4 text-slate-400">Loading data...</div>;
  if (clusters.length === 0) return (
    <div className="p-8 text-center text-slate-500">
      <p className="text-lg mb-2">No detections yet</p>
      <p className="text-sm">Upload an H5 file or fetch from MOSDAC to see TCC clusters here.</p>
    </div>
  );

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead className="bg-slate-800">
          <tr>
            <th className="text-left py-3 px-4 text-xs font-medium text-slate-300 uppercase tracking-wider">Cluster ID</th>
            <th className="text-left py-3 px-4 text-xs font-medium text-slate-300 uppercase tracking-wider">Classification</th>
            <th className="text-left py-3 px-4 text-xs font-medium text-slate-300 uppercase tracking-wider">Centroid</th>
            <th className="text-left py-3 px-4 text-xs font-medium text-slate-300 uppercase tracking-wider">Area (km²)</th>
            <th className="text-left py-3 px-4 text-xs font-medium text-slate-300 uppercase tracking-wider">Mean BT (K)</th>
            <th className="text-left py-3 px-4 text-xs font-medium text-slate-300 uppercase tracking-wider">Min BT (K)</th>
            <th className="text-left py-3 px-4 text-xs font-medium text-slate-300 uppercase tracking-wider">Radius (km)</th>
            <th className="text-left py-3 px-4 text-xs font-medium text-slate-300 uppercase tracking-wider">Source</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800">
          {clusters.map((cluster, index) => {
            // Determine classification from BT
            const minBT = cluster.minBT || 999;
            const classification = minBT < 220 ? 'Confirmed TCC' : minBT < 235 ? 'Likely TCC' : 'Cloud Cluster';
            const classStyle = minBT < 220
              ? 'bg-red-500/20 text-red-300 border border-red-500/30'
              : minBT < 235
                ? 'bg-yellow-500/20 text-yellow-300 border border-yellow-500/30'
                : 'bg-slate-500/20 text-slate-300 border border-slate-500/30';

            return (
              <tr key={index} className="hover:bg-slate-800/50 transition-colors">
                <td className="py-3 px-4 font-medium text-cyan-400">{cluster.id}</td>
                <td className="py-3 px-4">
                  <span className={cn("inline-flex items-center px-2 py-1 rounded-full text-xs font-semibold", classStyle)}>
                    {classification}
                  </span>
                </td>
                <td className="py-3 px-4 text-slate-200">
                  {cluster.centroidLat?.toFixed(2)}°, {cluster.centroidLon?.toFixed(2)}°
                </td>
                <td className="py-3 px-4 text-slate-200 font-medium">{cluster.area?.toLocaleString()}</td>
                <td className="py-3 px-4 text-orange-400 font-medium">{cluster.avgBT?.toFixed(1)}</td>
                <td className="py-3 px-4 text-red-400 font-medium">{cluster.minBT?.toFixed(1)}</td>
                <td className="py-3 px-4 text-slate-200">{cluster.radius?.toFixed(1)}</td>
                <td className="py-3 px-4">
                  <span className="text-xs text-slate-400 font-mono truncate max-w-[150px] block">{cluster.source || "—"}</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

export default ClusterTable;
