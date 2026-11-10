import { useMutation, useQuery } from '@tanstack/react-query'
import { FileText, MoreHorizontal, Pencil, Plus, Search, Send, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'

import { PageHeader } from '@/components/common'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { FormDialog, type FieldDef } from '@/components/FormDialog'
import { ListShell } from '@/components/ListShell'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useDebounce } from '@/hooks/useDebounce'
import { api } from '@/lib/api'
import { notifyError, useDelete, useList, useSave } from '@/lib/queries'
import { ApiError } from '@/lib/api'
import type { Proprietaire, ReleveProprietaire } from '@/lib/types'
import { formatFCFA, formatMois } from '@/lib/utils'

const FIELDS: FieldDef[] = [
  { name: 'type_proprietaire', label: 'Type', type: 'select', required: true, options: [{ value: 'personne', label: 'Personne physique' }, { value: 'societe', label: 'Société / SCI' }] },
  { name: 'prenom', label: 'Prénom', hint: 'Laisser vide pour une société.' },
  { name: 'nom', label: 'Nom ou raison sociale', required: true, full: true },
  { name: 'telephone', label: 'Téléphone', type: 'tel', required: true, placeholder: '+221 77 123 45 67' },
  { name: 'whatsapp', label: 'WhatsApp', type: 'tel', hint: 'Laisser vide si identique au téléphone.' },
  { name: 'email', label: 'Email', type: 'email' },
  { name: 'adresse', label: 'Adresse' },
  { name: 'commission_pct', label: 'Commission de gestion (%)', type: 'number', required: true, hint: 'Prélevée sur les loyers encaissés.' },
  { name: 'compte_reversement', label: 'Compte de reversement', hint: 'Numéro Wave / Orange Money ou IBAN.' },
  { name: 'notif_email', label: 'Email', type: 'checkbox', hint: 'Recevoir ses relevés et ses loyers encaissés par email' },
  { name: 'notif_whatsapp', label: 'WhatsApp', type: 'checkbox', hint: 'Recevoir ses relevés et ses loyers encaissés par WhatsApp (avec son accord)' },
  { name: 'actif', label: 'Actif', type: 'checkbox', hint: 'Propose ce propriétaire lors de la création des biens' },
  { name: 'notes', label: 'Notes', type: 'textarea' },
]

const DEFAUTS = { type_proprietaire: 'personne', commission_pct: 10, actif: true, notif_email: true, notif_whatsapp: false }

function moisCourant() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
}

