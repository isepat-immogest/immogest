import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Pencil } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { toast } from 'sonner'

import { EmptyState, ErrorState, PageHeader, StatusBadge } from '@/components/common'
import { DocumentsPanel } from '@/components/DocumentsPanel'
import { FormDialog } from '@/components/FormDialog'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api } from '@/lib/api'
import { STATUT_BIEN, STATUT_CONTRAT, STATUT_INTERVENTION, STATUT_PAIEMENT, PRIORITE } from '@/lib/labels'
import { useDetail, useList, useSave } from '@/lib/queries'
import type { Bien, Contrat, Intervention, Paiement, Rentabilite } from '@/lib/types'
import { formatDate, formatFCFA, formatMois } from '@/lib/utils'
import { BIEN_FIELDS } from '@/pages/Biens'

function Info({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium">{value || '—'}</dd>
    </div>
  )
}

export default function BienDetail() {
  const { id } = useParams()
  const bien = useDetail<Bien>('/biens', id)
  const contrats = useList<Contrat>('/contrats', { bien: id, page_size: 50 })
  const paiements = useList<Paiement>('/paiements', { bien: id, ordering: '-mois', page_size: 12 })
  const interventions = useList<Intervention>('/interventions', { bien: id, page_size: 50 })
  const rentabilite = useQuery({ queryKey: ['/biens', 'rentabilite', id], queryFn: () => api.get<Rentabilite>(`/biens/${id}/rentabilite/`), enabled: !!id })
  const save = useSave<Bien>('/biens')
  const [editing, setEditing] = useState(false)

  if (bien.isError) return <ErrorState message="Bien introuvable." />
  if (bien.isPending) return <Skeleton className="h-96" />
  const b = bien.data

  return (
    <>
      <Button variant="ghost" size="sm" asChild className="mb-3"><Link to="/biens"><ArrowLeft /> Biens</Link></Button>
      <PageHeader
        title={b.nom}
        description={`${b.adresse}, ${b.ville}`}
        actions={<><StatusBadge map={STATUT_BIEN} value={b.statut} /><Button variant="outline" onClick={() => setEditing(true)}><Pencil /> Modifier</Button></>}
      />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="overflow-hidden lg:col-span-1">
          {b.photo ? <img src={b.photo} alt={b.nom} className="h-52 w-full object-cover" /> : <div className="flex h-52 items-center justify-center bg-muted text-muted-foreground">Pas de photo</div>}
          <CardContent className="pt-4">
            <dl className="grid grid-cols-2 gap-4">
              <Info label="Type" value={b.type_display} />
              <Info label="Surface" value={`${b.surface} m²`} />
              <Info label="Pièces" value={b.nb_pieces} />
              <Info label="Étage" value={b.etage} />
              <Info label="Loyer" value={formatFCFA(b.loyer_charges)} />
              <Info label="Dépôt de garantie" value={formatFCFA(b.depot_garantie)} />
              <Info label="Tarif / nuit" value={b.prix_nuit ? formatFCFA(b.prix_nuit) : null} />
              <Info label="Locataire" value={b.locataire_actuel ? <Link className="text-primary hover:underline" to={`/locataires/${b.locataire_actuel.id}`}>{b.locataire_actuel.nom}</Link> : null} />
            </dl>
            {b.description && <p className="mt-4 text-sm text-muted-foreground">{b.description}</p>}
          </CardContent>
        </Card>
        <Card className="lg:col-span-1">
          <CardHeader><CardTitle>Rentabilité (12 mois)</CardTitle></CardHeader>
          <CardContent>
            {rentabilite.data ? (
              <dl className="grid grid-cols-2 gap-4">
                <Info label="Revenus encaissés" value={formatFCFA(rentabilite.data.revenus_12m)} />
                <Info label="Dépenses" value={formatFCFA(rentabilite.data.depenses_12m)} />
                <Info label="Résultat net" value={<span className={Number(rentabilite.data.net_12m) >= 0 ? 'text-success' : 'text-destructive'}>{formatFCFA(rentabilite.data.net_12m)}</span>} />
                <Info label="Rendement net" value={rentabilite.data.rendement_net_pct !== null ? `${rentabilite.data.rendement_net_pct} %` : null} />
              </dl>
            ) : <Skeleton className="h-20" />}
            {rentabilite.data && rentabilite.data.rendement_net_pct === null && <p className="mt-3 text-xs text-muted-foreground">Renseignez le prix d&apos;acquisition du bien pour calculer le rendement.</p>}
          </CardContent>
        </Card>

        <div className="lg:col-span-2">
          <Tabs defaultValue="paiements">
            <TabsList>
              <TabsTrigger value="paiements">Paiements</TabsTrigger>
              <TabsTrigger value="contrats">Contrats</TabsTrigger>
              <TabsTrigger value="interventions">Interventions</TabsTrigger>
              <TabsTrigger value="documents">Documents</TabsTrigger>
            </TabsList>
            <TabsContent value="documents"><DocumentsPanel bien={b.id} /></TabsContent>
            <TabsContent value="paiements">
              <Card><CardContent className="space-y-2 pt-5">
                {paiements.data?.results.length ? paiements.data.results.map((p) => (
                  <div key={p.id} className="flex items-center justify-between text-sm">
                    <span className="capitalize">{formatMois(p.mois)}</span>
                    <span className="tabular-nums">{formatFCFA(p.montant_paye)} / {formatFCFA(p.montant_du)}</span>
                    <StatusBadge map={STATUT_PAIEMENT} value={p.statut} />
                  </div>
                )) : <EmptyState title="Aucun paiement" />}
              </CardContent></Card>
            </TabsContent>
            <TabsContent value="contrats">
              <Card><CardContent className="space-y-3 pt-5">
                {contrats.data?.results.length ? contrats.data.results.map((c) => (
                  <div key={c.id} className="flex items-center justify-between gap-2 text-sm">
                    <div><p className="font-medium">{c.locataire_nom}</p><p className="text-xs text-muted-foreground">{formatDate(c.date_debut)} → {formatDate(c.date_fin)}</p></div>
                    <span className="tabular-nums">{formatFCFA(c.loyer_total)}</span>
                    <StatusBadge map={STATUT_CONTRAT} value={c.statut} />
                  </div>
                )) : <EmptyState title="Aucun contrat" />}
              </CardContent></Card>
            </TabsContent>
            <TabsContent value="interventions">
              <Card><CardHeader className="sr-only"><CardTitle>Interventions</CardTitle></CardHeader><CardContent className="space-y-3 pt-5">
                {interventions.data?.results.length ? interventions.data.results.map((i) => (
                  <div key={i.id} className="flex items-center justify-between gap-2 text-sm">
                    <div><p className="font-medium">{i.titre}</p><p className="text-xs text-muted-foreground">{formatDate(i.date_signalement)}</p></div>
                    <StatusBadge map={PRIORITE} value={i.priorite} />
                    <StatusBadge map={STATUT_INTERVENTION} value={i.statut} />
                  </div>
                )) : <EmptyState title="Aucune intervention" />}
              </CardContent></Card>
            </TabsContent>
          </Tabs>
        </div>
      </div>

      <FormDialog
        open={editing}
        onOpenChange={setEditing}
        title="Modifier le bien"
        fields={BIEN_FIELDS}
        defaultValues={{ ...b, photo: undefined }}
        onSubmit={async (payload) => {
          await save.mutateAsync({ id: b.id, data: payload })
          toast.success('Bien modifié.')
        }}
      />
    </>
  )
}
