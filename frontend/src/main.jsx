import React from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AnalysisProvider } from "./contexts/AnalysisContext";
import App from "./App";
import "./index.css";

// Create a client
const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            refetchOnWindowFocus: false,
            retry: 1,
        },
    },
});

const root = createRoot(document.getElementById("root"));
root.render(
    <QueryClientProvider client={queryClient}>
        <AnalysisProvider>
            <App />
        </AnalysisProvider>
    </QueryClientProvider>
);
