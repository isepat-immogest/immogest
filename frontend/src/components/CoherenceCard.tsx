import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Wrench } from 'lucide-react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { api } from '@/lib/api'
import { invalidateAll, notifyError } from '@/lib/queries'
import type { Coherence } from '@/lib/types'

/** Anomalies de données détectées (bien « loué » sans contrat, quotes-parts ≠ 100 %, loyers hors contrat…). */
export function CoherenceCard() {
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ['/coherence'], queryFn: () => api.get<Coherence>('/coherence/'), staleTime: 60_000 })
  const corriger = useMutation({
    mutationFn: () => api.post<{ biens_corriges: number }>('/coherence/'),
    onSuccess: (r) => {
      invalidateAll(qc, '/biens', '/coherence')
      toast.success(r.biens_corriges ? `${r.biens_corriges} bien(s) resynchronisé(s).` : 'Aucun statut à corriger.')
    },
    onError: notifyError,
  })
  if (!data) return null
  if (data.total === 0) {
    return (
      <Card><CardContent className="flex items-center gap-2 p-4 text-sm text-success"><CheckCircle2 className="h-4 w-4" /> Données cohérentes : aucune anomalie détectée.</CardContent></Card>
    )
  }
  const statutsABiens = data.anomalies.some((a) => ['bien_loue_sans_contrat', 'bien_libre_avec_contrat'].includes(a.code))
  return (
    <Card className="border-warning/50">
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="flex items-center gap-2 text-base"><AlertTriangle className="h-4 w-4 text-warning" /> {data.total} anomalie(s) à vérifier</CardTitle>
        {statutsABiens && <Button size="sm" variant="outline" loading={corriger.isPending} onClick={() => corriger.mutate()}><Wrench /> Réaligner les statuts des biens</Button>}
      </CardHeader>
      <CardContent>
        <ul className="space-y-1.5 text-sm">
          {data.anomalies.slice(0, 6).map((a, i) => (
            <li key={i} className="flex gap-2">
              <span className={a.gravite === 'erreur' ? 'text-destructive' : 'text-warning'}>●</span>
              {a.url ? <Link to={a.url} className="hover:underline">{a.message}</Link> : a.message}
            </li>
          ))}
        </ul>
        {data.total > 6 && <p className="mt-2 text-xs text-muted-foreground">… et {data.total - 6} autre(s).</p>}
      </CardContent>
    </Card>
  )
}
