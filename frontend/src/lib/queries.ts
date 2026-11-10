import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query'
import { toast } from 'sonner'

import { api, ApiError } from '@/lib/api'
import type { Paginated } from '@/lib/types'

type Params = Record<string, string | number | boolean | undefined | null>

/** Liste paginée : la page précédente reste affichée pendant le chargement de la suivante (navigation fluide). */
export function useList<T, P = Paginated<T>>(path: string, params: Params = {}, refetchInterval?: number) {
  return useQuery({
    queryKey: [path, 'list', params],
    queryFn: () => api.get<P>(path + '/', params),
    placeholderData: keepPreviousData,
    refetchInterval,
  })
}

export function useDetail<T>(path: string, id: number | string | undefined) {
  return useQuery({
    queryKey: [path, 'detail', String(id)],
    queryFn: () => api.get<T>(`${path}/${id}/`),
    enabled: id !== undefined && id !== '',
  })
}

/** Invalide les listes/détails d'une ressource et les agrégats qui en dépendent. */
export function invalidateAll(qc: QueryClient, ...paths: string[]) {
  for (const p of [...paths, '/dashboard', '/espace']) qc.invalidateQueries({ queryKey: [p] })
}

export function notifyError(error: unknown) {
  if (error instanceof ApiError && error.code === 'validation_error') return // affiché dans le formulaire
  toast.error(error instanceof Error ? error.message : 'Une erreur est survenue.')
}

export function useSave<T>(path: string, related: string[] = []) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id?: number; data: unknown }) =>
      id ? api.patch<T>(`${path}/${id}/`, data) : api.post<T>(`${path}/`, data),
    onSuccess: () => invalidateAll(qc, path, ...related),
  })
}

export function useDelete(path: string, related: string[] = []) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.delete(`${path}/${id}/`),
    onSuccess: () => {
      invalidateAll(qc, path, ...related)
      toast.success('Supprimé.')
    },
    // « Ce bien a un contrat actif… » : refus métier, à montrer (notifyError ignore les erreurs de formulaire).
    onError: (error) => {
      if (error instanceof ApiError && error.code === 'validation_error') toast.error(error.message)
    },
  })
}

/**
 * Action sur un élément (POST /ressource/{id}/{action}/) avec mise à jour optimiste :
 * l'interface réagit immédiatement et revient en arrière si le serveur refuse.
 */
export function useItemAction<T extends { id: number }>(path: string, related: string[] = []) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, action, body }: { id: number; action: string; body?: unknown; optimistic?: Partial<T> }) =>
      api.post<T>(`${path}/${id}/${action}/`, body),
    onMutate: async ({ id, optimistic }) => {
      if (!optimistic) return { snapshots: [] as [readonly unknown[], unknown][] }
      await qc.cancelQueries({ queryKey: [path] })
      const snapshots = qc.getQueriesData<Paginated<T>>({ queryKey: [path, 'list'] })
      qc.setQueriesData<Paginated<T>>({ queryKey: [path, 'list'] }, (old) =>
        old ? { ...old, results: old.results.map((r) => (r.id === id ? { ...r, ...optimistic } : r)) } : old,
      )
      return { snapshots }
    },
    onError: (error, _vars, ctx) => {
      ctx?.snapshots.forEach(([key, data]) => qc.setQueryData<unknown>(key, data))
      notifyError(error)
    },
    onSettled: () => invalidateAll(qc, path, ...related),
  })
}