/** Décompte de reversement : part des loyers encaissés, commission, dépenses, net à reverser. */
function ReleveDialog({ proprietaire, onClose }: { proprietaire: Proprietaire | null; onClose: () => void }) {
  const [mois, setMois] = useState(moisCourant())
  const releve = useQuery({
    queryKey: ['/proprietaires', 'releve', proprietaire?.id, mois],
    queryFn: () => api.get<ReleveProprietaire>(`/proprietaires/${proprietaire?.id}/releve/`, { mois }),
    enabled: !!proprietaire,
  })
  const r = releve.data
  const envoyer = useMutation({
    mutationFn: () => api.post<{ resultats: { canal: string; adresse: string; statut: string; erreur: string }[] }>(
      `/proprietaires/${proprietaire?.id}/envoyer-releve/?mois=${mois}`),
    onSuccess: (res) => res.resultats.forEach((x) => {
      const nom = x.canal === 'email' ? 'Email' : 'WhatsApp'
      if (x.statut === 'envoye') toast.success(`${nom} envoyé à ${x.adresse}.`)
      else toast.error(`${nom} : ${x.erreur || 'non envoyé'}`)
    }),
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Envoi impossible."),
  })
  return (
    <Dialog open={proprietaire !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Relevé de reversement — {proprietaire?.nom_complet}</DialogTitle>
          <DialogDescription>Commission de gestion : {proprietaire?.commission_pct} % des loyers encaissés.</DialogDescription>
        </DialogHeader>
        <div className="flex items-center gap-3">
          <label htmlFor="mois-releve" className="text-sm font-medium">Mois</label>
          <Input id="mois-releve" type="month" className="w-48" value={mois.slice(0, 7)} onChange={(e) => e.target.value && setMois(`${e.target.value}-01`)} />
          <span className="text-sm capitalize text-muted-foreground">{formatMois(mois)}</span>
          <Button variant="outline" size="sm" className="ml-auto" loading={envoyer.isPending} disabled={!r || r.lignes.length === 0} onClick={() => envoyer.mutate()}>
            <Send /> Envoyer au propriétaire
          </Button>
        </div>
        {releve.isPending ? <p className="py-6 text-center text-sm text-muted-foreground">Calcul…</p> : !r || r.lignes.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">Ce propriétaire n&apos;a aucun bien associé.</p>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Bien</TableHead><TableHead>Part</TableHead><TableHead>Loyers (sa part)</TableHead>
                <TableHead>Commission</TableHead><TableHead>Dépenses</TableHead><TableHead>Net à reverser</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {r.lignes.map((l) => (
                  <TableRow key={l.bien}>
                    <TableCell className="font-medium">{l.bien_nom}</TableCell>
                    <TableCell>{Number(l.quote_part)} %</TableCell>
                    <TableCell className="tabular-nums">{formatFCFA(l.encaisse_part)}</TableCell>
                    <TableCell className="tabular-nums">−{formatFCFA(l.commission)}</TableCell>
                    <TableCell className="tabular-nums">−{formatFCFA(l.depenses_part)}</TableCell>
                    <TableCell className="tabular-nums font-semibold">{formatFCFA(l.net)}</TableCell>
                  </TableRow>
                ))}
                <TableRow className="bg-muted/40 font-semibold">
                  <TableCell colSpan={2}>Total</TableCell>
                  <TableCell className="tabular-nums">{formatFCFA(r.totaux.encaisse_part)}</TableCell>
                  <TableCell className="tabular-nums">−{formatFCFA(r.totaux.commission)}</TableCell>
                  <TableCell className="tabular-nums">−{formatFCFA(r.totaux.depenses_part)}</TableCell>
                  <TableCell className="tabular-nums">{formatFCFA(r.totaux.net)}</TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

export default function Proprietaires() {
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const q = useDebounce(search)
  const query = useList<Proprietaire>('/proprietaires', { page, search: q })
  const save = useSave<Proprietaire>('/proprietaires', ['/biens'])
  const remove = useDelete('/proprietaires', ['/biens'])
  const [editing, setEditing] = useState<Proprietaire | 'new' | null>(null)
  const [deleting, setDeleting] = useState<Proprietaire | null>(null)
  const [releve, setReleve] = useState<Proprietaire | null>(null)

  return (
    <>
      <PageHeader
        title="Propriétaires"
        description="Les propriétaires des biens que vous gérez. Un bien peut en avoir plusieurs (indivision, héritiers…), chacun avec sa quote-part."
        actions={<Button onClick={() => setEditing('new')}><Plus /> Ajouter un propriétaire</Button>}
      />
      <ListShell
        query={query}
        page={page}
        onPage={setPage}
        cols={6}
        emptyTitle="Aucun propriétaire"
        emptyDescription="Ajoutez les propriétaires pour leur associer des biens et calculer leurs reversements."
        emptyAction={<Button onClick={() => setEditing('new')}><Plus /> Ajouter un propriétaire</Button>}
        toolbar={
          <div className="relative min-w-52 flex-1">
            <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
            <Input className="pl-9" placeholder="Rechercher (nom, téléphone, email)…" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }} aria-label="Rechercher un propriétaire" />
          </div>
        }
      >
        {(rows) => (
          <Table>
            <TableHeader><TableRow>
              <TableHead>Propriétaire</TableHead><TableHead>Contact</TableHead><TableHead>Biens</TableHead>
              <TableHead>Commission</TableHead><TableHead>Statut</TableHead><TableHead className="w-10" />
            </TableRow></TableHeader>
            <TableBody>
              {rows.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>
                    <p className="font-medium">{p.nom_complet}</p>
                    <p className="text-xs text-muted-foreground">{p.type_display}</p>
                  </TableCell>
                  <TableCell className="text-sm">{p.telephone}{p.email && <span className="block text-xs text-muted-foreground">{p.email}</span>}</TableCell>
                  <TableCell className="text-sm">
                    {p.biens_detail.length ? p.biens_detail.map((b) => (
                      <Link key={b.id} to={`/biens/${b.id}`} className="block hover:underline">{b.nom} <span className="text-muted-foreground">({Number(b.quote_part)} %)</span></Link>
                    )) : <span className="text-muted-foreground">Aucun</span>}
                  </TableCell>
                  <TableCell className="tabular-nums">{Number(p.commission_pct)} %</TableCell>
                  <TableCell><Badge tone={p.actif ? 'success' : 'neutral'}>{p.actif ? 'Actif' : 'Inactif'}</Badge></TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild><Button variant="ghost" size="icon" aria-label={`Actions pour ${p.nom_complet}`}><MoreHorizontal /></Button></DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onSelect={() => setReleve(p)}><FileText /> Relevé de reversement</DropdownMenuItem>
                        <DropdownMenuItem onSelect={() => setEditing(p)}><Pencil /> Modifier</DropdownMenuItem>
                        <DropdownMenuItem destructive onSelect={() => setDeleting(p)}><Trash2 /> Supprimer</DropdownMenuItem>
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
        title={editing === 'new' ? 'Ajouter un propriétaire' : 'Modifier le propriétaire'}
        fields={FIELDS}
        defaultValues={editing && editing !== 'new' ? { ...editing } : DEFAUTS}
        onSubmit={async (payload) => {
          await save.mutateAsync({ id: editing && editing !== 'new' ? editing.id : undefined, data: payload })
          toast.success('Propriétaire enregistré.')
        }}
      />
      <ReleveDialog proprietaire={releve} onClose={() => setReleve(null)} />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        title="Supprimer ce propriétaire ?"
        description={`« ${deleting?.nom_complet ?? ''} » sera supprimé. Impossible s'il possède encore des biens : retirez-le d'abord de chaque bien.`}
        confirmLabel="Supprimer"
        destructive
        loading={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting.id, { onSuccess: () => setDeleting(null), onError: (e) => { setDeleting(null); notifyError(e) } })}
      />
    </>
  )
}
