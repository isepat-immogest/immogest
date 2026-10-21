import { Download, FileText, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/common'
import { FormDialog, type FieldDef } from '@/components/FormDialog'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { downloadFile } from '@/lib/api'
import { TYPES_DOCUMENT } from '@/lib/labels'
import { notifyError, useDelete, useList, useSave } from '@/lib/queries'
import type { DocumentPiece } from '@/lib/types'
import { formatDate } from '@/lib/utils'

const FIELDS: FieldDef[] = [
  { name: 'titre', label: 'Titre', required: true, full: true },
  { name: 'type_document', label: 'Type', type: 'select', required: true, options: TYPES_DOCUMENT },
  { name: 'date_expiration', label: "Date d'expiration", type: 'date', nullable: true },
  { name: 'fichier', label: 'Fichier (PDF, JPG ou PNG — 5 Mo max)', type: 'file', accept: '.pdf,.jpg,.jpeg,.png', full: true },
]

function taille(octets: number): string {
  if (octets < 1024) return `${octets} o`
  return octets < 1024 * 1024 ? `${Math.round(octets / 1024)} Ko` : `${(octets / 1024 / 1024).toFixed(1)} Mo`
}

/** Pièces jointes d'un bien ou d'un locataire (téléchargement authentifié, jamais d'URL publique). */
export function DocumentsPanel({ bien, locataire }: { bien?: number; locataire?: number }) {
  const query = useList<DocumentPiece>('/documents', { bien, locataire, page_size: 50 })
  const save = useSave<DocumentPiece>('/documents')
  const remove = useDelete('/documents')
  const [open, setOpen] = useState(false)
  const [deleting, setDeleting] = useState<DocumentPiece | null>(null)
  const docs = query.data?.results ?? []

  return (
    <Card>
      <CardContent className="space-y-3 pt-5">
        <div className="flex justify-end"><Button size="sm" onClick={() => setOpen(true)}><Plus /> Ajouter un document</Button></div>
        {docs.length === 0 && !query.isPending && <EmptyState title="Aucun document" description="Ajoutez pièce d'identité, bail signé, assurance…" icon={<FileText className="h-6 w-6" />} />}
        {docs.map((d) => (
          <div key={d.id} className="flex items-center gap-3 rounded-md border p-3 text-sm">
            <FileText className="h-5 w-5 shrink-0 text-muted-foreground" />
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">{d.titre}</p>
              <p className="truncate text-xs text-muted-foreground">{d.type_display} · {d.nom_fichier} · {taille(d.taille)} · {formatDate(d.created_at)}{d.date_expiration ? ` · expire le ${formatDate(d.date_expiration)}` : ''}</p>
            </div>
            <Button variant="ghost" size="icon" aria-label={`Télécharger ${d.titre}`} onClick={() => downloadFile(`/documents/${d.id}/telecharger/`, undefined, d.nom_fichier).catch(notifyError)}><Download /></Button>
            <Button variant="ghost" size="icon" className="text-destructive" aria-label={`Supprimer ${d.titre}`} onClick={() => setDeleting(d)}><Trash2 /></Button>
          </div>
        ))}
      </CardContent>

      <FormDialog
        open={open}
        onOpenChange={setOpen}
        title="Ajouter un document"
        fields={FIELDS}
        defaultValues={{ type_document: 'autre' }}
        onSubmit={async (payload) => {
          const data = payload instanceof FormData ? payload : { ...payload }
          if (data instanceof FormData) {
            if (bien) data.append('bien', String(bien))
            if (locataire) data.append('locataire', String(locataire))
          } else {
            toast.error('Sélectionnez un fichier.')
            throw new Error('Sélectionnez un fichier.')
          }
          await save.mutateAsync({ data })
          toast.success('Document ajouté.')
        }}
      />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        title="Supprimer ce document ?"
        description={`« ${deleting?.titre ?? ''} » sera définitivement supprimé.`}
        confirmLabel="Supprimer"
        destructive
        loading={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting.id, { onSuccess: () => setDeleting(null) })}
      />
    </Card>
  )
}
