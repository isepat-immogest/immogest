import {
  Building2,
  CalendarCheck,
  CalendarDays,
  FileText,
  Home,
  Inbox,
  KeyRound,
  LogOut,
  Menu,
  Moon,
  PiggyBank,
  Search,
  Sun,
  Users,
  Wallet,
  Wrench,
  X,
  type LucideIcon,
} from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'

import { CommandPalette } from '@/components/layout/CommandPalette'
import { NotificationsBell } from '@/components/layout/NotificationsBell'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/hooks/useAuth'
import { useTheme } from '@/hooks/useTheme'
import { prefetchRoute, prefetchWhenIdle } from '@/lib/prefetch'
import { cn } from '@/lib/utils'

interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
  preload?: () => Promise<unknown>
}

const GESTION_NAV: NavItem[] = [
  { to: '/', label: 'Tableau de bord', icon: Home, end: true, preload: () => import('@/pages/Dashboard') },
  { to: '/biens', label: 'Biens', icon: Building2, preload: () => import('@/pages/Biens') },
  { to: '/locataires', label: 'Locataires', icon: Users, preload: () => import('@/pages/Locataires') },
  { to: '/contrats', label: 'Contrats', icon: FileText, preload: () => import('@/pages/Contrats') },
  { to: '/paiements', label: 'Paiements', icon: Wallet, preload: () => import('@/pages/Paiements') },
  { to: '/interventions', label: 'Interventions', icon: Wrench, preload: () => import('@/pages/Interventions') },
  { to: '/reservations', label: 'Réservations', icon: CalendarCheck, preload: () => import('@/pages/Reservations') },
  { to: '/calendrier', label: 'Calendrier', icon: CalendarDays, preload: () => import('@/pages/Calendrier') },
  { to: '/depenses', label: 'Dépenses', icon: PiggyBank, preload: () => import('@/pages/Depenses') },
  { to: '/demandes', label: 'Demandes clients', icon: Inbox, preload: () => import('@/pages/Demandes') },
]

const LOCATAIRE_NAV: NavItem[] = [
  { to: '/espace', label: 'Mon espace', icon: Home, end: true },
  { to: '/espace/paiements', label: 'Mes paiements', icon: Wallet },
  { to: '/espace/signalements', label: 'Mes signalements', icon: Wrench },
  { to: '/espace/securite', label: 'Mot de passe', icon: KeyRound },
]

export function AppShell() {
  const { user, logout } = useAuth()
  const { theme, toggle } = useTheme()
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const isLocataire = user?.role === 'locataire'
  const nav = isLocataire ? LOCATAIRE_NAV : GESTION_NAV
  const qc = useQueryClient()

  // Pendant les temps morts, charge à l'avance le code et les données des pages principales.
  useEffect(() => {
    if (isLocataire) return
    return prefetchWhenIdle(GESTION_NAV.flatMap((n) => [() => n.preload?.(), () => prefetchRoute(qc, n.to)]))
  }, [isLocataire, qc])

  const warm = (item: NavItem) => {
    void item.preload?.()
    prefetchRoute(qc, item.to)
  }

  const links = (
    <nav className="flex flex-col gap-1 p-3" aria-label="Navigation principale">
      {nav.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          onMouseEnter={() => warm(item)}
          onFocus={() => warm(item)}
          onClick={() => setMenuOpen(false)}
          className={({ isActive }) =>
            cn(
              'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
              isActive ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
            )
          }
        >
          <item.icon className="h-4 w-4" />
          {item.label}
        </NavLink>
      ))}
    </nav>
  )

  const brand = (
    <div className="flex h-16 items-center gap-2 border-b px-5">
      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
        <Building2 className="h-4 w-4" />
      </div>
      <span className="text-lg font-semibold tracking-tight">ImmoGest</span>
    </div>
  )

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[16rem_1fr]">
      <aside className="sticky top-0 hidden h-screen flex-col border-r bg-card lg:flex">
        {brand}
        <div className="flex-1 overflow-y-auto">{links}</div>
      </aside>

      {menuOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true">
          <button className="absolute inset-0 bg-black/50" aria-label="Fermer le menu" onClick={() => setMenuOpen(false)} />
          <aside className="relative flex h-full w-64 animate-fade-in flex-col bg-card shadow-xl">
            <div className="flex items-center justify-between">
              {brand}
              <Button variant="ghost" size="icon" className="mr-2" onClick={() => setMenuOpen(false)} aria-label="Fermer">
                <X />
              </Button>
            </div>
            {links}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-col">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-2 border-b bg-card/85 px-4 backdrop-blur">
          <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMenuOpen(true)} aria-label="Ouvrir le menu">
            <Menu />
          </Button>
          {!isLocataire && (
            <button
              onClick={() => setSearchOpen(true)}
              className="flex h-9 w-full max-w-sm items-center gap-2 rounded-md border bg-background px-3 text-sm text-muted-foreground transition-colors hover:bg-accent"
            >
              <Search className="h-4 w-4" />
              <span className="flex-1 text-left">Rechercher…</span>
              <kbd className="hidden rounded border px-1.5 text-[10px] sm:block">Ctrl K</kbd>
            </button>
          )}
          <div className="ml-auto flex items-center gap-1">
            <Button variant="ghost" size="icon" onClick={toggle} aria-label="Changer de thème">
              {theme === 'dark' ? <Sun /> : <Moon />}
            </Button>
            <NotificationsBell />
            <div className="ml-2 hidden text-right sm:block">
              <p className="text-sm font-medium leading-tight">{user?.nom}</p>
              <p className="text-xs text-muted-foreground">{isLocataire ? 'Locataire' : 'Gestionnaire'}</p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Se déconnecter"
              onClick={async () => {
                await logout()
                navigate('/connexion')
              }}
            >
              <LogOut />
            </Button>
          </div>
        </header>
        <main className="flex-1 p-4 sm:p-6 lg:p-8">
          <div className="mx-auto w-full max-w-6xl animate-fade-in">
            <Outlet />
          </div>
        </main>
      </div>
      {!isLocataire && <CommandPalette open={searchOpen} onOpenChange={setSearchOpen} />}
    </div>
  )
}
