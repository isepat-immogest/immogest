export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface Me {
  id: number
  username: string
  nom: string
  email: string
  role: 'gestionnaire' | 'locataire'
  is_staff: boolean
  locataire_id: number | null
  notifications_non_lues: number
}

export type BienStatut = 'libre' | 'loue' | 'travaux' | 'vente'

export interface Bien {
  id: number
  nom: string
  type_bien: string
  type_display: string
  statut: BienStatut
  statut_display: string
  adresse: string
  ville: string
  code_postal: string
  surface: string
  nb_pieces: number
  etage: number | null
  loyer_charges: string
  prix_nuit: string | null
  depot_garantie: string
  description: string
  photo: string | null
  locataire_actuel: { id: number; nom: string } | null
  created_at: string
}

export interface Locataire {
  id: number
  prenom: string
  nom: string
  nom_complet: string
  initiales: string
  email: string
  telephone: string
  date_naissance: string | null
  profession: string
  revenu_mensuel: string | null
  adresse_precedente: string
  notes: string
  a_un_acces: boolean
  acces_actif: boolean
  contrat_actif: { id: number; bien: string; loyer_total: number } | null
}

export type ContratStatut = 'actif' | 'termine' | 'resilie'

export interface Contrat {
  id: number
  bien: number
  bien_nom: string
  locataire: number
  locataire_nom: string
  type_bail: string
  statut: ContratStatut
  statut_display: string
  date_debut: string
  date_fin: string | null
  loyer_mensuel: string
  charges_mensuelles: string
  loyer_total: string
  depot_garantie: string
  jour_paiement: number
  duree_mois: number
  notes: string
}

export type PaiementStatut = 'paye' | 'en_attente' | 'retard' | 'partiel'

export interface Paiement {
  id: number
  contrat: number
  locataire_nom: string
  bien_nom: string
  mois: string
  montant_du: string
  montant_paye: string
  solde: string
  statut: PaiementStatut
  statut_display: string
  mode_paiement: string
  date_paiement: string | null
  date_echeance: string
  notes: string
}

export interface PaiementsPage extends Paginated<Paiement> {
  totaux: { encaisse: number | string; reste_a_payer: number | string; nb_retard: number }
}

export type InterventionStatut = 'ouverte' | 'en_cours' | 'terminee' | 'annulee'
export type Priorite = 'basse' | 'normale' | 'haute' | 'urgente'

export interface Intervention {
  id: number
  bien: number
  bien_nom: string
  titre: string
  description: string
  priorite: Priorite
  priorite_display: string
  statut: InterventionStatut
  statut_display: string
  date_signalement: string
  date_intervention: string | null
  date_resolution: string | null
  prestataire: string
  cout: string | null
  notes: string
  signale_par_nom: string | null
}

export type ReservationStatut = 'en_attente' | 'payee' | 'confirmee' | 'annulee'

export interface Reservation {
  id: number
  reference: string
  bien: number
  bien_nom: string
  nom: string
  telephone: string
  email: string
  date_arrivee: string
  date_depart: string | null
  nb_personnes: number
  mode_paiement: string
  statut: ReservationStatut
  statut_display: string
  montant_total: string
  nb_nuits: number
  message: string
  created_at: string
}

export interface Demande {
  id: number
  bien: number | null
  bien_nom: string | null
  nom: string
  email: string
  telephone: string
  message: string
  traite: boolean
  created_at: string
}

export interface AppNotification {
  id: number
  titre: string
  message: string
  lien: string
  lue: boolean
  created_at: string
}

export interface Dashboard {
  kpis: {
    total_biens: number
    biens_loues: number
    biens_libres: number
    biens_travaux: number
    taux_occupation: number
    revenus_mois: number | string
    prevu_mois: number | string
    taux_recouvrement: number
    nb_retard: number
    montant_retard: number | string
    demandes_non_traitees: number
    reservations_a_traiter: number
  }
  revenus: { mois: string; prevu: number | string; encaisse: number | string }[]
  repartition_biens: { statut: BienStatut; nombre: number }[]
  interventions: { id: number; titre: string; bien: string; priorite: Priorite; statut: InterventionStatut }[]
  contrats_fin: { id: number; bien: string; locataire: string; date_fin: string }[]
  paiements_recents: Paiement[]
}

export interface EspaceAccueil {
  locataire: Locataire
  contrat: Contrat | null
  bien: Bien | null
  montant_du: number | string
  paiements_recents: Paiement[]
  interventions: Intervention[]
}

export interface SearchResult {
  type: 'bien' | 'locataire' | 'reservation'
  id: number
  titre: string
  detail: string
  url: string
}

export interface Depense {
  id: number
  bien: number
  bien_nom: string
  categorie: string
  categorie_display: string
  libelle: string
  montant: string
  date: string
  notes: string
}

export interface ResumeFinance {
  revenus_12m: number | string
  depenses_12m: number | string
  net_12m: number | string
  par_categorie: { categorie: string; total: number | string }[]
}

export interface Rentabilite {
  revenus_12m: number | string
  depenses_12m: number | string
  net_12m: number | string
  rendement_net_pct: number | null
  depenses_par_categorie: Record<string, number | string>
}

export interface ScoreLocataire {
  score: number | null
  niveau: 'bon' | 'moyen' | 'risque' | 'inconnu'
  nb_paiements: number
  nb_retards: number
  taux_effort: number | null
}

export interface DocumentPiece {
  id: number
  type_document: string
  type_display: string
  titre: string
  locataire: number | null
  bien: number | null
  date_expiration: string | null
  created_at: string
  nom_fichier: string
  taille: number
}

export type CalendrierType = 'reservation' | 'loyer' | 'contrat' | 'intervention'

export interface EvenementCalendrier {
  id: string
  type: CalendrierType
  titre: string
  debut: string
  fin: string
  statut: string
  url: string
}
