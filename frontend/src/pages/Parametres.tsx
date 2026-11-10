import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, CheckCircle2, MailCheck, MessageCircle, MinusCircle, Send } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { PageHeader } from '@/components/common'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { api, ApiError } from '@/lib/api'
import type { EnvoiNotification, Paginated, PreferencesNotification } from '@/lib/types'
import { formatDate } from '@/lib/utils'

const KEY = ['/me', 'notifications']

function Interrupteur({ label, detail, checked, onChange, disabled }: { label: string; detail?: string; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <label className="flex items-start justify-between gap-4 py-2">
      <span>
        <span className="block text-sm font-medium">{label}</span>
        {detail && <span className="block text-xs text-muted-foreground">{detail}</span>}
      </span>
      <input type="checkbox" role="switch" className="mt-1 h-5 w-5 shrink-0 accent-primary" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
    </label>
  )
}

const ICONE_STATUT = {
  envoye: <CheckCircle2 className="h-4 w-4 text-success" />,
  echec: <AlertCircle className="h-4 w-4 text-destructive" />,
  ignore: <MinusCircle className="h-4 w-4 text-muted-foreground" />,
}

export default function Parametres() {
  const qc = useQueryClient()
  const prefs = useQuery({ queryKey: KEY, queryFn: () => api.get<PreferencesNotification>('/me/notifications/') })
  const envois = useQuery({ queryKey: [...KEY, 'envois'], queryFn: () => api.get<Paginated<EnvoiNotification>>('/me/notifications/envois/', { page_size: 15 }) })
  const [email, setEmail] = useState('')
  const [numero, setNumero] = useState('')
  const [erreur, setErreur] = useState('')

  useEffect(() => {
    if (prefs.data) {
      setEmail(prefs.data.email)
      setNumero(prefs.data.numero_whatsapp)
    }
  }, [prefs.data])

  const maj = useMutation({
    mutationFn: (data: Partial<PreferencesNotification>) => api.patch<PreferencesNotification>('/me/notifications/', data),
    onSuccess: (d) => { qc.setQueryData(KEY, d); setErreur('') },
    onError: (e) => setErreur(e instanceof ApiError ? e.message : 'Enregistrement impossible.'),
  })

  const test = useMutation({
    mutationFn: () => api.post<{ resultats: { canal: string; adresse: string; statut: string; erreur: string }[] }>('/me/notifications/test/'),
    onSuccess: (r) => {
      void qc.invalidateQueries({ queryKey: [...KEY, 'envois'] })
      if (r.resultats.length === 0) toast.warning('Aucun canal actif : renseignez un email ou un numéro WhatsApp.')
      r.resultats.forEach((x) => {
        const nom = x.canal === 'email' ? 'Email' : 'WhatsApp'
        if (x.statut === 'envoye') toast.success(`${nom} envoyé à ${x.adresse}.`)
        else toast.error(`${nom} : ${x.erreur || 'non envoyé'}`)
      })
    },
  })

  if (prefs.isPending) return <Skeleton className="h-96" />
  if (prefs.isError) return <p className="text-sm text-destructive">Chargement impossible.</p>
  const p = prefs.data
  const modifie = email !== p.email || numero !== p.numero_whatsapp

  return (
    <>
      <PageHeader title="Notifications" description="Où et comment recevoir les alertes : nouvelles réservations, messages, signalements, paiements, retards…" />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><MessageCircle className="h-4 w-4" /> Mes coordonnées</CardTitle>
            <CardDescription>Les alertes arrivent dans l&apos;application, par email et sur WhatsApp.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-1.5">
              <label htmlFor="p-email" className="text-sm font-medium">Adresse email</label>
              <Input id="p-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="vous@exemple.com" />
            </div>
            <div className="grid gap-1.5">
              <label htmlFor="p-wa" className="text-sm font-medium">Numéro WhatsApp</label>
              <Input id="p-wa" type="tel" value={numero} onChange={(e) => setNumero(e.target.value)} placeholder="+221 77 123 45 67" />
              <p className="text-xs text-muted-foreground">Format international ; un numéro à 9 chiffres est automatiquement complété par +221.</p>
            </div>
            {erreur && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{erreur}</p>}
            {!p.whatsapp_disponible && (
              <p className="rounded-md bg-warning/15 px-3 py-2 text-sm text-warning">
                WhatsApp n&apos;est pas encore branché sur le serveur (variable WHATSAPP_PROVIDER). Vous recevrez les alertes par email et dans l&apos;application en attendant.
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              <Button disabled={!modifie} loading={maj.isPending} onClick={() => maj.mutate({ email, numero_whatsapp: numero })}>Enregistrer</Button>
              <Button variant="outline" loading={test.isPending} disabled={modifie} onClick={() => test.mutate()}><Send /> Envoyer un message de test</Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><MailCheck className="h-4 w-4" /> Ce que je reçois</CardTitle>
            <CardDescription>La cloche de l&apos;application reçoit toujours tout ; décochez pour ne plus être prévenu par email / WhatsApp.</CardDescription>
          </CardHeader>
          <CardContent className="divide-y">
            <Interrupteur label="Recevoir par email" checked={p.notif_email} onChange={(v) => maj.mutate({ notif_email: v })} />
            <Interrupteur label="Recevoir par WhatsApp" checked={p.notif_whatsapp} onChange={(v) => maj.mutate({ notif_whatsapp: v })} />
            <div className="pt-2">
              {p.evenements.map((e) => (
                <Interrupteur
                  key={e.code}
                  label={e.label}
                  checked={e.actif}
                  disabled={!p.notif_email && !p.notif_whatsapp}
                  onChange={(v) => maj.mutate({ evenements_desactives: v ? p.evenements_desactives.filter((c) => c !== e.code) : [...p.evenements_desactives, e.code] })}
                />
              ))}
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Derniers envois</CardTitle>
            <CardDescription>Chaque email et WhatsApp est tracé ici. Un envoi en échec est retenté automatiquement (3 essais).</CardDescription>
          </CardHeader>
          <CardContent>
            {envois.data?.results.length ? (
              <ul className="divide-y">
                {envois.data.results.map((e) => (
                  <li key={e.id} className="flex items-start gap-3 py-2 text-sm">
                    <span className="mt-0.5">{ICONE_STATUT[e.statut]}</span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{e.sujet || e.evenement_label}</p>
                      <p className="text-xs text-muted-foreground">{e.canal_display}{e.libelle_destinataire && ` → ${e.libelle_destinataire}`}{e.adresse && ` (${e.adresse})`} · {formatDate(e.created_at)}</p>
                      {e.erreur && <p className="text-xs text-destructive">{e.erreur}</p>}
                    </div>
                    <Badge tone={e.statut === 'envoye' ? 'success' : e.statut === 'echec' ? 'danger' : 'neutral'}>{e.statut_display}</Badge>
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-muted-foreground">Aucun envoi pour le moment.</p>}
          </CardContent>
        </Card>
      </div>
    </>
  )
}
