/** Libellés et variantes de couleur pour les statuts métier. */
export type Tone = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

export const STATUT_PAIEMENT: Record<string, { label: string; tone: Tone }> = {
  paye: { label: 'Payé', tone: 'success' },
  partiel: { label: 'Partiel', tone: 'warning' },
  en_attente: { label: 'En attente', tone: 'info' },
  retard: { label: 'En retard', tone: 'danger' },
}

export const STATUT_BIEN: Record<string, { label: string; tone: Tone }> = {
  libre: { label: 'Libre', tone: 'success' },
  loue: { label: 'Loué', tone: 'info' },
  travaux: { label: 'En travaux', tone: 'warning' },
  vente: { label: 'En vente', tone: 'neutral' },
}

export const STATUT_CONTRAT: Record<string, { label: string; tone: Tone }> = {
  actif: { label: 'Actif', tone: 'success' },
  termine: { label: 'Terminé', tone: 'neutral' },
  resilie: { label: 'Résilié', tone: 'danger' },
}

export const STATUT_RESERVATION: Record<string, { label: string; tone: Tone }> = {
  en_attente: { label: 'En attente de paiement', tone: 'warning' },
  payee: { label: 'Payée', tone: 'info' },
  confirmee: { label: 'Confirmée', tone: 'success' },
  annulee: { label: 'Annulée', tone: 'neutral' },
}

export const PRIORITE: Record<string, { label: string; tone: Tone }> = {
  basse: { label: 'Basse', tone: 'neutral' },
  normale: { label: 'Normale', tone: 'info' },
  haute: { label: 'Haute', tone: 'warning' },
  urgente: { label: 'Urgente', tone: 'danger' },
}

export const STATUT_INTERVENTION: Record<string, { label: string; tone: Tone }> = {
  ouverte: { label: 'Ouverte', tone: 'warning' },
  en_cours: { label: 'En cours', tone: 'info' },
  terminee: { label: 'Terminée', tone: 'success' },
  annulee: { label: 'Annulée', tone: 'neutral' },
}

export const MODES_PAIEMENT = [
  { value: 'wave', label: 'Wave' },
  { value: 'orange_money', label: 'Orange Money' },
  { value: 'free_money', label: 'Free Money' },
  { value: 'especes', label: 'Espèces' },
  { value: 'virement', label: 'Virement' },
  { value: 'cheque', label: 'Chèque' },
  { value: 'prelevement', label: 'Prélèvement' },
]

export const TYPES_BIEN = [
  { value: 'appartement', label: 'Appartement' },
  { value: 'maison', label: 'Maison' },
  { value: 'studio', label: 'Studio' },
  { value: 'commerce', label: 'Local commercial' },
  { value: 'garage', label: 'Garage' },
]

export const STATUTS_BIEN = [
  { value: 'libre', label: 'Libre' },
  { value: 'loue', label: 'Loué' },
  { value: 'travaux', label: 'En travaux' },
  { value: 'vente', label: 'En vente' },
]

export const TYPES_BAIL = [
  { value: 'vide', label: 'Location vide' },
  { value: 'meuble', label: 'Location meublée' },
  { value: 'commercial', label: 'Bail commercial' },
  { value: 'saisonnier', label: 'Saisonnier' },
]

export const PRIORITES = Object.entries(PRIORITE).map(([value, v]) => ({ value, label: v.label }))

export const CATEGORIES_DEPENSE = [
  { value: 'taxe', label: 'Taxes et impôts' },
  { value: 'assurance', label: 'Assurance' },
  { value: 'travaux', label: 'Travaux' },
  { value: 'entretien', label: 'Entretien' },
  { value: 'syndic', label: 'Syndic / charges' },
  { value: 'autre', label: 'Autre' },
]

export const TYPES_DOCUMENT = [
  { value: 'identite', label: "Pièce d'identité" },
  { value: 'bail', label: 'Bail signé' },
  { value: 'assurance', label: 'Assurance' },
  { value: 'justificatif', label: 'Justificatif de revenu' },
  { value: 'etat_lieux', label: 'État des lieux' },
  { value: 'autre', label: 'Autre' },
]

export const NIVEAU_SCORE: Record<string, { label: string; tone: Tone }> = {
  bon: { label: 'Fiable', tone: 'success' },
  moyen: { label: 'À surveiller', tone: 'warning' },
  risque: { label: 'À risque', tone: 'danger' },
  inconnu: { label: 'Pas assez de données', tone: 'neutral' },
}
