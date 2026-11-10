import { MoreHorizontal, Pencil, Plus, Search, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { PageHeader } from '@/components/common'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { FormDialog, type FieldDef } from '@/components/FormDialog'
import { ListShell } from '@/components/ListShell'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useDebounce } from '@/hooks/useDebounce'
import { notifyError, useDelete, useList, useSave } from '@/lib/queries'
import type { Locataire } from '@/lib/types'
import { formatFCFA } from '@/lib/utils'

export const LOCATAIRE_FIELDS: FieldDef[] = [
  { name: 'prenom', label: 'Prénom', required: true },
  { name: 'nom', label: 'Nom', required: true },
  { name: 'telephone', label: 'Téléphone', type: 'tel', required: true, placeholder: '+221 77 123 45 67' },
  { name: 'email', label: 'Email', type: 'email', hint: "Nécessaire pour envoyer l'invitation à l'espace locataire." },
  { name: 'date_naissance', label: 'Date de naissance', type: 'date', nullable: true },
  { name: 'notif_whatsapp', label: 'WhatsApp', type: 'checkbox', hint: 'Le locataire accepte les messages WhatsApp (reçus de paiement, rappels de loyer)' },
  { name: 'profession', label: 'Profession' },
  { name: 'revenu_mensuel', label: 'Revenu mensuel (FCFA)', type: 'number', nullable: true },
  { name: 'adresse_precedente', label: 'Adresse précédente' },
  { name: 'notes', label: 'Notes', type: 'textarea' },
]

export default function Locataires() {
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const q = useDebounce(search)
  const query = useList<Locataire>('/locataires', { page, search: q })
  const save = useSave<Locataire>('/locataires')
  const remove = useDelete('/locataires')
  const [editing, setEditing] = useState<Locataire | 'new' | null>(null)
  const [deleting, setDeleting] = useState<Locataire | null>(null)

  return (
    <>
      <PageHeader title="Locataires" description="Fiches et accès à l'espace locataire." actions={<Button onClick={() => setEditing('new')}><Plus /> Ajouter un locataire</Button>} />
      <ListShell
        query={query}
        page={page}
        onPage={setPage}
        emptyTitle="Aucun locataire"
        emptyAction={<Button onClick={() => setEditing('new')}><Plus /> Ajouter un locataire</Button>}
        toolbar={
          <div className="relative min-w-52 flex-1">
            <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
            <Input className="pl-9" placeholder="Rechercher (nom, email, téléphone)…" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }} aria-label="Rechercher un locataire" />
          </div>
        }
      >
        {(rows) => (
          <Table>
            <TableHeader>
              <TableRow><TableHead>Locataire</TableHead><TableHead>Contact</TableHead><TableHead>Bien loué</TableHead><TableHead>Accès</TableHead><TableHead className="w-10" /></TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((l) => (
                <TableRow key={l.id}>
                  <TableCell>
                    <Link to={`/locataires/${l.id}`} className="flex items-center gap-3 font-medium hover:underline">
                      <span className="flex h-9 w-9 items-center justify-center rounded-full bg-accent text-xs font-semibold text-accent-foreground">{l.initiales}</span>
                      {l.nom_complet}
                    </Link>
                  </TableCell>
                  <TableCell><p>{l.telephone}</p><p className="text-xs text-muted-foreground">{l.email}</p></TableCell>
                  <TableCell>{l.contrat_actif ? <>{l.contrat_actif.bien}<p className="text-xs text-muted-foreground">{formatFCFA(l.contrat_actif.loyer_total)}</p></> : <span className="text-muted-foreground">—</span>}</TableCell>
                  <TableCell>{l.a_un_acces ? <Badge tone={l.acces_actif ? 'success' : 'neutral'}>{l.acces_actif ? 'Actif' : 'Désactivé'}</Badge> : <Badge tone="outline">Aucun</Badge>}</TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild><Button variant="ghost" size="icon" aria-label={`Actions pour ${l.nom_complet}`}><MoreHorizontal /></Button></DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onSelect={() => setEditing(l)}><Pencil /> Modifier</DropdownMenuItem>
                        <DropdownMenuItem destructive onSelect={() => setDeleting(l)}><Trash2 /> Supprimer</DropdownMenuItem>
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
        title={editing === 'new' ? 'Ajouter un locataire' : 'Modifier le locataire'}
        fields={LOCATAIRE_FIELDS}
        defaultValues={editing && editing !== 'new' ? { ...editing } : {}}
        onSubmit={async (payload) => {
          await save.mutateAsync({ id: editing && editing !== 'new' ? editing.id : undefined, data: payload })
          toast.success(editing === 'new' ? 'Locataire ajouté.' : 'Locataire modifié.')
        }}
      />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        title="Supprimer ce locataire ?"
        description={`« ${deleting?.nom_complet ?? ''} » ainsi que ses contrats et paiements seront définitivement supprimés.`}
        confirmLabel="Supprimer"
        destructive
        loading={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting.id, { onSuccess: () => setDeleting(null), onError: notifyError })}
      />
    </>
  )
}
