import {
  Cog,
  Cylinder,
  LayoutGrid,
  LogOut,
  Scissors,
  Tag,
} from "lucide-react"

import printgooLogo from "@/assets/printgoo_logo.svg"

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar"

export type TabKey = "sela" | "extractor" | "label-imp" | "print-imp" | "gears"

interface AppSidebarProps {
  activeTab: TabKey
  onSelectTab: (tab: TabKey) => void
  authEnabled: boolean
  onLogout: () => void
}

export function AppSidebar({
  activeTab,
  onSelectTab,
  authEnabled,
  onLogout,
}: AppSidebarProps) {
  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="justify-center border-b border-sidebar-border px-3 py-2.5 group-data-[collapsible=icon]:h-12 group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:py-0">
        <div className="flex items-center select-none group-data-[collapsible=icon]:hidden">
          <img
            src={printgooLogo}
            alt="PrintGoo"
            className="h-14 w-auto max-w-full object-contain"
          />
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Tekstil etiketka</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  isActive={activeTab === "sela"}
                  tooltip="Sela Etiketka"
                  onClick={() => onSelectTab("sela")}
                >
                  <Tag />
                  <span>Sela Etiketka</span>
                </SidebarMenuButton>
                <SidebarMenuBadge>1</SidebarMenuBadge>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  isActive={activeTab === "label-imp"}
                  tooltip="Val Montaji"
                  onClick={() => onSelectTab("label-imp")}
                >
                  <Cylinder />
                  <span>Val Montaji</span>
                </SidebarMenuButton>
                <SidebarMenuBadge>2</SidebarMenuBadge>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel>Ofset va raqamli bosma</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  isActive={activeTab === "extractor"}
                  tooltip="Dizayn Ajratish"
                  onClick={() => onSelectTab("extractor")}
                >
                  <Scissors />
                  <span>Dizayn Ajratish</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  isActive={activeTab === "print-imp"}
                  tooltip="Varaq Montaji"
                  onClick={() => onSelectTab("print-imp")}
                >
                  <LayoutGrid />
                  <span>Varaq Montaji</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel>Boshqaruv</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  isActive={activeTab === "gears"}
                  tooltip="Vallar (Gears)"
                  onClick={() => onSelectTab("gears")}
                >
                  <Cog />
                  <span>Vallar (Gears)</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      {authEnabled && (
        <SidebarFooter className="border-t border-sidebar-border">
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton tooltip="Chiqish" onClick={onLogout}>
                <LogOut />
                <span>Chiqish</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarFooter>
      )}

      <SidebarRail />
    </Sidebar>
  )
}
