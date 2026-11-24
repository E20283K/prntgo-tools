import { useCallback, useEffect, useState } from "react"
import { ThemeProvider } from "next-themes"

import { AiDesignTab } from "@/components/AiDesignTab"
import { AppSidebar, type TabKey } from "@/components/AppSidebar"
import { ExtractorTab } from "@/components/ExtractorTab"
import { GearsTab } from "@/components/GearsTab"
import { LabelImpTab } from "@/components/LabelImpTab"
import { LoginDialog } from "@/components/LoginDialog"
import { ModeToggle } from "@/components/ModeToggle"
import { PrintImpTab } from "@/components/PrintImpTab"
import { SelaTab } from "@/components/SelaTab"
import { VectorCraftTab } from "@/components/VectorCraftTab"
import { Separator } from "@/components/ui/separator"
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import {
  setUnauthorizedHandler,
  type AuthStatusResponse,
  type LabelHandoff,
  type PrintHandoff,
  type VectorCraftHandoff,
} from "@/lib/api"

const TAB_TITLES: Record<TabKey, string> = {
  sela: "Sela Etiketka",
  extractor: "Dizayn va Pichoq Ajratish",
  "label-imp": "Val Montaji",
  "print-imp": "Varaq Montaji",
  "ai-design": "AI Dizayn & Skills (Claude Code + VectorCraft MCP)",
  vectorcraft: "VectorCraft Web Muharriri",
  gears: "Vallar (Gears)",
}

export default function App() {
  const [activeTab, setActiveTab] = useState<TabKey>("sela")
  const [authEnabled, setAuthEnabled] = useState(false)
  const [authenticated, setAuthenticated] = useState(false)
  const [authChecked, setAuthChecked] = useState(false)
  const [labelHandoff, setLabelHandoff] = useState<LabelHandoff | null>(null)
  const [printHandoff, setPrintHandoff] = useState<PrintHandoff | null>(null)
  const [vectorCraftHandoff, setVectorCraftHandoff] =
    useState<VectorCraftHandoff | null>(null)

  const checkAuth = useCallback(async () => {
    try {
      const res = await fetch("/api/auth/status")
      const data: AuthStatusResponse = await res.json()
      setAuthEnabled(data.auth_enabled)
      setAuthenticated(data.authenticated)
    } catch {
      setAuthenticated(true)
    } finally {
      setAuthChecked(true)
    }
  }, [])

  useEffect(() => {
    setUnauthorizedHandler(() => setAuthenticated(false))
    void checkAuth()
  }, [checkAuth])

  async function handleLogout() {
    await fetch("/api/auth/logout", { method: "POST" })
    window.location.reload()
  }

  function handleSendToLabelImp(handoff: LabelHandoff) {
    setLabelHandoff(handoff)
    setActiveTab("label-imp")
  }

  function handleSendToPrintImp(handoff: PrintHandoff) {
    setPrintHandoff(handoff)
    setActiveTab("print-imp")
  }

  function handleOpenInVectorCraft(handoff: VectorCraftHandoff) {
    setVectorCraftHandoff(handoff)
    setActiveTab("vectorcraft")
  }

  const appReady = authChecked && authenticated

  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <TooltipProvider>
        <SidebarProvider>
          <AppSidebar
            activeTab={activeTab}
            onSelectTab={setActiveTab}
            authEnabled={authEnabled}
            onLogout={() => void handleLogout()}
          />

          <SidebarInset>
            <header className="sticky top-0 z-10 flex h-12 shrink-0 items-center justify-between gap-2 border-b bg-background/95 px-4 backdrop-blur-xs">
              <div className="flex items-center gap-2">
                <SidebarTrigger className="-ml-1" />
                <Separator orientation="vertical" className="mr-2 h-4" />
                <span className="text-sm font-medium">
                  {TAB_TITLES[activeTab]}
                </span>
              </div>
              <ModeToggle />
            </header>

            <main
              className={`mx-auto w-full flex-1 p-4 md:p-6 ${
                activeTab === "label-imp" ||
                activeTab === "extractor" ||
                activeTab === "ai-design" ||
                activeTab === "vectorcraft"
                  ? "max-w-[1800px]"
                  : "max-w-6xl"
              }`}
            >
              <div className={activeTab === "sela" ? "block" : "hidden"}>
                <SelaTab
                  ready={appReady}
                  onSendToLabelImp={handleSendToLabelImp}
                />
              </div>

              <div className={activeTab === "extractor" ? "block" : "hidden"}>
                <ExtractorTab
                  onSendToLabelImp={handleSendToLabelImp}
                  onSendToPrintImp={handleSendToPrintImp}
                />
              </div>

              <div className={activeTab === "label-imp" ? "block" : "hidden"}>
                <LabelImpTab
                  handoff={labelHandoff}
                  onClearHandoff={() => setLabelHandoff(null)}
                />
              </div>

              <div className={activeTab === "print-imp" ? "block" : "hidden"}>
                <PrintImpTab
                  ready={appReady}
                  handoff={printHandoff}
                  onClearHandoff={() => setPrintHandoff(null)}
                />
              </div>

              <div className={activeTab === "ai-design" ? "block" : "hidden"}>
                <AiDesignTab
                  ready={appReady}
                  onOpenInVectorCraft={handleOpenInVectorCraft}
                  onSendToLabelImp={handleSendToLabelImp}
                  onSendToPrintImp={handleSendToPrintImp}
                />
              </div>

              <div className={activeTab === "vectorcraft" ? "block" : "hidden"}>
                <VectorCraftTab
                  ready={appReady}
                  active={appReady && activeTab === "vectorcraft"}
                  handoff={vectorCraftHandoff}
                  onClearHandoff={() => setVectorCraftHandoff(null)}
                  onSendToLabelImp={handleSendToLabelImp}
                  onSendToPrintImp={handleSendToPrintImp}
                />
              </div>

              <div className={activeTab === "gears" ? "block" : "hidden"}>
                <GearsTab active={appReady && activeTab === "gears"} />
              </div>
            </main>
          </SidebarInset>

          <LoginDialog
            open={authChecked && !authenticated}
            onSuccess={() => setAuthenticated(true)}
          />
          <Toaster position="bottom-right" richColors />
        </SidebarProvider>
      </TooltipProvider>
    </ThemeProvider>
  )
}
