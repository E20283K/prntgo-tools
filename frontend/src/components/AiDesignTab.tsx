import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ClipboardEvent,
} from "react"
import {
  BookOpen,
  Bot,
  CheckCircle2,
  Cylinder,
  Download,
  ExternalLink,
  FileCode2,
  FileText,
  FolderArchive,
  FolderOpen,
  KeyRound,
  LayoutGrid,
  Loader2,
  PenTool,
  Plus,
  RefreshCw,
  Save,
  Sparkles,
  Square,
  TerminalSquare,
  Trash2,
  Upload,
  Wrench,
  XCircle,
} from "lucide-react"
import { toast } from "sonner"

import { ClaudeTerminal } from "@/components/ClaudeTerminal"
import { CorelExportBar, useCorelSettings } from "@/components/CorelExportBar"
import { PdfPreview } from "@/components/PdfPreview"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  aiAssetFileUrl,
  apiFetch,
  jobFileUrl,
  type AiAssetItem,
  type AiDesignGenerateResponse,
  type AiDesignStatusResponse,
  type AiSkillDetail,
  type AiSkillSummary,
  type LabelHandoff,
  type PrintHandoff,
  type VectorCraftHandoff,
} from "@/lib/api"

type AiDesignRunStatus = "running" | "done" | "error" | "cancelled"

interface AiDesignRunLog {
  seq: number
  t: number
  kind:
    | "info"
    | "assistant"
    | "thinking"
    | "tool"
    | "tool_result"
    | "error"
    | "success"
    | "raw"
  text: string
}

interface AiDesignRunSnapshot {
  run_id: string
  status: AiDesignRunStatus
  job_id: string | null
  elapsed_sec: number
  logs: AiDesignRunLog[]
  next: number
  result: AiDesignGenerateResponse | null
  error: string | null
}

const LOG_KIND_STYLE: Record<AiDesignRunLog["kind"], string> = {
  info: "text-sky-300",
  assistant: "text-zinc-100",
  thinking: "text-zinc-500 italic",
  tool: "text-amber-300",
  tool_result: "text-zinc-400",
  error: "text-red-400",
  success: "text-emerald-400 font-medium",
  raw: "text-zinc-500",
}

const LOG_KIND_PREFIX: Record<AiDesignRunLog["kind"], string> = {
  info: "•",
  assistant: "Claude:",
  thinking: "…",
  tool: "→",
  tool_result: "←",
  error: "✕",
  success: "✓",
  raw: " ",
}

interface AiDesignTabProps {
  ready: boolean
  onOpenInVectorCraft: (handoff: VectorCraftHandoff) => void
  onSendToLabelImp: (handoff: LabelHandoff) => void
  onSendToPrintImp: (handoff: PrintHandoff) => void
}

const DESIGN_PRESETS = [
  {
    label: "Kosmetika etiketkasi (60×40 mm)",
    width: "60",
    height: "40",
    basename: "cosmetic_label",
    prompt:
      "60x40 mm o'lchamda zamonaviy premium kosmetika etiketkasi dizaynini yarat. To'q zumrad (#0f172a) fon, oltin (#f59e0b) dekorativ ichki ramka, markazda 'AROMA LUX' brend nomi, pastrog'ida 'NATURAL FACE SERUM • 50 ML' yozuvi va nafis vektorli barg/ornament elementi bo'lsin.",
  },
  {
    label: "Kiyim birkasi / Hang-Tag (50×90 mm)",
    width: "50",
    height: "90",
    basename: "fashion_hangtag",
    prompt:
      "50x90 mm o'lchamda tekstil kiyim birkasi (hang-tag) dizaynini yarat. Yuqori markazda diametri 4mm teshik joyi, minimalist geometrik vektor naqsh, 'URBAN COLLECTION' sarlavhasi, '100% ORGANIC COTTON', o'lcham ('L / XL') bloki va pastki qismda shtrix-kod uchun oq zona bo'lsin.",
  },
  {
    label: "Qadoq stikeri / Oziq-ovqat (80×50 mm)",
    width: "80",
    height: "50",
    basename: "food_sticker",
    prompt:
      "80x50 mm o'lchamda tabiiy asal qadoq stikerini yarat. Iliq kahrabo va oltin ranglar palitrasi, oltiburchak (asalari uyasi) vektorli geometrik elementlar, markazda 'TOZA TOG' ASALI', '100% TABIIY MAHSULOT • 500g' matni va kesish konturi (dieline) bo'lsin.",
  },
  {
    label: "Aksiya / Badge Stiker (50×50 mm)",
    width: "50",
    height: "50",
    basename: "promo_badge",
    prompt:
      "50x50 mm kvadrat artboard ichida yorqin yulduz/rozetka shaklidagi aksiya stikerini yarat. Qizil va sariq kontrast ranglar, markazda katta 'PREMIUM SIFAT' va '100% KAFOLAT' yozuvi hamda dekorativ aylana hoshiyalar bo'lsin.",
  },
]

