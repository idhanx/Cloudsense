import { Navigate } from 'react-router-dom';

export function ProtectedRoute({ children }) {
  const userId = localStorage.getItem('cloudsense_user_id');
  if (!userId) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}
