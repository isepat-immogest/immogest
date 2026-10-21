import { useQuery } from '@tanstack/react-query'
import { Command } from 'cmdk'
import { Building2, CalendarCheck, CalendarDays, FileText, Home, PiggyBank, Search, Users, Wallet, Wrench } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useDebounce } from '@/hooks/useDebounce'
import { api } from '@/lib/api'
import type { SearchResult } from '@/lib/types'

const PAGES = [
  { label: 'Tableau de bord', to: '/', icon: Home },
  { label: 'Biens', to: '/biens', icon: Building2 },
  { label: 'Locataires', to: '/locataires', icon: Users },
  { label: 'Contrats', to: '/contrats', icon: FileText },
  { label: 'Paiements', to: '/paiements', icon: Wallet },
  { label: 'Interventions', to: '/interventions', icon: Wrench },
  { label: 'Réservations', to: '/reservations', icon: CalendarCheck },
  { label: 'Calendrier', to: '/calendrier', icon: CalendarDays },
  { label: 'Dépenses et rentabilité', to: '/depenses', icon: PiggyBank },
]

const ICONS = { bien: Building2, locataire: Users, reservation: CalendarCheck }

export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [query, setQuery] = useState('')
  const debounced = useDebounce(query, 250)
  const navigate = useNavigate()

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        onOpenChange(!open)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onOpenChange])

  const { data } = useQuery({
    queryKey: ['/recherche', debounced],
    queryFn: () => api.get<{ resultats: SearchResult[] }>('/recherche/', { q: debounced }),
    enabled: open && debounced.trim().length >= 2,
    staleTime: 30_000,
  })

  const go = (to: string) => {
    onOpenChange(false)
    setQuery('')
    navigate(to)
  }

  return (
    <Command.Dialog
      open={open}
      onOpenChange={onOpenChange}
      label="Recherche globale"
      shouldFilter={false}
      overlayClassName="fixed inset-0 z-50 bg-black/50 backdrop-blur-[2px]"
      contentClassName="fixed left-1/2 top-[18%] z-50 w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 overflow-hidden rounded-lg border bg-popover text-popover-foreground shadow-lg"
    >
      <div className="flex items-center gap-2 border-b px-3">
        <Search className="h-4 w-4 text-muted-foreground" />
        <Command.Input
          value={query}
          onValueChange={setQuery}
          placeholder="Rechercher un bien, un locataire, une réservation…"
          className="h-12 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        />
        <kbd className="hidden rounded border px-1.5 text-[10px] text-muted-foreground sm:block">ÉCHAP</kbd>
      </div>
      <Command.List className="max-h-80 overflow-auto p-2">
        <Command.Empty className="py-6 text-center text-sm text-muted-foreground">Aucun résultat.</Command.Empty>
        {data && data.resultats.length > 0 && (
          <Command.Group heading="Résultats" className="text-xs text-muted-foreground [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5">
            {data.resultats.map((r) => {
              const Icon = ICONS[r.type]
              return (
                <Command.Item
                  key={`${r.type}-${r.id}`}
                  value={`${r.type}-${r.id}`}
                  onSelect={() => go(r.url)}
                  className="flex cursor-pointer items-center gap-3 rounded-md px-2 py-2 text-sm text-foreground aria-selected:bg-accent"
                >
                  <Icon className="h-4 w-4 text-muted-foreground" />
                  <span className="font-medium">{r.titre}</span>
                  <span className="truncate text-xs text-muted-foreground">{r.detail}</span>
                </Command.Item>
              )
            })}
          </Command.Group>
        )}
        <Command.Group heading="Aller à" className="text-xs text-muted-foreground [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5">
          {PAGES.map((p) => (
            <Command.Item
              key={p.to}
              value={p.label}
              onSelect={() => go(p.to)}
              className="flex cursor-pointer items-center gap-3 rounded-md px-2 py-2 text-sm text-foreground aria-selected:bg-accent"
            >
              <p.icon className="h-4 w-4 text-muted-foreground" />
              {p.label}
            </Command.Item>
          ))}
        </Command.Group>
      </Command.List>
    </Command.Dialog>
  )
}
