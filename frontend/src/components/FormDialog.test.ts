import { describe, expect, it } from 'vitest'

import { buildPayload, type FieldDef } from '@/components/FormDialog'

const champs: FieldDef[] = [
  { name: 'nom', label: 'Nom', type: 'text' },
  { name: 'meuble', label: 'Meublé', type: 'checkbox' },
  { name: 'equipements', label: 'Équipements', type: 'multiselect' },
  { name: 'photo', label: 'Photo', type: 'file' },
]

describe('buildPayload (équipements et cases à cocher)', () => {
  it('convertit les cases cochées (chaînes) en identifiants numériques', () => {
    const p = buildPayload(champs, { nom: 'Villa', meuble: true, equipements: ['3', '7'] })
    expect(p).toEqual({ nom: 'Villa', meuble: true, equipements: [3, 7] })
  })

  it('accepte une seule case cochée (react-hook-form renvoie alors une chaîne) ou aucune (false)', () => {
    expect((buildPayload(champs, { equipements: '5' }) as Record<string, unknown>).equipements).toEqual([5])
    expect((buildPayload(champs, { equipements: false, meuble: false }) as Record<string, unknown>)).toMatchObject({ equipements: [], meuble: false })
  })

  it('envoie les équipements un par un en multipart, avec un marqueur quand la liste est vide', () => {
    const photo = new File(['x'], 'photo.png', { type: 'image/png' })
    const avec = buildPayload(champs, { nom: 'Villa', equipements: ['3', '7'], photo: [photo] }) as FormData
    expect(avec.getAll('equipements')).toEqual(['3', '7'])
    expect(avec.get('equipements__present')).toBeNull()
    const vide = buildPayload(champs, { nom: 'Villa', equipements: [], photo: [photo] }) as FormData
    expect(vide.getAll('equipements')).toEqual([])
    expect(vide.get('equipements__present')).toBe('1')
  })
})
