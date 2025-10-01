import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './components/Dashboard';
import DomainManager from './components/DomainManager';
import IndexingPanel from './components/IndexingPanel';
import UserManagement from './components/UserManagement';
import ProtectedRoute from './components/ProtectedRoute';
import { AuthProvider, useAuth, LoginForm } from './components/Auth';
import './App.css';

// Компонент для маршрутов аутентификации
const AuthRoutes = () => {
  const { isAuthenticated, login } = useAuth();
  
  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }
  
  const handleLoginSuccess = (user, token) => {
    login(user, token);
    // Перенаправление произойдет автоматически через useAuth
  };
  
  return (
    <Routes>
      <Route path="/login" element={<LoginForm onLoginSuccess={handleLoginSuccess} />} />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
};

// Основные маршруты приложения
const AppRoutes = () => {
  return (
    <Layout>
      <Routes>
        <Route 
          path="/" 
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          } 
        />
        <Route 
          path="/domains" 
          element={
            <ProtectedRoute>
              <DomainManager />
            </ProtectedRoute>
          } 
        />
        <Route 
          path="/indexing" 
          element={
            <ProtectedRoute>
              <IndexingPanel />
            </ProtectedRoute>
          } 
        />
        <Route 
          path="/users" 
          element={
            <ProtectedRoute requireAdmin={true}>
              <UserManagement />
            </ProtectedRoute>
          } 
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
};

// Главный компонент приложения
const AppContent = () => {
  const { isAuthenticated, loading } = useAuth();
  
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Загрузка...</p>
        </div>
      </div>
    );
  }
  
  return isAuthenticated ? <AppRoutes /> : <AuthRoutes />;
};

function App() {
  return (
    <Router>
      <AuthProvider>
        <div className="App">
          <AppContent />
        </div>
      </AuthProvider>
    </Router>
  );
}

export default App;













