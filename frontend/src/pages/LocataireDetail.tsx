import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Copy, MailPlus, ShieldOff } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { toast } from 'sonner'

import { DocumentsPanel } from '@/components/DocumentsPanel'
import { ErrorState, PageHeader, StatusBadge } from '@/components/common'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { api } from '@/lib/api'
import { NIVEAU_SCORE, STATUT_CONTRAT, STATUT_PAIEMENT } from '@/lib/labels'
import { invalidateAll, notifyError, useDetail, useList } from '@/lib/queries'
import type { Contrat, Locataire, Paiement, ScoreLocataire } from '@/lib/types'
import { formatDate, formatFCFA, formatMois } from '@/lib/utils'

interface Invitation {
  identifiant: string
  lien_activation: string
  email_envoye: boolean
}

export default function LocataireDetail() {
  const { id } = useParams()
  const qc = useQueryClient()
  const loc = useDetail<Locataire>('/locataires', id)
  const contrats = useList<Contrat>('/contrats', { locataire: id, page_size: 50 })
  const paiements = useList<Paiement>('/paiements', { locataire: id, ordering: '-mois', page_size: 12 })
  const score = useQuery({ queryKey: ['/locataires', 'score', id], queryFn: () => api.get<ScoreLocataire>(`/locataires/${id}/score/`), enabled: !!id })
  const [invitation, setInvitation] = useState<Invitation | null>(null)

  const inviter = useMutation({
    mutationFn: () => api.post<Invitation>(`/locataires/${id}/inviter/`),
    onSuccess: (r) => { setInvitation(r); invalidateAll(qc, '/locataires') },
    onError: notifyError,
  })
  const revoquer = useMutation({
    mutationFn: () => api.post(`/locataires/${id}/revoquer/`),
    onSuccess: () => { invalidateAll(qc, '/locataires'); toast.success('Accès désactivé.') },
    onError: notifyError,
  })

  if (loc.isError) return <ErrorState message="Locataire introuvable." />
  if (loc.isPending) return <Skeleton className="h-96" />
  const l = loc.data

  return (
    <>
      <Button variant="ghost" size="sm" asChild className="mb-3"><Link to="/locataires"><ArrowLeft /> Locataires</Link></Button>
      <PageHeader
        title={l.nom_complet}
        description={`${l.telephone}${l.email ? ` · ${l.email}` : ''}`}
        actions={
          <>
            <Button onClick={() => inviter.mutate()} loading={inviter.isPending}>
              <MailPlus /> {l.a_un_acces ? "Renvoyer l'invitation" : "Créer l'accès locataire"}
            </Button>
            {l.a_un_acces && l.acces_actif && (
              <Button variant="outline" onClick={() => revoquer.mutate()} loading={revoquer.isPending}><ShieldOff /> Révoquer</Button>
            )}
          </>
        }
      />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader><CardTitle>Profil</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm">
            <p><span className="text-muted-foreground">Profession :</span> {l.profession || '—'}</p>
            <p><span className="text-muted-foreground">Revenu :</span> {l.revenu_mensuel ? formatFCFA(l.revenu_mensuel) : '—'}</p>
            <p><span className="text-muted-foreground">Naissance :</span> {formatDate(l.date_naissance)}</p>
            <p><span className="text-muted-foreground">Adresse précédente :</span> {l.adresse_precedente || '—'}</p>
            <p className="flex items-center gap-2"><span className="text-muted-foreground">Accès en ligne :</span>{l.a_un_acces ? <Badge tone={l.acces_actif ? 'success' : 'neutral'}>{l.acces_actif ? 'Actif' : 'Désactivé'}</Badge> : <Badge tone="outline">Aucun</Badge>}</p>
            {l.notes && <p className="rounded-md bg-muted p-3 text-muted-foreground">{l.notes}</p>}
          </CardContent>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader><CardTitle>Contrats</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {contrats.data?.results.length ? contrats.data.results.map((c) => (
              <div key={c.id} className="flex items-center justify-between gap-2 text-sm">
                <div><p className="font-medium">{c.bien_nom}</p><p className="text-xs text-muted-foreground">{formatDate(c.date_debut)} → {formatDate(c.date_fin)}</p></div>
                <span className="tabular-nums">{formatFCFA(c.loyer_total)}</span>
                <StatusBadge map={STATUT_CONTRAT} value={c.statut} />
              </div>
            )) : <p className="text-sm text-muted-foreground">Aucun contrat.</p>}
          </CardContent>
        </Card>
        <Card className="lg:col-span-3">
          <CardHeader><CardTitle>Fiabilité du locataire</CardTitle></CardHeader>
          <CardContent>
            {score.data ? (
              <div className="flex flex-wrap items-center gap-6">
                <div className="flex items-baseline gap-2">
                  <span className="text-4xl font-semibold tabular-nums">{score.data.score ?? '—'}</span>
                  <span className="text-sm text-muted-foreground">/ 100</span>
                </div>
                <StatusBadge map={NIVEAU_SCORE} value={score.data.niveau} />
                <p className="text-sm text-muted-foreground">
                  {score.data.nb_paiements} loyer(s) échu(s), {score.data.nb_retards} en retard ou partiel(s)
                  {score.data.taux_effort !== null ? ` · loyer = ${score.data.taux_effort} % du revenu` : ''}
                </p>
              </div>
            ) : <Skeleton className="h-12" />}
          </CardContent>
        </Card>
        <div className="lg:col-span-3"><DocumentsPanel locataire={l.id} /></div>
        <Card className="lg:col-span-3">
          <CardHeader><CardTitle>Historique des loyers</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {paiements.data?.results.length ? paiements.data.results.map((p) => (
              <div key={p.id} className="flex items-center justify-between text-sm">
                <span className="capitalize">{formatMois(p.mois)}</span>
                <span className="tabular-nums">{formatFCFA(p.montant_paye)} / {formatFCFA(p.montant_du)}</span>
                <StatusBadge map={STATUT_PAIEMENT} value={p.statut} />
              </div>
            )) : <p className="text-sm text-muted-foreground">Aucun paiement.</p>}
          </CardContent>
        </Card>
      </div>

      <Dialog open={invitation !== null} onOpenChange={(o) => !o && setInvitation(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Accès créé</DialogTitle>
            <DialogDescription>
              Identifiant : <strong>{invitation?.identifiant}</strong>.{' '}
              {invitation?.email_envoye ? "Un email contenant ce lien a été envoyé au locataire." : "Ce locataire n'a pas d'email : transmettez-lui ce lien (WhatsApp, SMS…)."}
              {' '}Le lien est personnel et à usage unique : le locataire y choisit lui-même son mot de passe.
            </DialogDescription>
          </DialogHeader>
          <div className="flex gap-2">
            <Input readOnly value={invitation?.lien_activation ?? ''} onFocus={(e) => e.currentTarget.select()} aria-label="Lien d'activation" />
            <Button variant="outline" size="icon" aria-label="Copier le lien" onClick={() => { void navigator.clipboard.writeText(invitation?.lien_activation ?? ''); toast.success('Lien copié.') }}><Copy /></Button>
          </div>
          <DialogFooter><Button onClick={() => setInvitation(null)}>Fermer</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
