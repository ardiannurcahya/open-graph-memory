import { lazy, Suspense } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import DatasetsPage from "./pages/DatasetsPage";

const GraphPage = lazy(() => import("./pages/GraphPage"));
const AgentMemoryPage = lazy(() => import("./pages/AgentMemoryPage"));
const PlaygroundPage = lazy(() => import("./pages/PlaygroundPage"));

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/datasets" element={<DatasetsPage />} />
          <Route path="/graph" element={<Suspense fallback={null}><GraphPage /></Suspense>} />
          <Route path="/memory" element={<Suspense fallback={null}><AgentMemoryPage /></Suspense>} />
          <Route path="/retrieval" element={<Suspense fallback={null}><PlaygroundPage /></Suspense>} />
          <Route path="/playground" element={<Suspense fallback={null}><PlaygroundPage /></Suspense>} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
