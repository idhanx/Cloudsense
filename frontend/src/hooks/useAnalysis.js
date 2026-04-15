import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { useAnalysisContext } from '../contexts/AnalysisContext';

const API_BASE = 'http://localhost:8000';

export const useAnalysis = () => {
    const { currentAnalysisId } = useAnalysisContext();

    // Fetch trajectory data
    const {
        data: trajectory,
        isLoading: trajectoryLoading,
        error: trajectoryError
    } = useQuery({
        queryKey: ['trajectory', currentAnalysisId],
        queryFn: async () => {
            const response = await axios.get(`${API_BASE}/api/analysis/${currentAnalysisId}/trajectory`);
            return response.data;
        },
        enabled: !!currentAnalysisId,
        staleTime: 30000, // 30 seconds
    });

    // Fetch metadata
    const {
        data: metadata,
        isLoading: metadataLoading,
        error: metadataError
    } = useQuery({
        queryKey: ['metadata', currentAnalysisId],
        queryFn: async () => {
            const response = await axios.get(`${API_BASE}/api/analysis/${currentAnalysisId}/metadata`);
            return response.data;
        },
        enabled: !!currentAnalysisId,
        staleTime: 60000, // 1 minute
    });

    // Fetch status
    const {
        data: status,
        isLoading: statusLoading,
        error: statusError
    } = useQuery({
        queryKey: ['status', currentAnalysisId],
        queryFn: async () => {
            const response = await axios.get(`${API_BASE}/api/analysis/${currentAnalysisId}/status`);
            return response.data;
        },
        enabled: !!currentAnalysisId,
        refetchInterval: 5000, // Poll every 5 seconds if processing
        refetchIntervalInBackground: false,
    });

    return {
        currentAnalysisId,
        trajectory,
        metadata,
        status,
        isLoading: trajectoryLoading || metadataLoading || statusLoading,
        error: trajectoryError || metadataError || statusError,
    };
};

// Hook for fetching recent analyses list
export const useRecentAnalyses = () => {
    return useQuery({
        queryKey: ['recentAnalyses'],
        queryFn: async () => {
            const response = await axios.get(`${API_BASE}/api/analyses/recent`);
            return response.data;
        },
        staleTime: 10000, // 10 seconds
    });
};
