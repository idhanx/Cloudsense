import { createContext, useState, useContext, useEffect } from 'react';

export const AnalysisContext = createContext();

export const AnalysisProvider = ({ children }) => {
    const [currentAnalysisId, setCurrentAnalysisId] = useState(() => {
        // Restore from localStorage on init
        return localStorage.getItem('current_analysis_id') || null;
    });

    const selectAnalysis = (analysisId) => {
        setCurrentAnalysisId(analysisId);
        if (analysisId) {
            localStorage.setItem('current_analysis_id', analysisId);
        } else {
            localStorage.removeItem('current_analysis_id');
        }
    };

    const clearAnalysis = () => {
        setCurrentAnalysisId(null);
        localStorage.removeItem('current_analysis_id');
    };

    return (
        <AnalysisContext.Provider value={{
            currentAnalysisId,
            selectAnalysis,
            clearAnalysis
        }}>
            {children}
        </AnalysisContext.Provider>
    );
};

export const useAnalysisContext = () => {
    const context = useContext(AnalysisContext);
    if (!context) {
        throw new Error('useAnalysisContext must be used within AnalysisProvider');
    }
    return context;
};
