import { useQuery } from '@tanstack/react-query'
import {
  AlertTriangle,
  Building2,
  CalendarCheck,
  Download,
  Percent,
  Plus,
  RefreshCw,
  Wallet,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { EmptyState, ErrorState, PageHeader, StatCard, StatusBadge } from '@/components/common'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { api, downloadFile } from '@/lib/api'
import { PRIORITE, STATUT_BIEN, STATUT_PAIEMENT } from '@/lib/labels'
import { invalidateAll, notifyError } from '@/lib/queries'
import type { Dashboard as DashboardData } from '@/lib/types'
import { formatDate, formatFCFA, toNumber } from '@/lib/utils'
import { useMutation, useQueryClient } from '@tanstack/react-query'

const PIE_COLORS: Record<string, string> = {
  libre: 'hsl(var(--success))',
  loue: 'hsl(var(--primary))',
  travaux: 'hsl(var(--warning))',
  vente: 'hsl(var(--muted-foreground))',
}

export default function Dashboard() {
  const qc = useQueryClient()
  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ['/dashboard'],
    queryFn: () => api.get<DashboardData>('/dashboard/'),
    refetchInterval: 60_000,
  })

  const generer = useMutation({
    mutationFn: () => api.post<{ crees: number }>('/paiements/generer-mois/'),
    onSuccess: (r) => {
      invalidateAll(qc, '/paiements')
      toast.success(r.crees ? `${r.crees} loyer(s) généré(s) pour ce mois.` : 'Tous les loyers du mois existent déjà.')
    },
    onError: notifyError,
  })

  if (isError) return <ErrorState message={error instanceof Error ? error.message : 'Erreur'} onRetry={() => void refetch()} />

  const k = data?.kpis
  const serie = (data?.revenus ?? []).map((r) => ({ mois: r.mois, Prévu: toNumber(r.prevu), Encaissé: toNumber(r.encaisse) }))
  const pie = (data?.repartition_biens ?? []).map((r) => ({ name: STATUT_BIEN[r.statut]?.label ?? r.statut, key: r.statut, value: r.nombre }))

  return (
    <>
      <PageHeader
        title="Tableau de bord"
        description="Vue d'ensemble de votre patrimoine."
        actions={
          <>
            <Button variant="outline" size="sm" loading={generer.isPending} onClick={() => generer.mutate()}>
              <RefreshCw /> Générer les loyers du mois
            </Button>
            <Button variant="outline" size="sm" onClick={() => downloadFile('/rapports/financier/', { export: 'xlsx' }, 'rapport.xlsx').catch(notifyError)}>
              <Download /> Rapport Excel
            </Button>
            <Button size="sm" asChild>
              <Link to="/biens"><Plus /> Nouveau bien</Link>
            </Button>
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {isPending || !k ? (
          Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />)
        ) : (
          <>
            <StatCard label="Biens" value={k.total_biens} hint={`${k.biens_loues} loués · ${k.biens_libres} libres`} icon={<Building2 className="h-5 w-5" />} />
            <StatCard label="Taux d'occupation" value={`${k.taux_occupation} %`} hint={`${k.biens_travaux} en travaux`} icon={<Percent className="h-5 w-5" />} tone="success" />
            <StatCard label="Encaissé ce mois" value={formatFCFA(k.revenus_mois)} hint={`${k.taux_recouvrement} % du prévu (${formatFCFA(k.prevu_mois)})`} icon={<Wallet className="h-5 w-5" />} tone="success" />
            <StatCard label="Loyers en retard" value={k.nb_retard} hint={`${formatFCFA(k.montant_retard)} à recouvrer`} icon={<AlertTriangle className="h-5 w-5" />} tone={k.nb_retard ? 'danger' : 'neutral'} />
          </>
        )}
      </div>

      {k && (k.reservations_a_traiter > 0 || k.demandes_non_traitees > 0) && (
        <Card className="mt-4 flex flex-wrap items-center gap-4 border-primary/30 bg-accent/50 p-4 text-sm">
          <CalendarCheck className="h-5 w-5 text-primary" />
          {k.reservations_a_traiter > 0 && (
            <Link className="font-medium hover:underline" to="/reservations">{k.reservations_a_traiter} réservation(s) à traiter</Link>
          )}
          {k.demandes_non_traitees > 0 && (
            <Link className="font-medium hover:underline" to="/demandes">{k.demandes_non_traitees} demande(s) client non traitée(s)</Link>
          )}
        </Card>
      )}

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader><CardTitle>Loyers : prévu vs encaissé (6 mois)</CardTitle></CardHeader>
          <CardContent>
            {isPending ? <Skeleton className="h-64" /> : (
              <div className="h-64" role="img" aria-label="Histogramme des loyers prévus et encaissés sur 6 mois">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={serie} margin={{ left: -10, right: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" />
                    <XAxis dataKey="mois" tickLine={false} axisLine={false} fontSize={12} />
                    <YAxis tickLine={false} axisLine={false} fontSize={12} tickFormatter={(v: number) => `${Math.round(v / 1000)}k`} />
                    <Tooltip formatter={(v: number) => formatFCFA(v)} contentStyle={{ background: 'hsl(var(--popover))', border: '1px solid hsl(var(--border))', borderRadius: 8 }} />
                    <Legend />
                    <Bar isAnimationActive={false} dataKey="Prévu" fill="hsl(var(--muted-foreground) / 0.35)" radius={[4, 4, 0, 0]} />
                    <Bar isAnimationActive={false} dataKey="Encaissé" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Répartition des biens</CardTitle></CardHeader>
          <CardContent>
            {isPending ? <Skeleton className="h-64" /> : pie.length === 0 ? (
              <EmptyState title="Aucun bien" description="Ajoutez votre premier bien pour voir la répartition." />
            ) : (
              <div className="h-64" role="img" aria-label="Répartition des biens par statut">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie isAnimationActive={false} data={pie} dataKey="value" nameKey="name" innerRadius={55} outerRadius={85} paddingAngle={3}>
                      {pie.map((p) => <Cell key={p.key} fill={PIE_COLORS[p.key]} />)}
                    </Pie>
                    <Tooltip contentStyle={{ background: 'hsl(var(--popover))', border: '1px solid hsl(var(--border))', borderRadius: 8 }} />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader><CardTitle>Derniers paiements</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {isPending ? <Skeleton className="h-32" /> : data.paiements_recents.length === 0 ? (
              <p className="text-sm text-muted-foreground">Aucun paiement.</p>
            ) : data.paiements_recents.map((p) => (
              <div key={p.id} className="flex items-center justify-between gap-2 text-sm">
                <div className="min-w-0">
                  <p className="truncate font-medium">{p.locataire_nom}</p>
                  <p className="truncate text-xs text-muted-foreground">{p.bien_nom}</p>
                </div>
                <div className="text-right">
                  <p className="tabular-nums">{formatFCFA(p.montant_paye)}</p>
                  <StatusBadge map={STATUT_PAIEMENT} value={p.statut} />
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Interventions ouvertes</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {isPending ? <Skeleton className="h-32" /> : data.interventions.length === 0 ? (
              <p className="text-sm text-muted-foreground">Rien à traiter.</p>
            ) : data.interventions.map((i) => (
              <div key={i.id} className="flex items-center justify-between gap-2 text-sm">
                <div className="min-w-0">
                  <p className="truncate font-medium">{i.titre}</p>
                  <p className="truncate text-xs text-muted-foreground">{i.bien}</p>
                </div>
                <StatusBadge map={PRIORITE} value={i.priorite} />
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Contrats arrivant à échéance</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {isPending ? <Skeleton className="h-32" /> : data.contrats_fin.length === 0 ? (
              <p className="text-sm text-muted-foreground">Aucune échéance dans les 90 jours.</p>
            ) : data.contrats_fin.map((c) => (
              <div key={c.id} className="flex items-center justify-between gap-2 text-sm">
                <div className="min-w-0">
                  <p className="truncate font-medium">{c.locataire}</p>
                  <p className="truncate text-xs text-muted-foreground">{c.bien}</p>
                </div>
                <span className="text-xs text-muted-foreground">{formatDate(c.date_fin)}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </>
  )
}
