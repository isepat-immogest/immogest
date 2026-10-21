import { useQuery } from '@tanstack/react-query'
import { MoreHorizontal, Pencil, PiggyBank, Plus, Receipt, Trash2, TrendingUp } from 'lucide-react'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'

import { PageHeader, StatCard } from '@/components/common'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { FormDialog, type FieldDef } from '@/components/FormDialog'
import { ListShell } from '@/components/ListShell'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Select } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api } from '@/lib/api'
import { CATEGORIES_DEPENSE } from '@/lib/labels'
import { notifyError, useDelete, useList, useSave } from '@/lib/queries'
import type { Bien, Depense, ResumeFinance } from '@/lib/types'
import { formatDate, formatFCFA, toNumber } from '@/lib/utils'

const LABEL = Object.fromEntries(CATEGORIES_DEPENSE.map((c) => [c.value, c.label]))

export default function Depenses() {
  const [page, setPage] = useState(1)
  const [categorie, setCategorie] = useState('')
  const [bien, setBien] = useState('')
  const query = useList<Depense>('/depenses', { page, categorie, bien })
  const biens = useList<Bien>('/biens', { page_size: 200 })
  const resume = useQuery({ queryKey: ['/depenses', 'resume'], queryFn: () => api.get<ResumeFinance>('/depenses/resume/') })
  const save = useSave<Depense>('/depenses', ['/biens'])
  const remove = useDelete('/depenses', ['/biens'])
  const [editing, setEditing] = useState<Depense | 'new' | null>(null)
  const [deleting, setDeleting] = useState<Depense | null>(null)

  const fields: FieldDef[] = useMemo(() => [
    { name: 'bien', label: 'Bien', type: 'select', required: true, full: true, options: (biens.data?.results ?? []).map((b) => ({ value: b.id, label: `${b.nom} — ${b.ville}` })) },
    { name: 'libelle', label: 'Libellé', required: true, full: true },
    { name: 'categorie', label: 'Catégorie', type: 'select', required: true, options: CATEGORIES_DEPENSE },
    { name: 'montant', label: 'Montant (FCFA)', type: 'number', required: true },
    { name: 'date', label: 'Date', type: 'date', required: true },
    { name: 'notes', label: 'Notes', type: 'textarea' },
  ], [biens.data])

  const r = resume.data
  const total = toNumber(r?.depenses_12m)

  return (
    <>
      <PageHeader title="Dépenses et rentabilité" description="Suivez les charges de chaque bien (12 derniers mois)." actions={<Button onClick={() => setEditing('new')}><Plus /> Ajouter une dépense</Button>} />
      <div className="mb-4 grid gap-4 sm:grid-cols-3">
        <StatCard label="Revenus encaissés" value={formatFCFA(r?.revenus_12m)} tone="success" icon={<TrendingUp className="h-5 w-5" />} />
        <StatCard label="Dépenses" value={formatFCFA(r?.depenses_12m)} tone="warning" icon={<Receipt className="h-5 w-5" />} />
        <StatCard label="Résultat net" value={formatFCFA(r?.net_12m)} tone={toNumber(r?.net_12m) >= 0 ? 'success' : 'danger'} icon={<PiggyBank className="h-5 w-5" />} />
      </div>

      {r && r.par_categorie.length > 0 && (
        <Card className="mb-4">
          <CardHeader><CardTitle>Répartition par catégorie</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {r.par_categorie.map((c) => {
              const pct = total ? Math.round((toNumber(c.total) / total) * 100) : 0
              return (
                <div key={c.categorie} className="space-y-1">
                  <div className="flex justify-between text-sm"><span>{LABEL[c.categorie] ?? c.categorie}</span><span className="tabular-nums text-muted-foreground">{formatFCFA(c.total)} · {pct} %</span></div>
                  <div className="h-2 overflow-hidden rounded-full bg-muted" role="presentation"><div className="h-full rounded-full bg-primary transition-all duration-500" style={{ width: `${pct}%` }} /></div>
                </div>
              )
            })}
          </CardContent>
        </Card>
      )}

      <ListShell
        query={query}
        page={page}
        onPage={setPage}
        cols={5}
        emptyTitle="Aucune dépense"
        emptyDescription="Enregistrez taxes, assurances, travaux… pour connaître la rentabilité réelle de vos biens."
        emptyAction={<Button onClick={() => setEditing('new')}><Plus /> Ajouter une dépense</Button>}
        toolbar={
          <>
            <Select className="w-52" value={bien} onChange={(e) => { setBien(e.target.value); setPage(1) }} aria-label="Filtrer par bien">
              <option value="">Tous les biens</option>
              {(biens.data?.results ?? []).map((b) => <option key={b.id} value={b.id}>{b.nom}</option>)}
            </Select>
            <Select className="w-52" value={categorie} onChange={(e) => { setCategorie(e.target.value); setPage(1) }} aria-label="Filtrer par catégorie">
              <option value="">Toutes les catégories</option>
              {CATEGORIES_DEPENSE.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
            </Select>
          </>
        }
      >
        {(rows) => (
          <Table>
            <TableHeader><TableRow><TableHead>Date</TableHead><TableHead>Libellé</TableHead><TableHead>Bien</TableHead><TableHead>Catégorie</TableHead><TableHead>Montant</TableHead><TableHead className="w-10" /></TableRow></TableHeader>
            <TableBody>
              {rows.map((d) => (
                <TableRow key={d.id}>
                  <TableCell className="text-muted-foreground">{formatDate(d.date)}</TableCell>
                  <TableCell className="font-medium">{d.libelle}</TableCell>
                  <TableCell>{d.bien_nom}</TableCell>
                  <TableCell><Badge tone="outline">{d.categorie_display}</Badge></TableCell>
                  <TableCell className="tabular-nums">{formatFCFA(d.montant)}</TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild><Button variant="ghost" size="icon" aria-label="Actions"><MoreHorizontal /></Button></DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onSelect={() => setEditing(d)}><Pencil /> Modifier</DropdownMenuItem>
                        <DropdownMenuItem destructive onSelect={() => setDeleting(d)}><Trash2 /> Supprimer</DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </ListShell>

      <FormDialog
        open={editing !== null}
        onOpenChange={(o) => !o && setEditing(null)}
        title={editing === 'new' ? 'Ajouter une dépense' : 'Modifier la dépense'}
        fields={fields}
        defaultValues={editing && editing !== 'new' ? { ...editing } : { categorie: 'autre', date: new Date().toISOString().slice(0, 10) }}
        onSubmit={async (payload) => {
          await save.mutateAsync({ id: editing && editing !== 'new' ? editing.id : undefined, data: payload })
          toast.success('Dépense enregistrée.')
        }}
      />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        title="Supprimer cette dépense ?"
        description={`« ${deleting?.libelle ?? ''} » sera définitivement supprimée.`}
        confirmLabel="Supprimer"
        destructive
        loading={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting.id, { onSuccess: () => setDeleting(null), onError: notifyError })}
      />
    </>
  )
}
