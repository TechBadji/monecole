import { StrictMode, Suspense, lazy, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AuthProvider, useAuth } from "./auth";
import Layout from "./components/Layout";
import { SyncBanner } from "./components/OfflineBanners";
import { startSyncWatcher } from "./offline/sync";
import ForgotPassword from "./pages/ForgotPassword";
import Login from "./pages/Login";
import RouteBoundary from "./components/RouteBoundary";
import ResetPassword from "./pages/ResetPassword";

// Écrans chargés à la demande. Un comptable qui saisit des encaissements n'a pas à
// télécharger la bibliothèque de graphiques du tableau de bord, ni le module de paie.
const Account = lazy(() => import("./pages/Account"));
const Arrears = lazy(() => import("./pages/Arrears"));
const Attendance = lazy(() => import("./pages/Attendance"));
const Compositions = lazy(() => import("./pages/Compositions"));
const Grades = lazy(() => import("./pages/Grades"));
const ReportCards = lazy(() => import("./pages/ReportCards"));
const Settings = lazy(() => import("./pages/Settings"));
const Subjects = lazy(() => import("./pages/Subjects"));
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
  return <Screen>{children}</Screen>;
}

/**
 * Écran chargé à la demande : attente pendant le chargement, message si le
 * chargement échoue. Sans la barrière, un module introuvable — cas courant
 * après un déploiement, quand le service worker garde un fragment périmé —
 * vidait toute la page sans rien dire.
 */
function Screen({ children }: { children: ReactNode }) {
  return (
    <RouteBoundary>
      <Suspense fallback={<div className="spinner">Chargement…</div>}>{children}</Suspense>
    </RouteBoundary>
  );
}

/** La page d'accueil dépend du rôle : chacun arrive sur ce qu'il utilise. */
function Home() {
  const { can } = useAuth();
  if (can("report", "view")) {
    return (
      <Screen>
        <Dashboard />
      </Screen>
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
      <Screen>
        <ParentPortal />
      </Screen>
    );
  }
  // Hors session, trois écrans sont joignables. Sans ces routes, le lien reçu
  // par courrier tomberait sur le formulaire de connexion, et « mot de passe
  // oublié » ne mènerait nulle part.
  if (!profile) {
    return (
      <Routes>
        <Route path="/mot-de-passe-oublie" element={<ForgotPassword />} />
        <Route path="/reinitialiser" element={<ResetPassword />} />
        <Route path="*" element={<Login />} />
      </Routes>
    );
  }

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        {/* Aucun `Guarded` : chacun accède à son propre compte, quel que soit
            son rôle. */}
        <Route
          path="compte"
          element={
            <Screen>
              <Account />
            </Screen>
          }
        />
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
          path="matieres"
          element={
            <Guarded resource="subject">
              <Subjects />
            </Guarded>
          }
        />
        <Route
          path="compositions"
          element={
            <Guarded resource="composition">
              <Compositions />
            </Guarded>
          }
        />
        <Route
          path="notes"
          element={
            <Guarded resource="grade">
              <Grades />
            </Guarded>
          }
        />
        <Route
          path="bulletins"
          element={
            <Guarded resource="reportcard">
              <ReportCards />
            </Guarded>
          }
        />
        <Route
          path="assiduite"
          element={
            <Guarded resource="attendance">
              <Attendance />
            </Guarded>
          }
        />
        <Route
          path="parametres"
          element={
            <Guarded resource="reportcard">
              <Settings />
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