export function AiDesignTab({
  ready,
  onOpenInVectorCraft,
  onSendToLabelImp,
  onSendToPrintImp,
}: AiDesignTabProps) {
  const [subTab, setSubTab] = useState<string>("terminal")
  const [status, setStatus] = useState<AiDesignStatusResponse | null>(null)
  const [statusLoading, setStatusLoading] = useState(false)

  // Skills & Assets catalog
  const [skills, setSkills] = useState<AiSkillSummary[]>([])
  const [assets, setAssets] = useState<AiAssetItem[]>([])

  // Studio generator form state
  const [prompt, setPrompt] = useState(DESIGN_PRESETS[0].prompt)
  const [widthMm, setWidthMm] = useState(DESIGN_PRESETS[0].width)
  const [heightMm, setHeightMm] = useState(DESIGN_PRESETS[0].height)
  const [outputBasename, setOutputBasename] = useState(DESIGN_PRESETS[0].basename)
  const [selectedSkills, setSelectedSkills] = useState<string[]>([])
  const [selectedAssets, setSelectedAssets] = useState<string[]>([])
  const [inputFiles, setInputFiles] = useState<File[]>([])
  const [dragOver, setDragOver] = useState(false)

  const addInputFiles = useCallback((files: File[], source: string) => {
    if (files.length === 0) return
    const stamp = new Date()
      .toISOString()
      .replace(/[-:T]/g, "")
      .slice(0, 14)
    const normalized = files.map((f, i) => {
      // Clipboard images usually come as "image.png" — give them unique names
      if (!f.name || /^image\.(png|jpe?g|gif|webp|bmp)$/i.test(f.name)) {
        const ext = (f.type.split("/")[1] || "png").replace("jpeg", "jpg")
        return new File([f], `pasted-${stamp}-${i + 1}.${ext}`, {
          type: f.type,
          lastModified: Date.now(),
        })
      }
      return f
    })
    setInputFiles((prev) => {
      const key = (f: File) => `${f.name}:${f.size}`
      const existing = new Set(prev.map(key))
      return [...prev, ...normalized.filter((f) => !existing.has(key(f)))]
    })
    toast.success(`${normalized.length} ta fayl biriktirildi (${source})`)
  }, [])

  const handlePasteFiles = useCallback(
    (e: ClipboardEvent) => {
      const items = Array.from(e.clipboardData?.items ?? [])
      const files = items
        .filter((it) => it.kind === "file")
        .map((it) => it.getAsFile())
        .filter((f): f is File => !!f)
      if (files.length === 0) return // plain text paste — leave as is
      e.preventDefault()
      addInputFiles(files, "bufer")
    },
    [addInputFiles]
  )

  function removeInputFile(index: number) {
    setInputFiles((prev) => prev.filter((_, i) => i !== index))
  }
  const [sourceJobId, setSourceJobId] = useState<string | null>(null)
  const [sourceFilename, setSourceFilename] = useState<string | null>(null)
  const [generating, setGenerating] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [runId, setRunId] = useState<string | null>(null)
  const [runStatus, setRunStatus] = useState<AiDesignRunStatus | null>(null)
  const [runLogs, setRunLogs] = useState<AiDesignRunLog[]>([])
  const [runElapsed, setRunElapsed] = useState(0)
  const pollTokenRef = useRef(0)
  const logBoxRef = useRef<HTMLDivElement>(null)
  const logStickRef = useRef(true)

  // Stop polling when the component unmounts
  useEffect(() => () => void (pollTokenRef.current += 1), [])

  // Auto-scroll the live log to the bottom unless the user scrolled up
  useEffect(() => {
    const el = logBoxRef.current
    if (el && logStickRef.current) el.scrollTop = el.scrollHeight
  }, [runLogs])
  const [result, setResult] = useState<AiDesignGenerateResponse | null>(null)

  // Claude Auth & Login state
  const [oauthTokenInput, setOauthTokenInput] = useState("")
  const [apiKeyInput, setApiKeyInput] = useState("")
  const [loginCodeInput, setLoginCodeInput] = useState("")
  const [authBusy, setAuthBusy] = useState(false)

  // Skill editor state
  const [activeSkillSlug, setActiveSkillSlug] = useState<string | null>(null)
  const [skillName, setSkillName] = useState("")
  const [skillDesc, setSkillDesc] = useState("")
  const [skillContent, setSkillContent] = useState("")
  const [skillExtraFiles, setSkillExtraFiles] = useState<
    Array<{ name: string; size_kb: number }>
  >([])
  const [skillSaving, setSkillSaving] = useState(false)

  // Workspace config (.mcp.json & CLAUDE.md)
  const [mcpJson, setMcpJson] = useState("")
  const [claudeMd, setClaudeMd] = useState("")
  const [configSaving, setConfigSaving] = useState(false)

  const corel = useCorelSettings()

  const loadAllData = useCallback(async () => {
    if (!ready) return
    setStatusLoading(true)
    try {
      const [stRes, skRes, asRes, cfgRes] = await Promise.all([
        apiFetch("/api/ai-design/status"),
        apiFetch("/api/ai-design/skills"),
        apiFetch("/api/ai-design/assets"),
        apiFetch("/api/ai-design/workspace-config"),
      ])
      const stData: AiDesignStatusResponse = await stRes.json()
      const skData: { skills: AiSkillSummary[] } = await skRes.json()
      const asData: { assets: AiAssetItem[] } = await asRes.json()
      const cfgData: { mcp_json: string; claude_md: string } = await cfgRes.json()

      setStatus(stData)
      setSkills(skData.skills)
      setAssets(asData.assets)
      setMcpJson(cfgData.mcp_json)
      setClaudeMd(cfgData.claude_md)

      setSelectedSkills((prev) =>
        prev.length > 0 ? prev : skData.skills.map((s) => s.slug)
      )
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Ma'lumotlarni yuklashda xato")
    } finally {
      setStatusLoading(false)
    }
  }, [ready])

  useEffect(() => {
    void loadAllData()
  }, [loadAllData])

  async function handleSelectSkillForEdit(slug: string) {
    try {
      const res = await apiFetch(`/api/ai-design/skills/${encodeURIComponent(slug)}`)
      const detail: AiSkillDetail = await res.json()
      setActiveSkillSlug(detail.slug)
      setSkillName(detail.name)
      setSkillDesc(detail.description)
      setSkillContent(detail.content)
      setSkillExtraFiles(detail.extra_files)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Skill yuklashda xato")
    }
  }

  function handleNewSkillDraft() {
    setActiveSkillSlug(null)
    setSkillName("my-custom-design-skill")
    setSkillDesc("Maxsus etiketka va vektor dizayn qoidalari")
    setSkillContent(
      `---\nname: my-custom-design-skill\ndescription: Maxsus etiketka va vektor dizayn qoidalari\n---\n\n# Maxsus Dizayn Qoidalari\n\n1. Artboard o'lchamini aniq mm -> pt bo'yicha yarating.\n2. VectorCraft MCP tool'lari orqali shakllar, matnlar va logotiplarni joylashtiring.\n3. Natijani ham .vectorcraft, ham .pdf formatda saqlang.\n`
    )
    setSkillExtraFiles([])
  }

  async function handleSaveSkill() {
    if (!skillName.trim()) {
      toast.error("Skill nomini kiriting.")
      return
    }
    setSkillSaving(true)
    try {
      const res = await apiFetch("/api/ai-design/skills", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          slug: activeSkillSlug,
          name: skillName,
          description: skillDesc,
          content: skillContent,
        }),
      })
      const saved: AiSkillDetail = await res.json()
      setActiveSkillSlug(saved.slug)
      setSkillName(saved.name)
      setSkillDesc(saved.description)
      setSkillContent(saved.content)
      setSkillExtraFiles(saved.extra_files)
      toast.success(`Skill saqlandi: ${saved.slug}`)
      await loadAllData()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Skill saqlashda xato")
    } finally {
      setSkillSaving(false)
    }
  }

  async function handleDeleteSkill(slug: string) {
    try {
      await apiFetch(`/api/ai-design/skills/${encodeURIComponent(slug)}`, {
        method: "DELETE",
      })
      if (activeSkillSlug === slug) {
        setActiveSkillSlug(null)
        setSkillName("")
        setSkillDesc("")
        setSkillContent("")
        setSkillExtraFiles([])
      }
      toast.success(`Skill o'chirildi: ${slug}`)
      await loadAllData()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "O'chirishda xato")
    }
  }

  async function handleUploadSkillExtraFile(file: File) {
    const targetSlug = activeSkillSlug || skillName.trim()
    if (!targetSlug) {
      toast.error("Avval skillni tanlang yoki nom bering.")
      return
    }
    const fd = new FormData()
    fd.append("file", file)
    try {
      const res = await apiFetch(
        `/api/ai-design/skills/${encodeURIComponent(targetSlug)}/files`,
        {
          method: "POST",
          body: fd,
        }
      )
      const detail: AiSkillDetail = await res.json()
      setActiveSkillSlug(detail.slug)
      setSkillName(detail.name)
      setSkillDesc(detail.description)
      setSkillContent(detail.content)
      setSkillExtraFiles(detail.extra_files)
      toast.success(`Fayl skill ichiga yuklandi: ${file.name}`)
      await loadAllData()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Fayl yuklashda xato")
    }
  }

  async function handleDeleteSkillExtraFile(filename: string) {
    if (!activeSkillSlug) return
    try {
      const res = await apiFetch(
        `/api/ai-design/skills/${encodeURIComponent(activeSkillSlug)}/files/${encodeURIComponent(filename)}`,
        { method: "DELETE" }
      )
      const detail: AiSkillDetail = await res.json()
      setSkillExtraFiles(detail.extra_files)
      toast.success(`O'chirildi: ${filename}`)
      await loadAllData()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Fayl o'chirishda xato")
    }
  }

  async function handleUploadServerAssets(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return
    const fd = new FormData()
    Array.from(fileList).forEach((f) => fd.append("files", f))
    try {
      const res = await apiFetch("/api/ai-design/assets", {
        method: "POST",
        body: fd,
      })
      const data: { assets: AiAssetItem[] } = await res.json()
      setAssets(data.assets)
      toast.success(`${fileList.length} ta fayl server assets papkasiga saqlandi!`)
      await loadAllData()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Asset yuklashda xato")
    }
  }

  async function handleDeleteAsset(filename: string) {
    try {
      await apiFetch(`/api/ai-design/assets/${encodeURIComponent(filename)}`, {
        method: "DELETE",
      })
      setAssets((prev) => prev.filter((a) => a.name !== filename))
      setSelectedAssets((prev) => prev.filter((n) => n !== filename))
      toast.success(`Asset o'chirildi: ${filename}`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Asset o'chirishda xato")
    }
  }

  async function handleStartClaudeLogin() {
    setAuthBusy(true)
    try {
      const res = await apiFetch("/api/ai-design/auth/login/start", {
        method: "POST",
      })
      const sessionState = await res.json()
      await loadAllData()
      if (sessionState.oauth_url) {
        toast.success("Claude login havolasi olindi! Havolani ochib kodni kiriting.")
      } else {
        toast.info(sessionState.message || "Login jarayoni boshlandi.")
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Login boshlashda xato")
    } finally {
      setAuthBusy(false)
    }
  }

  async function handleSubmitLoginCode() {
    if (!loginCodeInput.trim()) {
      toast.error("Tasdiqlash kodini kiriting.")
      return
    }
    setAuthBusy(true)
    try {
      await apiFetch("/api/ai-design/auth/login/code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: loginCodeInput.trim() }),
      })
      setLoginCodeInput("")
      toast.success("Kod yuborildi! Holat yangilanmoqda...")
      await loadAllData()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Kodni tasdiqlashda xato")
    } finally {
      setAuthBusy(false)
    }
  }

  async function handleSaveTokens() {
    setAuthBusy(true)
    try {
      const res = await apiFetch("/api/ai-design/auth/token", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          oauth_token: oauthTokenInput.trim() || undefined,
          api_key: apiKeyInput.trim() || undefined,
        }),
      })
      const stData: AiDesignStatusResponse = await res.json()
      setStatus(stData)
      setOauthTokenInput("")
      setApiKeyInput("")
      toast.success("Claude avtorizatsiya ma'lumotlari saqlandi!")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Token saqlashda xato")
    } finally {
      setAuthBusy(false)
    }
  }

  async function handleSaveWorkspaceConfig() {
    setConfigSaving(true)
    try {
      await apiFetch("/api/ai-design/workspace-config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mcp_json: mcpJson,
          claude_md: claudeMd,
        }),
      })
      toast.success(".mcp.json va CLAUDE.md muvaffaqiyatli saqlandi!")
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Konfiguratsiyani saqlashda xato"
      )
    } finally {
      setConfigSaving(false)
    }
  }

  async function handleGenerateDesign() {
    if (!prompt.trim()) {
      toast.error("Dizayn topshirig'ini kiriting.")
      return
    }
    const myToken = ++pollTokenRef.current
    setGenerating(true)
    setStopping(false)
    setRunLogs([])
    setRunElapsed(0)
    setRunStatus("running")
    setRunId(null)
    try {
      const fd = new FormData()
      fd.append("prompt", prompt.trim())
      fd.append("skill_slugs_json", JSON.stringify(selectedSkills))
      fd.append("asset_names_json", JSON.stringify(selectedAssets))
      if (widthMm.trim()) fd.append("width_mm", widthMm.trim())
      if (heightMm.trim()) fd.append("height_mm", heightMm.trim())
      fd.append("output_basename", outputBasename.trim() || "design")
      if (sourceJobId && sourceFilename) {
        fd.append("source_job_id", sourceJobId)
        fd.append("source_filename", sourceFilename)
      }
      inputFiles.forEach((f) => fd.append("files", f))

      const startRes = await apiFetch("/api/ai-design/generate/start", {
        method: "POST",
        body: fd,
      })
      const { run_id } = (await startRes.json()) as { run_id: string }
      setRunId(run_id)

      // Poll live logs until the run finishes
      let since = 0
      let failures = 0
      while (pollTokenRef.current === myToken) {
        await new Promise((r) => setTimeout(r, 1000))
        if (pollTokenRef.current !== myToken) return
        let snap: AiDesignRunSnapshot
        try {
          const res = await apiFetch(
            `/api/ai-design/generate/runs/${encodeURIComponent(run_id)}?since=${since}`
          )
          snap = await res.json()
          failures = 0
        } catch (err) {
          if (++failures >= 5) throw err
          continue
        }
        if (snap.logs.length > 0) {
          setRunLogs((prev) => [...prev, ...snap.logs].slice(-3000))
        }
        since = snap.next
        setRunElapsed(snap.elapsed_sec)
        setRunStatus(snap.status)

        if (snap.status === "done" && snap.result) {
          setResult(snap.result)
          toast.success("Dizayn muvaffaqiyatli generatsiya qilindi!")
          break
        }
        if (snap.status === "cancelled") {
          toast.info("Generatsiya to'xtatildi.")
          break
        }
        if (snap.status === "error") {
          throw new Error(snap.error || "Dizayn generatsiyasida xatolik")
        }
      }
    } catch (err) {
      setRunStatus("error")
      toast.error(
        err instanceof Error ? err.message : "Dizayn generatsiyasida xatolik"
      )
    } finally {
      if (pollTokenRef.current === myToken) {
        setGenerating(false)
        setStopping(false)
      }
    }
  }

  async function handleStopGeneration() {
    if (!runId) return
    setStopping(true)
    try {
      await apiFetch(
        `/api/ai-design/generate/runs/${encodeURIComponent(runId)}/cancel`,
        { method: "POST" }
      )
    } catch (err) {
      setStopping(false)
      toast.error(err instanceof Error ? err.message : "To'xtatishda xato")
    }
  }

  async function handleSaveJobOutputToAssets(jobId: string, filename: string) {
    const fd = new FormData()
    fd.append("filename", filename)
    try {
      await apiFetch(`/api/ai-design/jobs/${encodeURIComponent(jobId)}/save-asset`, {
        method: "POST",
        body: fd,
      })
      toast.success(`'${filename}' serverdagi doimiy Assets papkasiga saqlandi!`)
      await loadAllData()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Assets'ga saqlashda xato")
    }
  }

  function toggleSkillSelection(slug: string) {
    setSelectedSkills((prev) =>
      prev.includes(slug) ? prev.filter((s) => s !== slug) : [...prev, slug]
    )
  }

  function toggleAssetSelection(name: string) {
    setSelectedAssets((prev) =>
      prev.includes(name) ? prev.filter((a) => a !== name) : [...prev, name]
    )
  }

  return (
    <div className="space-y-6">
      {/* Top Status Strip */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-card p-3.5 shadow-2xs">
        <div className="flex flex-wrap items-center gap-2">
          <Badge
            variant={status?.claude_cli.installed ? "default" : "destructive"}
            className="gap-1.5"
          >
            <Bot className="size-3.5" />
            Claude Code:{" "}
            {status?.claude_cli.installed
              ? status.claude_cli.version
              : "O'rnatilmagan"}
          </Badge>

          <Badge
            variant={status?.auth.authenticated ? "default" : "secondary"}
            className="max-w-full gap-1.5"
          >
            {status?.auth.authenticated ? (
              <CheckCircle2 className="size-3.5 shrink-0 text-emerald-400" />
            ) : (
              <XCircle className="size-3.5 shrink-0 text-amber-400" />
            )}
            <span className="truncate">
              Obuna: {status?.auth.account_info ?? "Tekshirilmoqda..."}
            </span>
          </Badge>

          <Badge
            variant={
              status?.vectorcraft_cli.installed ? "outline" : "destructive"
            }
            className="gap-1.5"
          >
            <PenTool className="size-3.5" />
            VectorCraft MCP:{" "}
            {status?.vectorcraft_cli.installed
              ? status.vectorcraft_cli.version
              : "O'rnatilmagan"}
          </Badge>

          <Badge variant="outline" className="gap-1">
            <BookOpen className="size-3.5" />
            {skills.length} ta Skill
          </Badge>

          <Badge variant="outline" className="gap-1">
            <FolderOpen className="size-3.5" />
            {assets.length} ta Server Asset
          </Badge>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => void loadAllData()}
            disabled={statusLoading}
          >
            <RefreshCw
              className={`mr-1.5 size-3.5 ${statusLoading ? "animate-spin" : ""}`}
            />
            Yangilash
          </Button>
        </div>
      </div>

      <Tabs value={subTab} onValueChange={setSubTab}>
        <TabsList className="grid w-full max-w-2xl grid-cols-1 gap-1 !h-auto md:grid-cols-3 md:gap-0 md:!h-9">
          <TabsTrigger
            value="terminal"
            className="min-w-0 w-full h-auto justify-start gap-1.5 overflow-hidden px-2.5 py-2 md:h-[calc(100%-1px)] md:justify-center md:px-2 md:py-0.5"
          >
            <TerminalSquare className="size-4 shrink-0" />
            <span className="truncate">Claude Code Terminal</span>
          </TabsTrigger>
          <TabsTrigger
            value="studio"
            className="min-w-0 w-full h-auto justify-start gap-1.5 overflow-hidden px-2.5 py-2 md:h-[calc(100%-1px)] md:justify-center md:px-2 md:py-0.5"
          >
            <Sparkles className="size-4 shrink-0" />
            <span className="truncate">Tezkor Forma Generator</span>
          </TabsTrigger>
          <TabsTrigger
            value="settings"
            className="min-w-0 w-full h-auto justify-start gap-1.5 overflow-hidden px-2.5 py-2 md:h-[calc(100%-1px)] md:justify-center md:px-2 md:py-0.5"
          >
            <Wrench className="size-4 shrink-0" />
            <span className="truncate">Skills, Fayllar & Login</span>
          </TabsTrigger>
        </TabsList>

        {/* ================================================================= */}
        {/* SUB-TAB 0: INTERACTIVE CLAUDE CODE WEB TERMINAL (TUI)             */}
        {/* ================================================================= */}
        <TabsContent value="terminal" className="mt-4">
          <ClaudeTerminal
            active={ready && subTab === "terminal"}
            skills={skills}
            assets={assets}
            onOpenInVectorCraft={onOpenInVectorCraft}
            onSendToLabelImp={onSendToLabelImp}
            onSendToPrintImp={onSendToPrintImp}
          />
        </TabsContent>

        {/* ================================================================= */}
        {/* SUB-TAB 1: AI DESIGN GENERATOR STUDIO                             */}
        {/* ================================================================= */}
        <TabsContent value="studio" className="mt-4 space-y-6">
          {status && !status.auth.authenticated && (
            <Alert>
              <KeyRound className="size-4" />
              <AlertTitle>Claude Code obunasi ulanmagan</AlertTitle>
              <AlertDescription className="flex flex-wrap items-center justify-between gap-2">
                <span>
                  Dizayn generatsiya qilish uchun avval Claude Pro/Max obunangizga
                  login qiling yoki OAuth token kiriting.
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setSubTab("settings")}
                >
                  Login bo'limiga o'tish
                </Button>
              </AlertDescription>
            </Alert>
          )}

          <div className="grid gap-6 lg:grid-cols-12">
            {/* LEFT COLUMN: Prompt, Dimensions, Skills & Assets selector */}
            <Card className="lg:col-span-5" onPaste={handlePasteFiles}>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Sparkles className="size-4 text-primary" />
                  VectorCraft AI Dizayn Buyurtmasi
                </CardTitle>
                <CardDescription>
                  Claude Code serverdagi maxsus Skillar va VectorCraft MCP orqali{" "}
                  <code>.vectorcraft</code> hamda <code>.pdf</code> fayllarni
                  generatsiya qiladi.
                </CardDescription>
              </CardHeader>

              <CardContent className="space-y-4">
                {/* Quick Presets */}
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">
                    Tayyor shablon namunalari:
                  </Label>
                  <div className="flex flex-wrap gap-1.5">
                    {DESIGN_PRESETS.map((preset) => (
                      <Button
                        key={preset.basename}
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-7 px-2.5 text-xs"
                        onClick={() => {
                          setPrompt(preset.prompt)
                          setWidthMm(preset.width)
                          setHeightMm(preset.height)
                          setOutputBasename(preset.basename)
                        }}
                      >
                        {preset.label}
                      </Button>
                    ))}
                  </div>
                </div>

                {/* Continuance indicator if iterating on an existing design */}
                {sourceJobId && sourceFilename && (
                  <div className="flex items-center justify-between rounded-lg border border-primary/30 bg-primary/5 px-3 py-2 text-xs">
                    <div className="truncate">
                      <span className="font-semibold">Asos fayl:</span>{" "}
                      <code>{sourceFilename}</code> ({sourceJobId})
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-6 px-2 text-xs"
                      onClick={() => {
                        setSourceJobId(null)
                        setSourceFilename(null)
                      }}
                    >
                      Bekor qilish
                    </Button>
                  </div>
                )}

                {/* Prompt Textarea */}
                <div className="space-y-1.5">
                  <Label htmlFor="ai-prompt">
                    Dizayn topshirig'i (TZ / Batafsil tavsif)
                  </Label>
                  <textarea
                    id="ai-prompt"
                    rows={5}
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    placeholder="Qanday dizayn kerakligini batafsil yozing: o'lchami, ranglari, matnlar, brend nomi, pichoq konturi..."
                    className="flex min-h-[120px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-2xs focus-visible:ring-1 focus-visible:ring-ring focus-visible:outline-none"
                  />
                </div>

                {/* Dimensions & Filename */}
                <div className="grid grid-cols-3 gap-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="ai-w">Kenglik (mm)</Label>
                    <Input
                      id="ai-w"
                      type="number"
                      step="0.5"
                      value={widthMm}
                      onChange={(e) => setWidthMm(e.target.value)}
                      placeholder="60"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="ai-h">Balandlik (mm)</Label>
                    <Input
                      id="ai-h"
                      type="number"
                      step="0.5"
                      value={heightMm}
                      onChange={(e) => setHeightMm(e.target.value)}
                      placeholder="40"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="ai-basename">Fayl nomi</Label>
                    <Input
                      id="ai-basename"
                      value={outputBasename}
                      onChange={(e) => setOutputBasename(e.target.value)}
                      placeholder="design"
                    />
                  </div>
                </div>

                {/* Skills Selection */}
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <Label className="text-xs">
                      Qo'llaniladigan Skillar ({selectedSkills.length}/
                      {skills.length})
                    </Label>
                    <Button
                      type="button"
                      variant="link"
                      size="sm"
                      className="h-auto p-0 text-xs"
                      onClick={() => setSubTab("settings")}
                    >
                      + Skill boshqaruvi
                    </Button>
                  </div>
                  <div className="flex flex-wrap gap-1.5 rounded-lg border bg-muted/20 p-2.5">
                    {skills.length === 0 ? (
                      <span className="text-xs text-muted-foreground">
                        Skillar mavjud emas
                      </span>
                    ) : (
                      skills.map((sk) => {
                        const active = selectedSkills.includes(sk.slug)
                        return (
                          <Badge
                            key={sk.slug}
                            variant={active ? "default" : "outline"}
                            className="cursor-pointer select-none"
                            onClick={() => toggleSkillSelection(sk.slug)}
                            title={sk.description}
                          >
                            {sk.name}
                          </Badge>
                        )
                      })
                    )}
                  </div>
                </div>

                {/* Server Assets Selection */}
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <Label className="text-xs">
                      Serverdagi Fayllar / Shablonlar ({selectedAssets.length}/
                      {assets.length})
                    </Label>
                    <Button
                      type="button"
                      variant="link"
                      size="sm"
                      className="h-auto p-0 text-xs"
                      onClick={() => setSubTab("settings")}
                    >
                      + Fayl yuklash
                    </Button>
                  </div>
                  <div className="flex max-h-28 flex-wrap gap-1.5 overflow-y-auto rounded-lg border bg-muted/20 p-2.5">
                    {assets.length === 0 ? (
                      <span className="text-xs text-muted-foreground">
                        Server assets papkasi bo'sh (Sozlamalar bo'limidan logotip
                        yoki shablon yuklang)
                      </span>
                    ) : (
                      assets.map((as) => {
                        const active =SelectedAssetsIncludes(
                          selectedAssets,
                          as.name
                        )
                        return (
                          <Badge
                            key={as.name}
                            variant={active ? "default" : "outline"}
                            className="cursor-pointer select-none"
                            onClick={() => toggleAssetSelection(as.name)}
                          >
                            {as.name} ({as.size_kb} KB)
                          </Badge>
                        )
                      })
                    )}
                  </div>
                </div>

                {/* Direct Reference File Upload for this Job */}
                <div className="space-y-1.5">
                  <Label htmlFor="ai-files" className="text-xs">
                    Qo'shimcha namuna yoki mavjud fayl biriktirish (.vectorcraft,
                    .pdf, .svg, .png)
                  </Label>
                  <Input
                    id="ai-files"
                    type="file"
                    multiple
                    onChange={(e) => {
                      addInputFiles(
                        e.target.files ? Array.from(e.target.files) : [],
                        "tanlash"
                      )
                      e.target.value = ""
                    }}
                  />
                  <div
                    tabIndex={0}
                    role="button"
                    aria-label="Fayllarni bu yerga Ctrl+V bilan joylang yoki sudrab tashlang"
                    onClick={(e) => e.currentTarget.focus()}
                    onDragOver={(e) => {
                      e.preventDefault()
                      setDragOver(true)
                    }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={(e) => {
                      e.preventDefault()
                      setDragOver(false)
                      addInputFiles(
                        Array.from(e.dataTransfer.files ?? []),
                        "sudrash"
                      )
                    }}
                    className={`flex cursor-text items-center justify-center gap-2 rounded-lg border border-dashed px-3 py-3 text-center text-xs text-muted-foreground outline-none transition-colors focus:border-primary focus:bg-primary/5 focus:text-foreground ${
                      dragOver ? "border-primary bg-primary/5 text-foreground" : ""
                    }`}
                  >
                    <Upload className="size-3.5 shrink-0" />
                    <span>
                      Bu yerni bosib <kbd className="rounded border bg-muted px-1 font-mono">Ctrl</kbd>+
                      <kbd className="rounded border bg-muted px-1 font-mono">V</kbd> bilan
                      buferdan joylang yoki faylni sudrab tashlang
                    </span>
                  </div>
                  {inputFiles.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {inputFiles.map((f, i) => (
                        <Badge
                          key={`${f.name}-${f.size}-${i}`}
                          variant="secondary"
                          className="gap-1 pr-1"
                        >
                          {f.name} ({Math.max(1, Math.round(f.size / 1024))} KB)
                          <button
                            type="button"
                            className="rounded-sm p-0.5 hover:bg-destructive/20 hover:text-destructive"
                            onClick={() => removeInputFile(i)}
                            aria-label={`${f.name} ni olib tashlash`}
                          >
                            <XCircle className="size-3" />
                          </button>
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>

                <div className="flex gap-2">
                  <Button
                    className="flex-1 gap-2"
                    onClick={() => void handleGenerateDesign()}
                    disabled={generating}
                  >
                    {generating ? (
                      <>
                        <Loader2 className="size-4 animate-spin" />
                        Ishlamoqda... {Math.round(runElapsed)} s
                      </>
                    ) : (
                      <>
                        <Sparkles className="size-4" />
                        Dizaynni Generatsiya Qilish (.vectorcraft + .pdf)
                      </>
                    )}
                  </Button>
                  {generating && (
                    <Button
                      variant="destructive"
                      className="gap-2"
                      onClick={() => void handleStopGeneration()}
                      disabled={!runId || stopping}
                    >
                      {stopping ? (
                        <Loader2 className="size-4 animate-spin" />
                      ) : (
                        <Square className="size-4 fill-current" />
                      )}
                      {stopping ? "To'xtatilmoqda..." : "To'xtatish"}
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* RIGHT COLUMN: Generated Outputs, Preview & Handoffs */}
            <div className="space-y-4 lg:col-span-7">
              {(generating || runLogs.length > 0) && (
                <Card>
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between gap-2">
                      <CardTitle className="flex items-center gap-2 text-sm">
                        <TerminalSquare className="size-4" />
                        Jarayon logi (real vaqt)
                      </CardTitle>
                      <div className="flex items-center gap-2">
                        {runStatus && (
                          <Badge
                            variant={
                              runStatus === "error"
                                ? "destructive"
                                : runStatus === "running"
                                  ? "default"
                                  : "secondary"
                            }
                            className="gap-1"
                          >
                            {runStatus === "running" && (
                              <Loader2 className="size-3 animate-spin" />
                            )}
                            {
                              {
                                running: "Ishlamoqda",
                                done: "Tayyor",
                                error: "Xato",
                                cancelled: "To'xtatildi",
                              }[runStatus]
                            }{" "}
                            · {Math.round(runElapsed)} s
                          </Badge>
                        )}
                        {!generating && runLogs.length > 0 && (
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-6 px-2 text-xs"
                            onClick={() => {
                              setRunLogs([])
                              setRunStatus(null)
                            }}
                          >
                            Tozalash
                          </Button>
                        )}
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div
                      ref={logBoxRef}
                      onScroll={(e) => {
                        const el = e.currentTarget
                        logStickRef.current =
                          el.scrollHeight - el.scrollTop - el.clientHeight < 40
                      }}
                      className="h-72 overflow-y-auto rounded-lg bg-zinc-950 p-3 font-mono text-[11px] leading-relaxed"
                    >
                      {runLogs.length === 0 ? (
                        <div className="text-zinc-500">
                          Claude Code ishga tushirilmoqda...
                        </div>
                      ) : (
                        runLogs.map((l) => (
                          <div
                            key={l.seq}
                            className={`whitespace-pre-wrap break-words ${LOG_KIND_STYLE[l.kind] ?? "text-zinc-300"}`}
                          >
                            <span className="mr-2 select-none text-zinc-600">
                              {l.t.toFixed(1).padStart(6, " ")}s
                            </span>
                            <span className="mr-1 select-none">
                              {LOG_KIND_PREFIX[l.kind] ?? ""}
                            </span>
                            {l.text}
                          </div>
                        ))
                      )}
                    </div>
                  </CardContent>
                </Card>
              )}
              {!result ? (
                generating || runLogs.length > 0 ? null : (
                <Card className="flex min-h-[460px] flex-col items-center justify-center p-8 text-center">
                  <PenTool className="mb-3 size-10 text-muted-foreground/50" />
                  <h3 className="text-base font-medium">
                    VectorCraft + Claude Code Natija Oynasi
                  </h3>
                  <p className="mt-1 max-w-md text-xs text-muted-foreground">
                    Chap tomondan dizayn topshirig'ini yuboring. Claude Code
                    VectorCraft MCP orqali dizaynni chizib, sizga{" "}
                    <strong>.vectorcraft</strong> va <strong>.pdf</strong>{" "}
                    fayllarni taqdim etadi.
                  </p>
                </Card>
                )
              ) : (
                <>
                  {/* Main Download & Action Bar */}
                  <Card>
                    <CardHeader className="pb-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <CardTitle className="text-base">
                            Tayyor Dizayn Fayllari
                          </CardTitle>
                          <CardDescription>
                            Job: <code>{result.job_id}</code> • Vaqt:{" "}
                            {result.duration_sec} s
                          </CardDescription>
                        </div>

                        <div className="flex flex-wrap items-center gap-2">
                          {result.vectorcraft_file && (
                            <Button
                              size="sm"
                              className="gap-1.5"
                              nativeButton={false}
                              render={
                                <a
                                  href={jobFileUrl(
                                    result.job_id,
                                    result.vectorcraft_file
                                  )}
                                  download={result.vectorcraft_file}
                                />
                              }
                            >
                              <Download className="size-3.5" />
                              {result.vectorcraft_file} (.vectorcraft)
                            </Button>
                          )}

                          {result.pdf_file && (
                            <Button
                              size="sm"
                              variant="secondary"
                              className="gap-1.5"
                              nativeButton={false}
                              render={
                                <a
                                  href={jobFileUrl(
                                    result.job_id,
                                    result.pdf_file
                                  )}
                                  download={result.pdf_file}
                                />
                              }
                            >
                              <FileText className="size-3.5" />
                              {result.pdf_file} (.pdf)
                            </Button>
                          )}

                          {result.zip_file && (
                            <Button
                              size="sm"
                              variant="outline"
                              className="gap-1.5"
                              nativeButton={false}
                              render={
                                <a
                                  href={jobFileUrl(
                                    result.job_id,
                                    result.zip_file
                                  )}
                                  download={result.zip_file}
                                />
                              }
                            >
                              <FolderArchive className="size-3.5" />
                              ZIP
                            </Button>
                          )}
                        </div>
                      </div>
                    </CardHeader>

                    <CardContent className="space-y-4">
                      {/* Action buttons: Open in VectorCraft Web, Save to Assets, Send to Montaj */}
                      <div className="flex flex-wrap items-center gap-2">
                        {result.vectorcraft_file && (
                          <Button
                            size="sm"
                            variant="outline"
                            className="gap-1.5 border-primary/40 text-primary"
                            onClick={() =>
                              onOpenInVectorCraft({
                                filename: result.vectorcraft_file!,
                                downloadUrl: jobFileUrl(
                                  result.job_id,
                                  result.vectorcraft_file!
                                ),
                                sourceLabel: `AI Dizayn (${result.job_id})`,
                              })
                            }
                          >
                            <PenTool className="size-3.5" />
                            VectorCraft Web'da Tahrirlash
                          </Button>
                        )}

                        {result.vectorcraft_file && (
                          <Button
                            size="sm"
                            variant="outline"
                            className="gap-1.5"
                            onClick={() => {
                              setSourceJobId(result.job_id)
                              setSourceFilename(result.vectorcraft_file!)
                              toast.info(
                                "Endi qo'shimcha o'zgartirish topshirig'ini yozib 'Generatsiya qilish' tugmasini bosing."
                              )
                            }}
                          >
                            <Sparkles className="size-3.5" />
                            Claude bilan davom ettirish
                          </Button>
                        )}

                        {result.vectorcraft_file && (
                          <Button
                            size="sm"
                            variant="outline"
                            className="gap-1.5"
                            onClick={() =>
                              void handleSaveJobOutputToAssets(
                                result.job_id,
                                result.vectorcraft_file!
                              )
                            }
                          >
                            <Save className="size-3.5" />
                            Server Assets'ga saqlash
                          </Button>
                        )}

                        {result.pdf_file && (
                          <>
                            <Button
                              size="sm"
                              variant="outline"
                              className="gap-1.5"
                              onClick={() =>
                                onSendToLabelImp({
                                  job_id: result.job_id,
                                  filename: result.pdf_file!,
                                  total_labels: 1,
                                  source_label: `VectorCraft AI (${result.pdf_file})`,
                                })
                              }
                            >
                              <Cylinder className="size-3.5" />
                              Val Montajiga
                            </Button>

                            <Button
                              size="sm"
                              variant="outline"
                              className="gap-1.5"
                              onClick={() =>
                                onSendToPrintImp({
                                  job_id: result.job_id,
                                  front_filenames: [result.pdf_file!],
                                  trim_w_mm: result.width_mm ?? null,
                                  trim_h_mm: result.height_mm ?? null,
                                  source_label: `VectorCraft AI (${result.pdf_file})`,
                                })
                              }
                            >
                              <LayoutGrid className="size-3.5" />
                              Varaq Montajiga
                            </Button>
                          </>
                        )}
                      </div>

                      {result.pdf_file && (
                        <CorelExportBar
                          jobId={result.job_id}
                          filename={result.pdf_file}
                          version={corel.version}
                          onVersionChange={corel.setVersion}
                          askOnRun={corel.askOnRun}
                          onAskOnRunChange={corel.setAskOnRun}
                        />
                      )}

                      {/* All generated files list */}
                      {result.output_files.length > 0 && (
                        <div className="flex flex-wrap gap-2 pt-1">
                          {result.output_files.map((f) => (
                            <Badge
                              key={f.filename}
                              variant="secondary"
                              className="gap-1.5 py-1"
                            >
                              <span className="font-mono text-xs">
                                {f.filename}
                              </span>
                              <span className="text-[10px] text-muted-foreground">
                                ({f.size_kb} KB)
                              </span>
                              <a
                                href={jobFileUrl(result.job_id, f.filename)}
                                download={f.filename}
                                className="ml-1 underline"
                              >
                                Yuklash
                              </a>
                            </Badge>
                          ))}
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  {/* PDF Interactive Preview */}
                  {result.pdf_file && (
                    <PdfPreview
                      src={jobFileUrl(result.job_id, result.pdf_file, true)}
                      title={result.pdf_file}
                      downloadUrl={jobFileUrl(result.job_id, result.pdf_file)}
                      downloadFilename={result.pdf_file}
                      iframeClassName="h-[480px]"
                    />
                  )}

                  {/* Claude Code Assistant Summary */}
                  {result.assistant_reply && (
                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="flex items-center gap-2 text-sm">
                          <Bot className="size-4 text-primary" />
                          Claude Code Hisoboti
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <pre className="max-h-64 overflow-y-auto rounded-lg bg-muted/40 p-3 font-sans text-xs whitespace-pre-wrap">
                          {result.assistant_reply}
                        </pre>
                      </CardContent>
                    </Card>
                  )}
                </>
              )}
            </div>
          </div>
        </TabsContent>

        {/* ================================================================= */}
        {/* SUB-TAB 2: SKILLS, SERVER ASSETS & CLAUDE AUTH MANAGER            */}
        {/* ================================================================= */}
        <TabsContent value="settings" className="mt-4 space-y-6">
          {/* 1. CLAUDE SUBSCRIPTION LOGIN & AUTH */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <KeyRound className="size-4 text-primary" />
                1. Claude Code Obuna (Subscription) va Avtorizatsiya
              </CardTitle>
              <CardDescription>
                Claude Pro yoki Max obunangizni brauzer orqali OAuth havola bilan
                yoki <code>claude setup-token</code> orqali olingan token bilan
                ulang. Ma'lumotlar <code>/app/data/claude_home</code> ichida
                doimiy saqlanadi.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-6 md:grid-cols-2">
              {/* Method A: Interactive OAuth Login via Browser URL */}
              <div className="space-y-3 rounded-lg border p-4">
                <div className="flex items-center justify-between">
                  <h4 className="text-sm font-medium">
                    A-usul: Brauzer orqali Claude Login (OAuth)
                  </h4>
                  <Badge
                    variant={
                      status?.auth.authenticated ? "default" : "secondary"
                    }
                  >
                    {status?.auth.authenticated ? "Ulangan" : "Ulanmagan"}
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground">
                  Tugmani bossangiz serverda <code>claude auth login</code>{" "}
                  ishga tushadi va maxsus kirish havolasi chiqadi.
                </p>

                <Button
                  size="sm"
                  onClick={() => void handleStartClaudeLogin()}
                  disabled={authBusy}
                  className="gap-1.5"
                >
                  {authBusy ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <ExternalLink className="size-3.5" />
                  )}
                  Claude Login Havolasini Olish
                </Button>

                {status?.auth.login_session?.oauth_url && (
                  <div className="space-y-2 rounded-md border border-primary/30 bg-primary/5 p-3 text-xs">
                    <div className="font-medium">
                      1. Quyidagi havolani ochib Claude akkauntingiz bilan
                      tasdiqlang:
                    </div>
                    <a
                      href={status.auth.login_session.oauth_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block break-all text-primary underline"
                    >
                      {status.auth.login_session.oauth_url}
                    </a>
                    <div className="pt-1 font-medium">
                      2. Brauzer bergan tasdiqlash kodini kiriting:
                    </div>
                    <div className="flex gap-2">
                      <Input
                        value={loginCodeInput}
                        onChange={(e) => setLoginCodeInput(e.target.value)}
                        placeholder="Tasdiqlash kodi..."
                        className="h-8 text-xs"
                      />
                      <Button
                        size="sm"
                        className="h-8"
                        onClick={() => void handleSubmitLoginCode()}
                        disabled={authBusy}
                      >
                        Tasdiqlash
                      </Button>
                    </div>
                  </div>
                )}

                {status?.auth.login_session?.output && (
                  <pre className="max-h-28 overflow-y-auto rounded bg-muted p-2 font-mono text-[11px] whitespace-pre-wrap">
                    {status.auth.login_session.output}
                  </pre>
                )}
              </div>

              {/* Method B: Direct OAuth Token or API Key */}
              <div className="space-y-3 rounded-lg border p-4">
                <h4 className="text-sm font-medium">
                  B-usul: OAuth Token (<code>claude setup-token</code>) yoki API
                  Kalit
                </h4>
                <p className="text-xs text-muted-foreground">
                  Kompyuteringizda <code>claude setup-token</code> buyrug'ini
                  ishga tushirib olingan obuna tokenini shu yerga kiritsangiz,
                  darhol ulanadi.
                </p>

                <div className="space-y-1.5">
                  <Label className="text-xs">
                    CLAUDE_CODE_OAUTH_TOKEN{" "}
                    {status?.auth.masked_oauth_token && (
                      <span className="text-emerald-500">
                        (Saqlangan: {status.auth.masked_oauth_token})
                      </span>
                    )}
                  </Label>
                  <Input
                    type="password"
                    value={oauthTokenInput}
                    onChange={(e) => setOauthTokenInput(e.target.value)}
                    placeholder="sk-ant-oat01-..."
                    className="h-8 text-xs"
                  />
                </div>

                <div className="space-y-1.5">
                  <Label className="text-xs">
                    ANTHROPIC_API_KEY (Ixtiyoriy zaxira){" "}
                    {status?.auth.masked_api_key && (
                      <span className="text-emerald-500">
                        (Saqlangan: {status.auth.masked_api_key})
                      </span>
                    )}
                  </Label>
                  <Input
                    type="password"
                    value={apiKeyInput}
                    onChange={(e) => setApiKeyInput(e.target.value)}
                    placeholder="sk-ant-api03-..."
                    className="h-8 text-xs"
                  />
                </div>

                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => void handleSaveTokens()}
                  disabled={authBusy}
                  className="gap-1.5"
                >
                  <Save className="size-3.5" />
                  Tokenni Saqlash
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* 2. SKILLS MANAGER (.claude/skills/<slug>/SKILL.md) */}
          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <BookOpen className="size-4 text-primary" />
                    2. Claude Code Maxsus Skillar Boshqaruvi (
                    <code>.claude/skills/</code>)
                  </CardTitle>
                  <CardDescription>
                    Har bir skill o'zining <code>SKILL.md</code> yo'riqnomasiga va
                    qo'shimcha shablon/skript fayllariga ega bo'lishi mumkin.
                  </CardDescription>
                </div>
                <Button
                  size="sm"
                  onClick={handleNewSkillDraft}
                  className="gap-1.5"
                >
                  <Plus className="size-3.5" />
                  Yangi Skill Yaratish
                </Button>
              </div>
            </CardHeader>

            <CardContent className="grid gap-6 lg:grid-cols-12">
              {/* Skills List */}
              <div className="space-y-2 lg:col-span-4">
                {skills.map((sk) => (
                  <div
                    key={sk.slug}
                    className={`flex items-start justify-between gap-2 rounded-lg border p-3 transition-colors ${
                      activeSkillSlug === sk.slug
                        ? "border-primary bg-primary/5"
                        : "hover:bg-muted/40"
                    }`}
                  >
                    <button
                      type="button"
                      className="min-w-0 flex-1 text-left"
                      onClick={() => void handleSelectSkillForEdit(sk.slug)}
                    >
                      <div className="truncate text-sm font-medium">
                        {sk.name}
                      </div>
                      <div className="font-mono text-[11px] text-muted-foreground">
                        .claude/skills/{sk.slug}/SKILL.md
                      </div>
                      {sk.description && (
                        <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                          {sk.description}
                        </p>
                      )}
                      {sk.extra_files.length > 0 && (
                        <Badge variant="secondary" className="mt-1.5 text-[10px]">
                          +{sk.extra_files.length} ta fayl
                        </Badge>
                      )}
                    </button>

                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0 text-destructive"
                      onClick={() => void handleDeleteSkill(sk.slug)}
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </div>
                ))}
              </div>

              {/* Skill Editor */}
              <div className="space-y-4 rounded-lg border p-4 lg:col-span-8">
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Skill nomi (slug)</Label>
                    <Input
                      value={skillName}
                      onChange={(e) => setSkillName(e.target.value)}
                      placeholder="masalan: etiketka-dizayn-standarti"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Qisqacha tavsif</Label>
                    <Input
                      value={skillDesc}
                      onChange={(e) => setSkillDesc(e.target.value)}
                      placeholder="Ushbu skill nima vazifa bajaradi?"
                    />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <Label className="text-xs">
                    <code>SKILL.md</code> tarkibi (Markdown + YAML frontmatter)
                  </Label>
                  <textarea
                    rows={12}
                    value={skillContent}
                    onChange={(e) => setSkillContent(e.target.value)}
                    placeholder="Skill qoidalari va VectorCraft ko'rsatmalarini shu yerga yozing..."
                    className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 font-mono text-xs shadow-2xs focus-visible:ring-1 focus-visible:ring-ring focus-visible:outline-none"
                  />
                </div>

                {/* Extra files inside the skill folder */}
                <div className="space-y-2 rounded-md border bg-muted/20 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <Label className="text-xs">
                      Skill ichidagi qo'shimcha fayllar (yoki .zip skill paketi
                      yuklash)
                    </Label>
                    <label className="cursor-pointer">
                      <input
                        type="file"
                        className="hidden"
                        onChange={(e) => {
                          const f = e.target.files?.[0]
                          if (f) void handleUploadSkillExtraFile(f)
                        }}
                      />
                      <span className="inline-flex h-7 items-center gap-1 rounded-md border bg-background px-2.5 text-xs font-medium hover:bg-muted">
                        <Upload className="size-3" />
                        Skillga fayl / ZIP qo'shish
                      </span>
                    </label>
                  </div>

                  {skillExtraFiles.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {skillExtraFiles.map((ef) => (
                        <Badge
                          key={ef.name}
                          variant="outline"
                          className="gap-1.5"
                        >
                          <span className="font-mono text-xs">{ef.name}</span>
                          <span className="text-[10px] text-muted-foreground">
                            ({ef.size_kb} KB)
                          </span>
                          <button
                            type="button"
                            className="text-destructive hover:underline"
                            onClick={() =>
                              void handleDeleteSkillExtraFile(ef.name)
                            }
                          >
                            ×
                          </button>
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>

                <div className="flex justify-end">
                  <Button
                    onClick={() => void handleSaveSkill()}
                    disabled={skillSaving}
                    className="gap-1.5"
                  >
                    {skillSaving ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <Save className="size-4" />
                    )}
                    Skillni Saqlash
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* 3. SERVER ASSETS MANAGER (/app/data/claude_workspace/assets/) */}
          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <FolderOpen className="size-4 text-primary" />
                    3. Serverdagi Doimiy Dizayn Fayllari (
                    <code>/app/data/claude_workspace/assets/</code>)
                  </CardTitle>
                  <CardDescription>
                    Claude Code va VectorCraft foydalanishi uchun shablonlar (
                    <code>.vectorcraft</code>, <code>.svg</code>,{" "}
                    <code>.pdf</code>), logotiplar va shriftlarni serverda
                    saqlang.
                  </CardDescription>
                </div>

                <label className="cursor-pointer">
                  <input
                    type="file"
                    multiple
                    className="hidden"
                    onChange={(e) =>
                      void handleUploadServerAssets(e.target.files)
                    }
                  />
                  <span className="inline-flex h-9 items-center gap-1.5 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground shadow-2xs hover:bg-primary/90">
                    <Upload className="size-3.5" />
                    Serverga Fayllar Yuklash
                  </span>
                </label>
              </div>
            </CardHeader>

            <CardContent>
              {assets.length === 0 ? (
                <div className="rounded-lg border border-dashed p-6 text-center text-xs text-muted-foreground">
                  Hozircha hech qanday doimiy fayl yuklanmagan. Yuqoridagi tugma
                  orqali <code>.vectorcraft</code>, <code>.svg</code>,{" "}
                  <code>.pdf</code>, logotip yoki shrift yuklang.
                </div>
              ) : (
                <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
                  {assets.map((as) => (
                    <div
                      key={as.name}
                      className="flex items-center justify-between gap-2 rounded-lg border p-2.5"
                    >
                      <div className="min-w-0 flex-1">
                        <div
                          className="truncate font-mono text-xs font-medium"
                          title={as.name}
                        >
                          {as.name}
                        </div>
                        <div className="text-[11px] text-muted-foreground">
                          {as.size_kb} KB • {as.ext || "fayl"}
                        </div>
                      </div>

                      <div className="flex shrink-0 items-center gap-1">
                        {[".vectorcraft", ".svg", ".pdf", ".ai"].includes(
                          as.ext
                        ) && (
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 px-2 text-xs"
                            title="VectorCraft Web'da ochish"
                            onClick={() =>
                              onOpenInVectorCraft({
                                filename: as.name,
                                downloadUrl: aiAssetFileUrl(as.name),
                                sourceLabel: "Server Asset",
                              })
                            }
                          >
                            <PenTool className="size-3" />
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 w-7 p-0"
                          nativeButton={false}
                          render={
                            <a
                              href={aiAssetFileUrl(as.name)}
                              download={as.name}
                            />
                          }
                        >
                          <Download className="size-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 w-7 p-0 text-destructive"
                          onClick={() => void handleDeleteAsset(as.name)}
                        >
                          <Trash2 className="size-3.5" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* 4. MCP (.mcp.json) & CLAUDE.md WORKSPACE CONFIG */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <FileCode2 className="size-4 text-primary" />
                4. VectorCraft MCP (<code>.mcp.json</code>) va{" "}
                <code>CLAUDE.md</code> Sozlamalari
              </CardTitle>
              <CardDescription>
                Claude Code ishga tushganda avtomatik o'qiladigan MCP serverlar va
                tizim yo'riqnomasi.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-1.5">
                  <Label className="text-xs">
                    <code>.mcp.json</code> (VectorCraft va boshqa MCP serverlar)
                  </Label>
                  <textarea
                    rows={8}
                    value={mcpJson}
                    onChange={(e) => setMcpJson(e.target.value)}
                    className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 font-mono text-xs"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">
                    <code>CLAUDE.md</code> (Global Agent Qoidalari)
                  </Label>
                  <textarea
                    rows={8}
                    value={claudeMd}
                    onChange={(e) => setClaudeMd(e.target.value)}
                    className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 font-mono text-xs"
                  />
                </div>
              </div>
              <Separator />
              <div className="flex justify-end">
                <Button
                  size="sm"
                  onClick={() => void handleSaveWorkspaceConfig()}
                  disabled={configSaving}
                  className="gap-1.5"
                >
                  <Save className="size-3.5" />
                  Konfiguratsiyani Saqlash
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}

function SelectedAssetsIncludes(list: string[], name: string): boolean {
  return list.includes(name)
}
