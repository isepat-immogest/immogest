import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { PageHeader } from '@/components/common'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { api } from '@/lib/api'
import type { CalendrierType, EvenementCalendrier } from '@/lib/types'
import { cn } from '@/lib/utils'

const JOURS = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
const COULEURS: Record<CalendrierType, string> = {
  reservation: 'bg-primary/15 text-primary border-primary/30',
  loyer: 'bg-warning/15 text-warning border-warning/30',
  contrat: 'bg-destructive/15 text-destructive border-destructive/30',
  intervention: 'bg-success/15 text-success border-success/30',
}
const LEGENDE: Record<CalendrierType, string> = {
  reservation: 'Séjours',
  loyer: 'Loyers à payer',
  contrat: 'Fins de bail',
  intervention: 'Interventions',
}
const MAX_PAR_JOUR = 3

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

/** Grille de 6 semaines (lundi → dimanche) couvrant le mois affiché. */
function grille(mois: Date): Date[] {
  const premier = new Date(mois.getFullYear(), mois.getMonth(), 1)
  const decalage = (premier.getDay() + 6) % 7
  const debut = new Date(premier.getFullYear(), premier.getMonth(), 1 - decalage)
  return Array.from({ length: 42 }, (_, i) => new Date(debut.getFullYear(), debut.getMonth(), debut.getDate() + i))
}

export default function Calendrier() {
  const navigate = useNavigate()
  const [mois, setMois] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1))
  const jours = useMemo(() => grille(mois), [mois])
  const debut = iso(jours[0])
  const fin = iso(jours[41])

  const { data, isFetching } = useQuery({
    queryKey: ['/calendrier', debut, fin],
    queryFn: () => api.get<{ evenements: EvenementCalendrier[] }>('/calendrier/', { debut, fin }),
    placeholderData: keepPreviousData,
  })

  // Un événement sur plusieurs jours apparaît sur chacun de ses jours.
  const parJour = useMemo(() => {
    const map = new Map<string, EvenementCalendrier[]>()
    for (const e of data?.evenements ?? []) {
      const d = new Date(`${e.debut}T00:00:00`)
      const f = new Date(`${e.fin}T00:00:00`)
      for (let cur = d; cur <= f && (cur.getTime() - d.getTime()) / 86_400_000 < 60; cur = new Date(cur.getFullYear(), cur.getMonth(), cur.getDate() + 1)) {
        const k = iso(cur)
        map.set(k, [...(map.get(k) ?? []), e])
      }
    }
    return map
  }, [data])

  const aujourdhui = iso(new Date())
  const titre = mois.toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' })
  const changer = (delta: number) => setMois((m) => new Date(m.getFullYear(), m.getMonth() + delta, 1))

  return (
    <>
      <PageHeader
        title="Calendrier"
        description="Séjours, loyers à payer, fins de bail et interventions."
        actions={
          <div className="flex items-center gap-1">
            <Button variant="outline" size="icon" aria-label="Mois précédent" onClick={() => changer(-1)}><ChevronLeft /></Button>
            <Button variant="outline" onClick={() => setMois(new Date(new Date().getFullYear(), new Date().getMonth(), 1))}>Aujourd&apos;hui</Button>
            <Button variant="outline" size="icon" aria-label="Mois suivant" onClick={() => changer(1)}><ChevronRight /></Button>
          </div>
        }
      />
      <div className="mb-3 flex flex-wrap items-center gap-3 text-xs">
        <h2 className="mr-2 text-lg font-semibold capitalize">{titre}</h2>
        {(Object.keys(LEGENDE) as CalendrierType[]).map((t) => (
          <span key={t} className={cn('rounded-full border px-2 py-0.5', COULEURS[t])}>{LEGENDE[t]}</span>
        ))}
        {isFetching && <span className="text-muted-foreground" role="status">Mise à jour…</span>}
      </div>

      <Card className="overflow-hidden">
        <div className="grid grid-cols-7 border-b bg-muted/50 text-center text-xs font-medium text-muted-foreground">
          {JOURS.map((j) => <div key={j} className="py-2">{j}</div>)}
        </div>
        <div className="grid grid-cols-7">
          {jours.map((d) => {
            const k = iso(d)
            const evts = parJour.get(k) ?? []
            const horsMois = d.getMonth() !== mois.getMonth()
            return (
              <div key={k} className={cn('min-h-24 border-b border-r p-1.5 text-xs sm:min-h-28', horsMois && 'bg-muted/30 text-muted-foreground')}>
                <span className={cn('mb-1 inline-flex h-6 w-6 items-center justify-center rounded-full', k === aujourdhui && 'bg-primary font-semibold text-primary-foreground')}>{d.getDate()}</span>
                <div className="space-y-0.5">
                  {evts.slice(0, MAX_PAR_JOUR).map((e) => (
                    <button
                      key={`${e.id}-${k}`}
                      title={e.titre}
                      onClick={() => navigate(e.url)}
                      className={cn('block w-full truncate rounded border px-1 py-0.5 text-left leading-tight transition-opacity hover:opacity-80', COULEURS[e.type])}
                    >
                      {e.titre}
                    </button>
                  ))}
                  {evts.length > MAX_PAR_JOUR && <span className="block px-1 text-muted-foreground">+{evts.length - MAX_PAR_JOUR} autre(s)</span>}
                </div>
              </div>
            )
          })}
        </div>
      </Card>
    </>
  )
}
