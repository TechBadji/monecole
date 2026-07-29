import { StrictMode, Suspense, lazy, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AuthProvider, useAuth } from "./auth";
import Layout from "./components/Layout";
import { SyncBanner } from "./components/OfflineBanners";
import { startSyncWatcher } from "./offline/sync";
import Login from "./pages/Login";

// Écrans chargés à la demande. Un comptable qui saisit des encaissements n'a pas à
// télécharger la bibliothèque de graphiques du tableau de bord, ni le module de paie.
const Arrears = lazy(() => import("./pages/Arrears"));
const AuditTrail = lazy(() => import("./pages/AuditTrail"));
const Bilan = lazy(() => import("./pages/Bilan"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const DataImport = lazy(() => import("./pages/DataImport"));
const Encais = lazy(() => import("./pages/Encais"));
const Expenses = lazy(() => import("./pages/Expenses"));
const ParentPortal = lazy(() => import("./pages/portal/ParentPortal"));
const PaymentRegister = lazy(() => import("./pages/PaymentRegister"));
const Payroll = lazy(() => import("./pages/Payroll"));
const Students = lazy(() => import("./pages/Students"));
const Teachers = lazy(() => import("./pages/Teachers"));

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
  if (!can(resource, "view")) return <Navigate to="/" replace />;
  return <Suspense fallback={<div className="spinner">Chargement…</div>}>{children}</Suspense>;
}

/** La page d'accueil dépend du rôle : chacun arrive sur ce qu'il utilise. */
function Home() {
  const { can } = useAuth();
  if (can("report", "view")) {
    return (
      <Suspense fallback={<div className="spinner">Chargement…</div>}>
        <Dashboard />
      </Suspense>
    );
  }
  if (can("monthlypayment", "view")) return <Navigate to="/encaissements" replace />;
  return <Navigate to="/eleves" replace />;
}

function Root() {
  const { profile, loading } = useAuth();

  if (loading) return <div className="spinner">Chargement…</div>;

  // Un parent n'entre jamais dans l'administration : son interface est le portail.
  if (profile?.role === "PARENT") {
    return (
      <Suspense fallback={<div className="spinner">Chargement…</div>}>
        <ParentPortal />
      </Suspense>
    );
  }
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
          path="paie"
          element={
            <Guarded resource="salary">
              <Payroll />
            </Guarded>
          }
        />
        <Route
          path="import"
          element={
            <Guarded resource="dataimport">
              <DataImport />
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

/** Coquille hors ligne. Échec silencieux : l'application marche sans. */
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      console.info("Service worker non enregistré — mode hors ligne indisponible.");
    });
  });
}

startSyncWatcher();

function App() {
  return (
    <>
      <SyncBanner />
      <Root />
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
