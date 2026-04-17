import { useQuery } from '@tanstack/react-query';
import { useAnalysisContext } from '../contexts/AnalysisContext';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/**
 * Hook for fetching recent analyses list.
 * The backend exposes /api/analyses/recent — this is the only analysis
 * endpoint that exists. The old /trajectory, /metadata, /status endpoints
 * do not exist in the backend and have been removed.
 */
export const useRecentAnalyses = (limit = 10) => {
    return useQuery({
        queryKey: ['recentAnalyses', limit],
        queryFn: async () => {
            const response = await fetch(`${API_BASE}/api/analyses/recent?limit=${limit}`);
            if (!response.ok) throw new Error(`Failed to fetch analyses: ${response.status}`);
            return response.json();
        },
        staleTime: 10_000, // 10 seconds
    });
};

/**
 * Hook for fetching dashboard KPI stats.
 */
export const useDashboardStats = () => {
    return useQuery({
        queryKey: ['dashboardStats'],
        queryFn: async () => {
            const response = await fetch(`${API_BASE}/api/dashboard/stats`);
            if (!response.ok) throw new Error(`Failed to fetch stats: ${response.status}`);
            return response.json();
        },
        staleTime: 15_000,
    });
};

/**
 * Hook for fetching all cluster data for the map/table.
 */
export const useClusters = (limit = 50) => {
    return useQuery({
        queryKey: ['clusters', limit],
        queryFn: async () => {
            const response = await fetch(`${API_BASE}/api/analysis/clusters?limit=${limit}`);
            if (!response.ok) throw new Error(`Failed to fetch clusters: ${response.status}`);
            return response.json();
        },
        staleTime: 15_000,
    });
};

/**
 * Legacy hook — kept for backward compatibility.
 * Returns the current analysis ID from context + recent analyses.
 */
export const useAnalysis = () => {
    const { currentAnalysisId } = useAnalysisContext();
    const { data: analyses, isLoading, error } = useRecentAnalyses();

    const currentAnalysis = analyses?.find(a => a.analysis_id === currentAnalysisId) || null;

    return {
        currentAnalysisId,
        currentAnalysis,
        analyses,
        isLoading,
        error,
    };
};
