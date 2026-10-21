import { lazy, Suspense, type ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

import { AppShell } from '@/components/layout/AppShell'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuth } from '@/hooks/useAuth'

const Login = lazy(() => import('@/pages/Login'))
const SetPassword = lazy(() => import('@/pages/SetPassword'))
const Dashboard = lazy(() => import('@/pages/Dashboard'))
const Biens = lazy(() => import('@/pages/Biens'))
const BienDetail = lazy(() => import('@/pages/BienDetail'))
const Locataires = lazy(() => import('@/pages/Locataires'))
const LocataireDetail = lazy(() => import('@/pages/LocataireDetail'))
const Contrats = lazy(() => import('@/pages/Contrats'))
const Paiements = lazy(() => import('@/pages/Paiements'))
const Interventions = lazy(() => import('@/pages/Interventions'))
const Reservations = lazy(() => import('@/pages/Reservations'))
const Demandes = lazy(() => import('@/pages/Demandes'))
const Depenses = lazy(() => import('@/pages/Depenses'))
const Calendrier = lazy(() => import('@/pages/Calendrier'))
const EspaceAccueil = lazy(() => import('@/pages/espace/EspaceAccueil'))
const EspacePaiements = lazy(() => import('@/pages/espace/EspacePaiements'))
const EspaceSignalements = lazy(() => import('@/pages/espace/EspaceSignalements'))
const EspaceSecurite = lazy(() => import('@/pages/espace/EspaceSecurite'))
const NotFound = lazy(() => import('@/pages/NotFound'))

function PageFallback() {
  return (
    <div className="space-y-4" role="status" aria-label="Chargement">
      <Skeleton className="h-8 w-56" />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
      <Skeleton className="h-72" />
    </div>
  )
}

function Protected({ role, children }: { role: 'gestionnaire' | 'locataire'; children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="p-8"><PageFallback /></div>
  if (!user) return <Navigate to="/connexion" replace />
  if (user.role !== role) return <Navigate to={user.role === 'locataire' ? '/espace' : '/'} replace />
  return <>{children}</>
}

export default function App() {
  return (
    <Suspense fallback={<div className="p-8"><PageFallback /></div>}>
      <Routes>
        <Route path="/connexion" element={<Login />} />
        <Route path="/activer/:uid/:token" element={<SetPassword mode="activation" />} />
        <Route path="/reinitialiser/:uid/:token" element={<SetPassword mode="reinitialisation" />} />

        <Route
          element={
            <Protected role="gestionnaire">
              <AppShell />
            </Protected>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="biens" element={<Biens />} />
          <Route path="biens/:id" element={<BienDetail />} />
          <Route path="locataires" element={<Locataires />} />
          <Route path="locataires/:id" element={<LocataireDetail />} />
          <Route path="contrats" element={<Contrats />} />
          <Route path="paiements" element={<Paiements />} />
          <Route path="interventions" element={<Interventions />} />
          <Route path="reservations" element={<Reservations />} />
          <Route path="demandes" element={<Demandes />} />
          <Route path="depenses" element={<Depenses />} />
          <Route path="calendrier" element={<Calendrier />} />
        </Route>

        <Route
          path="espace"
          element={
            <Protected role="locataire">
              <AppShell />
            </Protected>
          }
        >
          <Route index element={<EspaceAccueil />} />
          <Route path="paiements" element={<EspacePaiements />} />
          <Route path="signalements" element={<EspaceSignalements />} />
          <Route path="securite" element={<EspaceSecurite />} />
        </Route>

        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  )
}
