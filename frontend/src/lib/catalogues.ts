import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'

import type { FieldDef } from '@/components/FormDialog'
import { api } from '@/lib/api'
import { OFFRES_BIEN, STATUTS_BIEN, STATUTS_JURIDIQUES, TYPES_BIEN } from '@/lib/labels'
import type { Bien, Equipement, Paginated, Proprietaire } from '@/lib/types'

/** Catalogue d'équipements (non paginé côté API, rarement modifié : mis en cache 5 min). */
export function useEquipements() {
  return useQuery({
    queryKey: ['/equipements'],
    queryFn: () => api.get<Equipement[]>('/equipements/'),
    staleTime: 5 * 60_000,
  })
}

export function useProprietaires() {
  return useQuery({
    queryKey: ['/proprietaires', 'list', { page_size: 200, actif: 'true' }],
    queryFn: () => api.get<Paginated<Proprietaire>>('/proprietaires/', { page_size: 200, actif: 'true' }),
  })
}

/**
 * Champs du formulaire « bien ». Le statut « loué » est géré automatiquement par les contrats :
 * on ne peut ni le poser, ni le retirer à la main (le serveur le refuse aussi).
 */
export function useBienFields(bien: Bien | 'new' | null): FieldDef[] {
  const equipements = useEquipements()
  const proprietaires = useProprietaires()
  const loue = bien !== null && bien !== 'new' && bien.statut === 'loue'
  const nouveau = bien === 'new'
  return useMemo(() => {
    const champs: FieldDef[] = [
      { name: 'nom', label: 'Nom du bien', required: true, full: true },
      { name: 'type_bien', label: 'Type', type: 'select', options: TYPES_BIEN, required: true },
      { name: 'offre', label: 'Annonce', type: 'select', options: OFFRES_BIEN, required: true, hint: 'Location ou vente : détermine l’affichage sur le site public.' },
      {
        name: 'statut', label: 'Statut', type: 'select', required: true,
        options: loue ? STATUTS_BIEN.filter((s) => s.value === 'loue') : STATUTS_BIEN.filter((s) => s.value !== 'loue'),
        hint: loue ? 'Bien loué : le statut change tout seul quand le contrat est résilié.' : 'Passe à « Loué » dès qu’un contrat est créé.',
      },
      { name: 'adresse', label: 'Adresse', required: true, full: true },
      { name: 'ville', label: 'Ville', required: true },
      { name: 'code_postal', label: 'Code postal', required: true },
      { name: 'surface', label: 'Surface (m²)', type: 'number', required: true },
      { name: 'nb_pieces', label: 'Nombre de pièces', type: 'number', required: true },
      { name: 'nb_chambres', label: 'Chambres', type: 'number' },
      { name: 'nb_salles_bain', label: 'Salles de bain', type: 'number' },
      { name: 'capacite', label: 'Capacité (personnes)', type: 'number', nullable: true, hint: 'Limite les réservations.' },
      { name: 'meuble', label: 'Meublé', type: 'checkbox', hint: 'Ce bien est loué meublé' },
      { name: 'etage', label: 'Étage', type: 'number', nullable: true },
      { name: 'loyer_charges', label: 'Loyer charges comprises (FCFA)', type: 'number', hint: 'Laisser 0 pour un bien à vendre.' },
      { name: 'prix_vente', label: 'Prix de vente (FCFA)', type: 'number', nullable: true, hint: 'Obligatoire si le bien est à vendre.' },
      { name: 'statut_juridique', label: 'Situation foncière', type: 'select', options: STATUTS_JURIDIQUES },
      { name: 'prix_nuit', label: 'Tarif par nuit (FCFA)', type: 'number', nullable: true, hint: 'Pour les réservations du site public.' },
      { name: 'depot_garantie', label: 'Dépôt de garantie (FCFA)', type: 'number' },
      {
        name: 'equipements', label: 'Équipements', type: 'multiselect', full: true,
        options: (equipements.data ?? []).map((e) => ({ value: e.id, label: e.nom, group: e.categorie_display })),
      },
    ]
    if (nouveau) {
      champs.push({
        name: 'proprietaire_principal', label: 'Propriétaire', type: 'select', nullable: true, full: true,
        options: (proprietaires.data?.results ?? []).map((p) => ({ value: p.id, label: p.nom_complet })),
        hint: 'Pour plusieurs propriétaires, répartissez les parts depuis la fiche du bien.',
      })
    }
    champs.push(
      { name: 'photo', label: 'Photo', type: 'file', full: true },
      { name: 'description', label: 'Description', type: 'textarea' },
    )
    return champs
  }, [equipements.data, proprietaires.data, loue, nouveau])
}

/** Valeurs initiales d'un bien : les cases à cocher de RHF comparent des chaînes. */
export function bienDefaults(b: Bien) {
  return { ...b, photo: undefined, equipements: b.equipements.map(String) }
}
