import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowUpToLine, ImagePlus, Pencil, Trash2 } from 'lucide-react'
import { useRef } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { api, ApiError } from '@/lib/api'
import { invalidateAll } from '@/lib/queries'

interface Photo {
  id: number | null
  url: string
  legende: string
  principale: boolean
  couverture: boolean
}

/** Galerie photos d'un bien (modèle BienPhoto) : voir, ajouter plusieurs photos, légender, mettre en tête, supprimer. */
export function GaleriePanel({ bienId, nom }: { bienId: number; nom: string }) {
  const qc = useQueryClient()
  const champ = useRef<HTMLInputElement>(null)
  const cle = ['/biens', 'galerie', bienId]
  const galerie = useQuery({ queryKey: cle, queryFn: () => api.get<Photo[]>(`/biens/${bienId}/galerie/`) })
  const photos = galerie.data ?? []

  // Chaque action renvoie la galerie à jour ; on rafraîchit aussi les listes (vignette de couverture).
  const succes = (message: string) => (data: Photo[]) => {
    qc.setQueryData(cle, data)
    invalidateAll(qc, '/biens')
    toast.success(message)
  }
  const erreur = (e: unknown) => toast.error(e instanceof ApiError ? e.message : 'Opération impossible.')

  const ajouter = useMutation({
    mutationFn: (fichiers: File[]) => {
      const fd = new FormData()
      fichiers.forEach((f) => fd.append('images', f))
      return api.post<Photo[]>(`/biens/${bienId}/galerie/`, fd)
    },
    onSuccess: (data, fichiers) => succes(`${fichiers.length} photo(s) ajoutée(s).`)(data),
    onError: erreur,
  })
  const supprimer = useMutation({
    mutationFn: (id: number | null) => api.delete(`/biens/${bienId}/galerie/${id ?? 'principale'}/`),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['/biens'] }); toast.success('Photo supprimée.') },
    onError: erreur,
  })
  const enTete = useMutation({
    mutationFn: (id: number) => api.post<Photo[]>(`/biens/${bienId}/galerie/${id}/en-tete/`),
    onSuccess: succes('Photo placée en première position.'),
    onError: erreur,
  })
  const legender = useMutation({
    mutationFn: ({ id, legende }: { id: number; legende: string }) => api.patch<Photo[]>(`/biens/${bienId}/galerie/${id}/`, { legende }),
    onSuccess: succes('Légende enregistrée.'),
    onError: erreur,
  })

  const choisir = (liste: FileList | null) => {
    const fichiers = Array.from(liste ?? [])
    if (champ.current) champ.current.value = ''
    if (fichiers.length > 0) ajouter.mutate(fichiers)
  }

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="flex items-center gap-2">
          <ImagePlus className="h-4 w-4" /> Galerie <span className="text-sm font-normal text-muted-foreground">({photos.length})</span>
        </CardTitle>
        <div>
          <input ref={champ} type="file" accept="image/*" multiple className="sr-only" onChange={(e) => choisir(e.target.files)} />
          <Button size="sm" loading={ajouter.isPending} onClick={() => champ.current?.click()}>
            <ImagePlus /> Ajouter des photos
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {galerie.isPending ? (
          <p className="text-sm text-muted-foreground">Chargement…</p>
        ) : photos.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Aucune photo. Ajoutez-en plusieurs d&apos;un coup : la première sert de couverture dans les listes et sur le site public.
          </p>
        ) : (
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {photos.map((p, i) => (
              <li key={p.id ?? 'principale'} className="group relative overflow-hidden rounded-lg border bg-muted">
                <a href={p.url} target="_blank" rel="noopener noreferrer">
                  <img src={p.url} alt={p.legende || `Photo ${i + 1} de ${nom}`} loading="lazy" className="h-32 w-full object-cover" />
                </a>
                {p.couverture && <Badge tone="success" className="absolute left-2 top-2">Couverture</Badge>}
                {p.legende && <p className="truncate bg-background/80 px-2 py-1 text-xs">{p.legende}</p>}
                <div className="absolute right-1 top-1 flex gap-1 opacity-100 sm:opacity-0 sm:transition-opacity sm:group-focus-within:opacity-100 sm:group-hover:opacity-100">
                  {p.id !== null && !p.couverture && (
                    <Button variant="secondary" size="icon" className="h-8 w-8" aria-label="Placer en première position" title="Placer en première position" onClick={() => enTete.mutate(p.id as number)}><ArrowUpToLine /></Button>
                  )}
                  {p.id !== null && (
                    <Button variant="secondary" size="icon" className="h-8 w-8" aria-label="Modifier la légende" title="Légende" onClick={() => { const l = window.prompt('Légende de la photo (ex. Salon, Façade) :', p.legende); if (l !== null) legender.mutate({ id: p.id as number, legende: l }) }}><Pencil /></Button>
                  )}
                  <Button variant="secondary" size="icon" className="h-8 w-8" aria-label="Supprimer cette photo" title="Supprimer" onClick={() => { if (window.confirm('Supprimer cette photo ?')) supprimer.mutate(p.id) }}><Trash2 /></Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
