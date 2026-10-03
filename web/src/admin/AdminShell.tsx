import { ClipboardList, Clapperboard, Cpu, FlaskConical, LayoutDashboard, TrendingUp, Users, type LucideIcon } from 'lucide-react'
import { useEffect } from 'react'
import { useSystemStatus } from '@/shared/hooks/queries'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
  useSidebar,
} from '@/shared/ui/sidebar'
import { SkipLink } from '@/shared/ui/skip-link'
import { siblingPage } from '@/shared/lib/pages'
import { Cases } from './Cases'
import { LogSection } from './LogSection'
import { ModelPanel } from './ModelPanel'
import { MoviesSection } from './MoviesSection'
import { Overview } from './Overview'
import { Popularity } from './Popularity'
import { hrefFor, SECTION_TITLES, SECTIONS, useRoute, type Section } from './route'
import { UsersSection } from './UsersSection'

const ICONS: Record<Section, LucideIcon> = {
  overview: LayoutDashboard,
  cases: FlaskConical,
  users: Users,
  movies: Clapperboard,
  popularity: TrendingUp,
  models: Cpu,
  log: ClipboardList,
}

/** On a narrow screen the sidebar is a drawer: choosing a section must close it. */
function CloseDrawerOnNavigate({ section }: { section: Section }) {
  const { setOpenMobile } = useSidebar()
  useEffect(() => {
    setOpenMobile(false)
  }, [section, setOpenMobile])
  return null
}

/** The admin frame (design D-7): a sidebar with the seven sections, a header with the serving model and a link to the user
 *  page, and the section picked by the URL hash. Below 1024 px the sidebar is a drawer. */
export function AdminShell() {
  const route = useRoute()
  const system = useSystemStatus({ refetchInterval: 30_000 })
  const title = SECTION_TITLES[route.section]

  useEffect(() => {
    document.title = `MovieLens — Quản trị — ${title}`
  }, [title])

  return (
    <SidebarProvider>
      <CloseDrawerOnNavigate section={route.section} />
      <SkipLink />
      <Sidebar>
        <SidebarHeader className="gap-1 border-b px-4 py-4">
          <div className="text-lg font-semibold">MovieLens</div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            Quản trị
            <span className="rounded border border-warning-text/50 px-1.5 py-0.5 text-[11px] font-semibold uppercase text-warning-text">demo-only</span>
          </div>
        </SidebarHeader>
        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupContent>
              <nav aria-label="Các mục quản trị">
              <SidebarMenu>
                {SECTIONS.map((section) => {
                  const Icon = ICONS[section]
                  const active = route.section === section
                  return (
                    <SidebarMenuItem key={section}>
                      <SidebarMenuButton asChild isActive={active} size="lg" className="min-h-11">
                        <a href={hrefFor(section, section === 'users' ? route.userId : null)} aria-current={active ? 'page' : undefined}>
                          <Icon aria-hidden="true" />
                          <span>{SECTION_TITLES[section]}</span>
                        </a>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  )
                })}
              </SidebarMenu>
              </nav>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
        <SidebarFooter className="border-t px-4 py-3 text-sm">
          <p className="text-xs text-muted-foreground">Chỉ gọi API cùng origin, không tải gì từ internet.</p>
        </SidebarFooter>
      </Sidebar>

      <SidebarInset>
        <header className="flex flex-wrap items-center gap-3 border-b bg-card px-4 py-3">
          <SidebarTrigger aria-label="Mở hoặc đóng menu" className="size-11 sm:size-10" />
          <h1 className="text-xl font-semibold">{title}</h1>
          <div className="ml-auto flex flex-wrap items-center gap-4 text-sm">
            <span className="font-mono text-muted-foreground">model {system.data?.activeVersion ?? '—'}</span>
            <a className="font-medium text-primary underline underline-offset-4 hover:text-primary-hover" href={siblingPage('user')}>
              Mở trang người dùng
            </a>
          </div>
        </header>
        <main id="main" tabIndex={-1} className="flex-1 space-y-4 p-4 outline-none" data-ui="admin-section" data-section={route.section}>
          {route.section === 'overview' && <Overview />}
          {route.section === 'cases' && <Cases />}
          {route.section === 'users' && <UsersSection userId={route.userId} />}
          {route.section === 'movies' && <MoviesSection />}
          {route.section === 'popularity' && <Popularity />}
          {route.section === 'models' && <ModelPanel />}
          {route.section === 'log' && <LogSection />}
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
