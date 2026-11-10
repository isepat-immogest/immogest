import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Users } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input, Select } from '@/components/ui/input'
import { api, ApiError } from '@/lib/api'
import { useProprietaires } from '@/lib/catalogues'
import { invalidateAll } from '@/lib/queries'
import type { Bien } from '@/lib/types'

interface Ligne {
  proprietaire: string
  quote_part: string
}

/** Propriétaires d'un bien et leurs quotes-parts (indivision) : la somme doit valoir exactement 100 %. */
export function ProprietairesPanel({ bien }: { bien: Bien }) {
  const qc = useQueryClient()
  const proprietaires = useProprietaires()
  const depart = (): Ligne[] => bien.proprietaires_detail.map((p) => ({ proprietaire: String(p.proprietaire), quote_part: String(Number(p.quote_part)) }))
  const [lignes, setLignes] = useState<Ligne[]>(depart)
  const [erreur, setErreur] = useState('')

  useEffect(() => {
    setLignes(depart())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bien.proprietaires_detail])

  const total = lignes.reduce((t, l) => t + (Number(l.quote_part) || 0), 0)
  const ok = lignes.length === 0 || Math.abs(total - 100) < 0.005
  const options = proprietaires.data?.results ?? []

  const enregistrer = useMutation({
    mutationFn: () =>
      api.put(`/biens/${bien.id}/proprietaires/`, {
        parts: lignes.map((l) => ({ proprietaire: Number(l.proprietaire), quote_part: Number(l.quote_part) })),
      }),
    onSuccess: () => {
      invalidateAll(qc, '/biens', '/proprietaires')
      toast.success('Propriétaires enregistrés.')
      setErreur('')
    },
    onError: (e) => setErreur(e instanceof ApiError ? e.message : 'Enregistrement impossible.'),
  })

  const modifie = JSON.stringify(lignes) !== JSON.stringify(depart())
  const maj = (i: number, patch: Partial<Ligne>) => setLignes((ls) => ls.map((l, k) => (k === i ? { ...l, ...patch } : l)))
  const repartir = (liste: Ligne[]) => {
    const part = Math.floor((10000 / liste.length)) / 100
    const reste = Math.round((100 - part * liste.length) * 100) / 100
    return liste.map((l, i) => ({ ...l, quote_part: String(i === 0 ? Math.round((part + reste) * 100) / 100 : part) }))
  }

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="flex items-center gap-2"><Users className="h-4 w-4" /> Propriétaires</CardTitle>
        <Badge tone={lignes.length === 0 ? 'warning' : ok ? 'success' : 'danger'}>
          {lignes.length === 0 ? 'Non renseigné' : `${total} % réparti`}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-3">
        {lignes.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Aucun propriétaire. {options.length === 0 && <>Commencez par <Link className="text-primary hover:underline" to="/proprietaires">créer un propriétaire</Link>.</>}
          </p>
        )}
        {lignes.map((l, i) => (
          <div key={i} className="flex items-center gap-2">
            <Select className="flex-1" value={l.proprietaire} onChange={(e) => maj(i, { proprietaire: e.target.value })} aria-label={`Propriétaire ${i + 1}`}>
              <option value="">Choisir…</option>
              {options.map((p) => (
                <option key={p.id} value={p.id} disabled={lignes.some((x, k) => k !== i && x.proprietaire === String(p.id))}>{p.nom_complet}</option>
              ))}
            </Select>
            <div className="relative w-28">
              <Input type="number" min="0.01" max="100" step="0.01" className="pr-7 text-right" value={l.quote_part} onChange={(e) => maj(i, { quote_part: e.target.value })} aria-label={`Quote-part ${i + 1}`} />
              <span className="pointer-events-none absolute right-3 top-2.5 text-sm text-muted-foreground">%</span>
            </div>
            <Button variant="ghost" size="icon" aria-label="Retirer ce propriétaire" onClick={() => setLignes((ls) => ls.filter((_, k) => k !== i))}><Trash2 /></Button>
          </div>
        ))}
        {!ok && <p role="alert" className="text-sm text-destructive">Les parts totalisent {total} % : elles doivent faire exactement 100 %.</p>}
        {erreur && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{erreur}</p>}
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" disabled={lignes.length >= options.length} onClick={() => setLignes((ls) => repartir([...ls, { proprietaire: '', quote_part: '0' }]))}>
            <Plus /> Ajouter un propriétaire
          </Button>
          {lignes.length > 1 && <Button variant="ghost" size="sm" onClick={() => setLignes((ls) => repartir(ls))}>Parts égales</Button>}
          <Button size="sm" className="ml-auto" disabled={!modifie || !ok || lignes.some((l) => !l.proprietaire)} loading={enregistrer.isPending} onClick={() => enregistrer.mutate()}>
            Enregistrer
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
