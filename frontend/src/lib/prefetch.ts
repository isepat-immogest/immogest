import type { QueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'

type Params = Record<string, string | number>

/** Paramètres par défaut de chaque liste : doivent rester identiques à ceux des pages pour partager le cache. */
const LISTES: Record<string, { path: string; params: Params }> = {
  '/biens': { path: '/biens', params: { page: 1, search: '', statut: '' } },
  '/locataires': { path: '/locataires', params: { page: 1, search: '' } },
  '/contrats': { path: '/contrats', params: { page: 1, statut: '' } },
  '/paiements': { path: '/paiements', params: { page: 1, statut: '' } },
  '/reservations': { path: '/reservations', params: { page: 1, statut: '' } },
  '/demandes': { path: '/demandes', params: { page: 1, traite: 'false' } },
  '/depenses': { path: '/depenses', params: { page: 1, categorie: '', bien: '' } },
  '/interventions': { path: '/interventions', params: { page_size: 200, ordering: '-poids' } },
}

const FRAICHEUR_MS = 30_000

/** Charge à l'avance les données d'une page (au survol du menu) : l'affichage est alors instantané. */
export function prefetchRoute(qc: QueryClient, to: string): void {
  if (to === '/') {
    void qc.prefetchQuery({ queryKey: ['/dashboard'], queryFn: () => api.get('/dashboard/'), staleTime: FRAICHEUR_MS })
    return
  }
  const liste = LISTES[to]
  if (!liste) return
  void qc.prefetchQuery({
    queryKey: [liste.path, 'list', liste.params],
    queryFn: () => api.get(`${liste.path}/`, liste.params),
    staleTime: FRAICHEUR_MS,
  })
}

/** Précharge en arrière-plan, pendant les temps morts du navigateur, les pages les plus utilisées. */
export function prefetchWhenIdle(tasks: Array<() => unknown>): () => void {
  let annule = false
  const schedule: (cb: () => void) => number =
    'requestIdleCallback' in window
      ? (cb) => window.requestIdleCallback(cb, { timeout: 4000 })
      : (cb) => window.setTimeout(cb, 1500)
  const run = (i: number) => {
    if (annule || i >= tasks.length) return
    schedule(() => {
      if (annule) return
      void tasks[i]()
      run(i + 1)
    })
  }
  run(0)
  return () => {
    annule = true
  }
}
