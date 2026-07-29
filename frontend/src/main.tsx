import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AuthProvider, useAuth } from "./auth";
import Layout from "./components/Layout";
import Arrears from "./pages/Arrears";
import AuditTrail from "./pages/AuditTrail";
import Bilan from "./pages/Bilan";
import Dashboard from "./pages/Dashboard";
import Encais from "./pages/Encais";
import Expenses from "./pages/Expenses";
import Login from "./pages/Login";
import PaymentRegister from "./pages/PaymentRegister";
import Students from "./pages/Students";
import Teachers from "./pages/Teachers";

import "./index.css";

/**
 * Masque une page que le rôle n'ouvre pas.
 *
 * Confort d'interface uniquement : l'autorisation qui fait foi est celle appliquée
 * par le serveur sur chaque appel. Contourner cette redirection ne donne accès à
 * rien.
 */
function Guarded({ resource, children }: { resource: string; children: ReactNode }) {
  const { can } = useAuth();
  return can(resource, "view") ? <>{children}</> : <Navigate to="/" replace />;
}

/** La page d'accueil dépend du rôle : chacun arrive sur ce qu'il utilise. */
function Home() {
  const { can } = useAuth();
  if (can("report", "view")) return <Dashboard />;
  if (can("monthlypayment", "view")) return <Navigate to="/encaissements" replace />;
  return <Navigate to="/eleves" replace />;
}

function Root() {
  const { profile, loading } = useAuth();

  if (loading) return <div className="spinner">Chargement…</div>;
  if (!profile) return <Login />;

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route
          path="eleves"
          element={
            <Guarded resource="student">
              <Students />
            </Guarded>
          }
        />
        <Route
          path="encaissements"
          element={
            <Guarded resource="monthlypayment">
              <PaymentRegister />
            </Guarded>
          }
        />
        <Route
          path="arrieres"
          element={
            <Guarded resource="monthlypayment">
              <Arrears />
            </Guarded>
          }
        />
        <Route
          path="depenses"
          element={
            <Guarded resource="expense">
              <Expenses />
            </Guarded>
          }
        />
        <Route
          path="bilan"
          element={
            <Guarded resource="report">
              <Bilan />
            </Guarded>
          }
        />
        <Route
          path="encais"
          element={
            <Guarded resource="report">
              <Encais />
            </Guarded>
          }
        />
        <Route
          path="enseignants"
          element={
            <Guarded resource="teacher">
              <Teachers />
            </Guarded>
          }
        />
        <Route
          path="journal"
          element={
            <Guarded resource="auditlog">
              <AuditTrail />
            </Guarded>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Root />
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
