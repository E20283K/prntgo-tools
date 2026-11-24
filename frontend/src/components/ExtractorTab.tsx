import { useEffect, useMemo, useRef, useState } from "react"
import {
  Archive,
  Check,
  CheckCircle2,
  CircleDot,
  Crosshair,
  Cylinder,
  Download,
  FileSearch,
  LayoutGrid,
  Loader2,
  MousePointerClick,
  Plus,
  Ruler,
  Scissors,
  Search,
  Sparkles,
  Trash2,
  UploadCloud,
} from "lucide-react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { Switch } from "@/components/ui/switch"
import { CorelExportBar, useCorelSettings } from "@/components/CorelExportBar"
import { PdfPreview } from "@/components/PdfPreview"
import {
  apiFetch,
  jobCdrBundleUrl,
  jobFileUrl,
  type ExtractorCandidate,
  type ExtractorInspectResponse,
  type ExtractorPageMeta,
  type ExtractorRunResponse,
  type LabelHandoff,
  type PrintHandoff,
} from "@/lib/api"

interface ExtractorTabProps {
  onSendToLabelImp: (handoff: LabelHandoff) => void
  onSendToPrintImp: (handoff: PrintHandoff) => void
}

interface EditableCandidate extends ExtractorCandidate {
  selected: boolean
}

export function ExtractorTab({
  onSendToLabelImp,
  onSendToPrintImp,
}: ExtractorTabProps) {
  const corel = useCorelSettings()

  const [file, setFile] = useState<File | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [inspecting, setInspecting] = useState(false)
  const [inspectData, setInspectData] =
    useState<ExtractorInspectResponse | null>(null)

  const [activePageIndex, setActivePageIndex] = useState<number>(0)
  const [candidates, setCandidates] = useState<EditableCandidate[]>([])
  const [focusedId, setFocusedId] = useState<string | null>(null)

  // Dimension search & manual box tools
  const [searchW, setSearchW] = useState("")
  const [searchH, setSearchH] = useState("")
  const [searchingSize, setSearchingSize] = useState(false)
  const [drawMode, setDrawMode] = useState(false)
  const [drawRole, setDrawRole] = useState<"design" | "dieline">("design")
  const [dragStartMm, setDragStartMm] = useState<[number, number] | null>(null)
  const [dragCurrMm, setDragCurrMm] = useState<[number, number] | null>(null)
  const [movingBox, setMovingBox] = useState<{
    id: string
    startClientX: number
    startClientY: number
    origBbox: [number, number, number, number]
  } | null>(null)

  // Global surgical extraction settings
  const [removeBorder, setRemoveBorder] = useState(false)
  const [removeHole, setRemoveHole] = useState(false)
  const [bleedMm, setBleedMm] = useState("0")
  const [rotationDeg, setRotationDeg] = useState("0")

  // Extraction result
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<ExtractorRunResponse | null>(null)
  const [previewItemIdx, setPreviewItemIdx] = useState<number>(0)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const canvasOverlayRef = useRef<HTMLDivElement>(null)
  const resultRef = useRef<HTMLDivElement>(null)

  const activePage: ExtractorPageMeta | null = useMemo(() => {
    if (!inspectData || !inspectData.pages.length) return null
    return (
      inspectData.pages.find((p) => p.page_index === activePageIndex) ??
      inspectData.pages[0]
    )
  }, [inspectData, activePageIndex])

  const pageCandidates = useMemo(
    () => candidates.filter((c) => c.page_index === activePageIndex),
    [candidates, activePageIndex]
  )

  const selectedCandidates = useMemo(
    () => candidates.filter((c) => c.selected),
    [candidates]
  )

  const focusedCandidate = useMemo(
    () => candidates.find((c) => c.id === focusedId) ?? null,
    [candidates, focusedId]
  )

  async function handleUploadFile(incoming: File) {
    if (!incoming.name.toLowerCase().endsWith(".pdf")) {
      toast.error("Iltimos, faqat .pdf formatidagi fayl tanlang.")
      return
    }
    setFile(incoming)
    setInspecting(true)
    setResult(null)
    try {
      const fd = new FormData()
      fd.append("file", incoming)
      if (searchW.trim()) fd.append("target_w_mm", searchW.trim())
      if (searchH.trim()) fd.append("target_h_mm", searchH.trim())

      const res = await apiFetch("/api/extractor/inspect", {
        method: "POST",
        body: fd,
      })
      const data: ExtractorInspectResponse = await res.json()
      setInspectData(data)

      const editable: EditableCandidate[] = data.candidates.map((c) => ({
        ...c,
        selected: c.selected_by_default,
      }))
      setCandidates(editable)

      // Pick first page that has detected designs, or page 0
      const firstPageWithCandidates =
        data.pages.find((p) => p.candidates_count > 0)?.page_index ?? 0
      setActivePageIndex(firstPageWithCandidates)
      setFocusedId(
        editable.find((c) => c.page_index === firstPageWithCandidates)?.id ??
          editable[0]?.id ??
          null
      )

      // Pre-fill dimension search if page text had explicit dimension hint (e.g. 50x120)
      const firstHint = data.pages[firstPageWithCandidates]?.dimension_hints?.[0]
      if (firstHint && !searchW && !searchH) {
        setSearchW(String(firstHint[0]))
        setSearchH(String(firstHint[1]))
      }

      toast.success(
        `${data.page_count} sahifa tahlil qilindi: ${data.candidates.length} ta obyekt topildi`
      )
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Tahlil xatosi")
    } finally {
      setInspecting(false)
    }
  }

  async function handleSearchBySize() {
    if (!inspectData) {
      toast.error("Avval PDF faylni yuklang.")
      return
    }
    const w = parseFloat(searchW)
    const h = parseFloat(searchH)
    if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) {
      toast.error("Eni va bo'yini (mm) to'g'ri kiriting (masalan: 50 va 120).")
      return
    }
    setSearchingSize(true)
    try {
      const res = await apiFetch("/api/extractor/search-size", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_job_id: inspectData.source_job_id,
          width_mm: w,
          height_mm: h,
          tolerance_mm: 3.0,
        }),
      })
      const data: {
        found_count: number
        candidates: ExtractorCandidate[]
      } = await res.json()

      if (data.found_count === 0) {
        toast.warning(
          `${w}×${h} mm o'lchamdagi tayyor shakl topilmadi. "Qo'lda ramka qo'shish" tugmasini bosing.`
        )
        return
      }

      setCandidates((prev) => {
        const next = [...prev]
        for (const found of data.candidates) {
          const exists = next.find(
            (e) =>
              e.page_index === found.page_index &&
              Math.abs(e.bbox_mm[0] - found.bbox_mm[0]) < 2.0 &&
              Math.abs(e.bbox_mm[1] - found.bbox_mm[1]) < 2.0
          )
          if (exists) {
            exists.selected = true
          } else {
            next.push({
              ...found,
              id: `search_${Date.now()}_${next.length + 1}`,
              selected: true,
            })
          }
        }
        return next
      })
      const firstPage = data.candidates[0].page_index
      setActivePageIndex(firstPage)
      toast.success(`${w}×${h} mm o'lchamga mos ${data.found_count} ta obyekt topildi!`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Qidirishda xatolik")
    } finally {
      setSearchingSize(false)
    }
  }

  function handleAddManualSizedBox() {
    if (!activePage) return
    const w = parseFloat(searchW) || 50
    const h = parseFloat(searchH) || 120
    const clampedW = Math.min(w, activePage.width_mm)
    const clampedH = Math.min(h, activePage.height_mm)
    const x0 = Math.max(0, round2((activePage.width_mm - clampedW) / 2))
    const y0 = Math.max(0, round2((activePage.height_mm - clampedH) / 2))
    const x1 = round2(x0 + clampedW)
    const y1 = round2(y0 + clampedH)

    const newId = `manual_p${activePage.page_number}_${Date.now()}`
    const newItem: EditableCandidate = {
      id: newId,
      page_index: activePage.page_index,
      role: drawRole,
      label: `${drawRole === "design" ? "Dizayn" : "Pichoq"} (${clampedW}×${clampedH} mm)`,
      bbox_mm: [x0, y0, x1, y1],
      width_mm: clampedW,
      height_mm: clampedH,
      has_outer_border: true,
      has_fill: drawRole === "design",
      fill_color_hex: null,
      interior_paths_count: 1,
      interior_texts_count: 0,
      has_hole: false,
      holes_count: 0,
      holes: [],
      confidence: 1.0,
      matches_text_hint: true,
      selected_by_default: true,
      selected: true,
    }
    setCandidates((prev) => [...prev, newItem])
    setFocusedId(newId)
    toast.success(
      `${clampedW}×${clampedH} mm ramka qo'shildi — sahifa ustida sichqoncha bilan kerakli joyga surishingiz mumkin.`
    )
  }

  function round2(n: number) {
    return Math.round(n * 100) / 100
  }

  function clientToPageMm(clientX: number, clientY: number): [number, number] | null {
    if (!canvasOverlayRef.current || !activePage) return null
    const rect = canvasOverlayRef.current.getBoundingClientRect()
    if (rect.width <= 0 || rect.height <= 0) return null
    const relX = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
    const relY = Math.max(0, Math.min(1, (clientY - rect.top) / rect.height))
    return [
      round2(relX * activePage.width_mm),
      round2(relY * activePage.height_mm),
    ]
  }

  function handleCanvasMouseDown(e: React.MouseEvent<HTMLDivElement>) {
    if (!drawMode || !activePage) return
    e.preventDefault()
    const pt = clientToPageMm(e.clientX, e.clientY)
    if (!pt) return
    setDragStartMm(pt)
    setDragCurrMm(pt)
  }

  function handleCanvasMouseMove(e: React.MouseEvent<HTMLDivElement>) {
    if (drawMode && dragStartMm) {
      const pt = clientToPageMm(e.clientX, e.clientY)
      if (pt) setDragCurrMm(pt)
      return
    }
    if (movingBox && activePage && canvasOverlayRef.current) {
      const rect = canvasOverlayRef.current.getBoundingClientRect()
      if (rect.width <= 0 || rect.height <= 0) return
      const dxMm =
        ((e.clientX - movingBox.startClientX) / rect.width) *
        activePage.width_mm
      const dyMm =
        ((e.clientY - movingBox.startClientY) / rect.height) *
        activePage.height_mm

      const [ox0, oy0, ox1, oy1] = movingBox.origBbox
      const w = ox1 - ox0
      const h = oy1 - oy0
      const nx0 = round2(
        Math.max(0, Math.min(activePage.width_mm - w, ox0 + dxMm))
      )
      const ny0 = round2(
        Math.max(0, Math.min(activePage.height_mm - h, oy0 + dyMm))
      )
      const nx1 = round2(nx0 + w)
      const ny1 = round2(ny0 + h)

      setCandidates((prev) =>
        prev.map((c) =>
          c.id === movingBox.id
            ? {
                ...c,
                bbox_mm: [nx0, ny0, nx1, ny1],
              }
            : c
        )
      )
    }
  }

  function handleCanvasMouseUp() {
    if (movingBox) {
      setMovingBox(null)
    }
    if (!drawMode || !dragStartMm || !dragCurrMm || !activePage) return
    const x0 = round2(Math.min(dragStartMm[0], dragCurrMm[0]))
    const y0 = round2(Math.min(dragStartMm[1], dragCurrMm[1]))
    const x1 = round2(Math.max(dragStartMm[0], dragCurrMm[0]))
    const y1 = round2(Math.max(dragStartMm[1], dragCurrMm[1]))
    const w = round2(x1 - x0)
    const h = round2(y1 - y0)

    setDragStartMm(null)
    setDragCurrMm(null)

    if (w < 4 || h < 4) {
      return
    }

    const newId = `drawn_p${activePage.page_number}_${Date.now()}`
    const newItem: EditableCandidate = {
      id: newId,
      page_index: activePage.page_index,
      role: drawRole,
      label: `${drawRole === "design" ? "Dizayn" : "Pichoq"} (${w}×${h} mm)`,
      bbox_mm: [x0, y0, x1, y1],
      width_mm: w,
      height_mm: h,
      has_outer_border: false,
      has_fill: drawRole === "design",
      fill_color_hex: null,
      interior_paths_count: 1,
      interior_texts_count: 0,
      has_hole: false,
      holes_count: 0,
      holes: [],
      confidence: 1.0,
      matches_text_hint: false,
      selected_by_default: true,
      selected: true,
    }
    setCandidates((prev) => [...prev, newItem])
    setFocusedId(newId)
    setDrawMode(false)
    toast.success(`Yangi hudud belgilandi: ${w}×${h} mm`)
  }

  useEffect(() => {
    function onWinUp() {
      setMovingBox(null)
    }
    window.addEventListener("mouseup", onWinUp)
    return () => window.removeEventListener("mouseup", onWinUp)
  }, [])

  function updateCandidateDimension(
    id: string,
    field: "width" | "height" | "x0" | "y0",
    valStr: string
  ) {
    const num = parseFloat(valStr)
    if (!Number.isFinite(num) || num < 0) return
    setCandidates((prev) =>
      prev.map((c) => {
        if (c.id !== id) return c
        let [x0, y0, x1, y1] = c.bbox_mm
        const cx = (x0 + x1) / 2
        const cy = (y0 + y1) / 2
        if (field === "width" && num >= 2) {
          x0 = round2(Math.max(0, cx - num / 2))
          x1 = round2(x0 + num)
        } else if (field === "height" && num >= 2) {
          y0 = round2(Math.max(0, cy - num / 2))
          y1 = round2(y0 + num)
        } else if (field === "x0") {
          const w = x1 - x0
          x0 = round2(num)
          x1 = round2(num + w)
        } else if (field === "y0") {
          const h = y1 - y0
          y0 = round2(num)
          y1 = round2(num + h)
        }
        const nw = round2(x1 - x0)
        const nh = round2(y1 - y0)
        return {
          ...c,
          bbox_mm: [x0, y0, x1, y1],
          width_mm: nw,
          height_mm: nh,
          label: `${c.role === "design" ? "Dizayn" : "Pichoq"} (${nw}×${nh} mm)`,
        }
      })
    )
  }

  function toggleCandidateRole(id: string, nextRole: "design" | "dieline") {
    setCandidates((prev) =>
      prev.map((c) =>
        c.id === id
          ? {
              ...c,
              role: nextRole,
              label: `${nextRole === "design" ? "Dizayn" : "Pichoq"} (${c.width_mm}×${c.height_mm} mm)`,
            }
          : c
      )
    )
  }

  function removeCandidate(id: string) {
    setCandidates((prev) => prev.filter((c) => c.id !== id))
    if (focusedId === id) {
      setFocusedId(null)
    }
  }

  async function handleRunExtraction() {
    if (!inspectData) {
      toast.error("Avval PDF faylni yuklang.")
      return
    }
    if (selectedCandidates.length === 0) {
      toast.error("Ajratib olish uchun kamida bitta dizayn yoki pichoqni belgilang.")
      return
    }
    setRunning(true)
    try {
      const res = await apiFetch("/api/extractor/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_job_id: inspectData.source_job_id,
          items: selectedCandidates.map((c) => ({
            id: c.id,
            page_index: c.page_index,
            role: c.role,
            label: c.label,
            bbox_mm: c.bbox_mm,
          })),
          remove_border: removeBorder,
          remove_hole: removeHole,
          bleed_mm: parseFloat(bleedMm) || 0,
          rotation_deg: parseInt(rotationDeg, 10) || 0,
        }),
      })
      const data: ExtractorRunResponse = await res.json()
      setResult(data)
      setPreviewItemIdx(0)
      toast.success(
        `${data.items_count} ta dizayn/pichoq alohida vektor sahifalarga ajratildi!`
      )
      window.setTimeout(() => {
        resultRef.current?.scrollIntoView({ behavior: "smooth" })
      }, 120)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Ajratishda xatolik")
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
          <Scissors className="size-5 text-muted-foreground" />
          Dizayn va Pichoq Ajratish (PDF Maket Extractor)
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Texnik pasport, brandbook yoki yig'ma PDF ichidan kerakli dizayn (birka, hangtag, etiketka) va pichoq (shtants) chizmasini avtomatik topish, alohida sahifalarga ajratish va montajga yuborish.
        </p>
      </div>

      {/* Top Row: Upload & Dimension Finder */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        {/* Upload Card */}
        <Card className="lg:col-span-5">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm">
              <UploadCloud className="size-4 text-muted-foreground" />
              1. PDF faylni yuklash
            </CardTitle>
            <CardDescription className="text-xs">
              Texnik pasport (TZ), ko'p betli katalog yoki yig'ma dizayn fayli
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div
              role="button"
              tabIndex={0}
              onClick={() => fileInputRef.current?.click()}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  fileInputRef.current?.click()
                }
              }}
              onDragOver={(e) => {
                e.preventDefault()
                setDragOver(true)
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault()
                setDragOver(false)
                const f = e.dataTransfer.files?.[0]
                if (f) void handleUploadFile(f)
              }}
              className={`flex cursor-pointer items-center gap-3 rounded-lg border border-dashed p-4 transition-colors ${
                dragOver
                  ? "border-primary bg-muted"
                  : "border-border bg-muted/30 hover:border-foreground/40 hover:bg-muted/60"
              }`}
            >
              <div className="flex size-10 shrink-0 items-center justify-center rounded-lg border bg-background text-muted-foreground">
                {inspecting ? (
                  <Loader2 className="size-5 animate-spin text-primary" />
                ) : (
                  <FileSearch className="size-5" />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium">
                  {inspecting
                    ? "PDF vektor tahlil qilinmoqda..."
                    : file
                      ? file.name
                      : "PDF faylni tanlang yoki shu yerga tashlang"}
                </div>
                <div className="text-xs text-muted-foreground">
                  {inspectData
                    ? `${inspectData.page_count} sahifa | ${candidates.length} ta obyekt aniqlandi`
                    : "Avtomatik dizayn va shtants o'lchamlarini aniqlaydi"}
                </div>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0]
                  if (f) void handleUploadFile(f)
                }}
              />
            </div>
          </CardContent>
        </Card>

        {/* Smart Size Search & Manual Box Tools */}
        <Card className="lg:col-span-7">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Ruler className="size-4 text-muted-foreground" />
              2. O'lcham bo'yicha qidirish yoki qo'lda belgilash
            </CardTitle>
            <CardDescription className="text-xs">
              Aniq eni va bo'yini (masalan: 50 × 120 mm) kiritib toping yoki sahifa ustida sichqoncha bilan belgilang
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap items-end gap-2.5">
              <div className="w-28 space-y-1">
                <Label htmlFor="extSearchW" className="text-xs">
                  Eni (mm)
                </Label>
                <Input
                  id="extSearchW"
                  type="number"
                  step="0.5"
                  placeholder="50"
                  className="h-9 tabular-nums"
                  value={searchW}
                  onChange={(e) => setSearchW(e.target.value)}
                />
              </div>
              <div className="w-28 space-y-1">
                <Label htmlFor="extSearchH" className="text-xs">
                  Bo'yi (mm)
                </Label>
                <Input
                  id="extSearchH"
                  type="number"
                  step="0.5"
                  placeholder="120"
                  className="h-9 tabular-nums"
                  value={searchH}
                  onChange={(e) => setSearchH(e.target.value)}
                />
              </div>
              <div className="w-36 space-y-1">
                <Label className="text-xs">Obyekt turi</Label>
                <Select
                  value={drawRole}
                  onValueChange={(v) =>
                    v && setDrawRole(v as "design" | "dieline")
                  }
                >
                  <SelectTrigger className="h-9 w-full">
                    <SelectValue>
                      {drawRole === "design"
                        ? "🟢 Dizayn (Maket)"
                        : "🔵 Pichoq (Shtants)"}
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="design">🟢 Dizayn (Maket)</SelectItem>
                    <SelectItem value="dieline">🔵 Pichoq (Shtants)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <Button
                variant="secondary"
                size="sm"
                className="h-9"
                disabled={!inspectData || searchingSize}
                onClick={() => void handleSearchBySize()}
              >
                {searchingSize ? (
                  <Loader2 className="animate-spin" />
                ) : (
                  <Search />
                )}
                <span>O'lchamni topish</span>
              </Button>

              <Button
                variant="outline"
                size="sm"
                className="h-9"
                disabled={!inspectData}
                onClick={handleAddManualSizedBox}
              >
                <Plus />
                <span>Shu o'lchamda ramka</span>
              </Button>

              <Button
                variant={drawMode ? "default" : "outline"}
                size="sm"
                className="h-9"
                disabled={!inspectData}
                onClick={() => setDrawMode((v) => !v)}
              >
                <Crosshair />
                <span>
                  {drawMode ? "Chizish rejimi yoqilgan" : "Sichqoncha bilan chizish"}
                </span>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Main Workspace: Pages + Interactive Page Canvas + Selected Items & Surgical Settings */}
      {inspectData && activePage && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
          {/* Left Column: Page Selector (if multi-page) & Page Info */}
          <Card className="xl:col-span-2">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">
                Sahifalar ({inspectData.page_count})
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex gap-2 overflow-x-auto pb-1 xl:max-h-[620px] xl:flex-col xl:overflow-y-auto">
                {inspectData.pages.map((p) => {
                  const isCurrent = p.page_index === activePageIndex
                  const pageCands = candidates.filter(
                    (c) => c.page_index === p.page_index
                  )
                  const selCount = pageCands.filter((c) => c.selected).length
                  return (
                    <button
                      key={p.page_index}
                      type="button"
                      onClick={() => {
                        setActivePageIndex(p.page_index)
                        const firstOnPage = pageCands[0]
                        if (firstOnPage) setFocusedId(firstOnPage.id)
                      }}
                      className={`group flex shrink-0 flex-col items-start gap-1.5 rounded-lg border p-2 text-left transition-all xl:w-full ${
                        isCurrent
                          ? "border-primary bg-primary/10 ring-1 ring-primary"
                          : "hover:bg-muted/60"
                      }`}
                    >
                      <div className="flex w-full items-center justify-between gap-2">
                        <span className="text-xs font-semibold">
                          {p.page_number}-sahifa
                        </span>
                        {selCount > 0 && (
                          <Badge variant="default" className="px-1.5 py-0 text-[10px]">
                            {selCount} tanlangan
                          </Badge>
                        )}
                      </div>
                      <div className="relative aspect-[4/3] w-28 overflow-hidden rounded border bg-white xl:w-full">
                        <img
                          src={jobFileUrl(
                            inspectData.source_job_id,
                            p.preview_file,
                            true
                          )}
                          alt={`Sahifa ${p.page_number}`}
                          className="h-full w-full object-contain"
                        />
                      </div>
                      <div className="flex flex-wrap items-center gap-1 text-[10px] text-muted-foreground tabular-nums">
                        <span>
                          {p.width_mm}×{p.height_mm} mm
                        </span>
                        {p.dimension_hints.length > 0 && (
                          <Badge
                            variant="secondary"
                            className="px-1 py-0 text-[9px]"
                          >
                            {p.dimension_hints[0][0]}×{p.dimension_hints[0][1]}
                          </Badge>
                        )}
                      </div>
                    </button>
                  )
                })}
              </div>
            </CardContent>
          </Card>

          {/* Center Column: Interactive Visual Page Canvas */}
          <Card className="xl:col-span-6">
            <CardHeader className="pb-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <CardTitle className="flex items-center gap-2 text-sm">
                    <MousePointerClick className="size-4 text-primary" />
                    <span>
                      {activePage.page_number}-sahifa ({activePage.width_mm} ×{" "}
                      {activePage.height_mm} mm)
                    </span>
                  </CardTitle>
                  <CardDescription className="text-xs">
                    {drawMode
                      ? "Sichqoncha chap tugmasini bosib ushlab kerakli dizayn ustidan to'rtburchak torting"
                      : "Ramka ustiga bosib tanlang yoki surib joyini o'zgartiring"}
                  </CardDescription>
                </div>
                <div className="flex items-center gap-1.5">
                  {activePage.dimension_hints.map((h, idx) => (
                    <Badge
                      key={idx}
                      variant="outline"
                      className="cursor-pointer gap-1 text-xs"
                      onClick={() => {
                        setSearchW(String(h[0]))
                        setSearchH(String(h[1]))
                      }}
                    >
                      <Sparkles className="size-3 text-amber-500" />
                      Matndan: {h[0]}×{h[1]} mm
                    </Badge>
                  ))}
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-center rounded-xl border bg-neutral-900/90 p-3 select-none">
                <div
                  ref={canvasOverlayRef}
                  onMouseDown={handleCanvasMouseDown}
                  onMouseMove={handleCanvasMouseMove}
                  onMouseUp={handleCanvasMouseUp}
                  className={`relative inline-block max-w-full overflow-hidden rounded shadow-lg ${
                    drawMode ? "cursor-crosshair" : "cursor-default"
                  }`}
                >
                  <img
                    src={jobFileUrl(
                      inspectData.source_job_id,
                      activePage.preview_file,
                      true
                    )}
                    alt={`Page ${activePage.page_number}`}
                    draggable={false}
                    className="block max-h-[600px] w-auto max-w-full select-none"
                  />

                  {/* Detected & Manual Candidate Overlays */}
                  {pageCandidates.map((c) => {
                    const leftPct =
                      (c.bbox_mm[0] / Math.max(1, activePage.width_mm)) * 100
                    const topPct =
                      (c.bbox_mm[1] / Math.max(1, activePage.height_mm)) * 100
                    const widthPct =
                      ((c.bbox_mm[2] - c.bbox_mm[0]) /
                        Math.max(1, activePage.width_mm)) *
                      100
                    const heightPct =
                      ((c.bbox_mm[3] - c.bbox_mm[1]) /
                        Math.max(1, activePage.height_mm)) *
                      100

                    const isDesign = c.role === "design"
                    const isFocused = c.id === focusedId

                    const borderClass = c.selected
                      ? isDesign
                        ? "border-2 border-emerald-500 bg-emerald-500/15 shadow-[0_0_0_2px_rgba(16,185,129,0.25)]"
                        : "border-2 border-dashed border-sky-500 bg-sky-500/15 shadow-[0_0_0_2px_rgba(14,165,233,0.25)]"
                      : "border border-dashed border-neutral-400/80 bg-neutral-500/10 opacity-70 hover:opacity-100"

                    return (
                      <div
                        key={c.id}
                        style={{
                          left: `${leftPct}%`,
                          top: `${topPct}%`,
                          width: `${widthPct}%`,
                          height: `${heightPct}%`,
                        }}
                        onMouseDown={(e) => {
                          if (drawMode) return
                          e.stopPropagation()
                          setFocusedId(c.id)
                          setMovingBox({
                            id: c.id,
                            startClientX: e.clientX,
                            startClientY: e.clientY,
                            origBbox: [...c.bbox_mm] as [
                              number,
                              number,
                              number,
                              number,
                            ],
                          })
                        }}
                        onClick={(e) => {
                          if (drawMode) return
                          e.stopPropagation()
                          setFocusedId(c.id)
                        }}
                        className={`group absolute transition-shadow ${borderClass} ${
                          isFocused ? "ring-2 ring-amber-400" : ""
                        } ${drawMode ? "pointer-events-none" : "cursor-move"}`}
                      >
                        {/* Top Badge Bar */}
                        <div className="absolute -top-6 left-0 z-10 flex items-center gap-1 whitespace-nowrap">
                          <button
                            type="button"
                            onMouseDown={(e) => e.stopPropagation()}
                            onClick={(e) => {
                              e.stopPropagation()
                              setCandidates((prev) =>
                                prev.map((item) =>
                                  item.id === c.id
                                    ? { ...item, selected: !item.selected }
                                    : item
                                )
                              )
                            }}
                            className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-semibold text-white shadow ${
                              c.selected
                                ? isDesign
                                  ? "bg-emerald-600 hover:bg-emerald-700"
                                  : "bg-sky-600 hover:bg-sky-700"
                                : "bg-neutral-700 hover:bg-neutral-600"
                            }`}
                          >
                            <span className="flex size-3 items-center justify-center rounded-xs border border-white/60">
                              {c.selected && <Check className="size-2.5" />}
                            </span>
                            <span>
                              {isDesign ? "Dizayn" : "Pichoq"}:{" "}
                              {c.width_mm}×{c.height_mm} mm
                            </span>
                          </button>
                        </div>

                        {/* Detected Punch Hole Indicator */}
                        {c.holes.map((h, hIdx) => {
                          const hLeftPct =
                            (h.center_x_mm / Math.max(1, c.width_mm)) * 100
                          const hTopPct =
                            (h.center_y_mm / Math.max(1, c.height_mm)) * 100
                          return (
                            <div
                              key={hIdx}
                              title={`Aniqlangan teshik (d=${h.diameter_mm} mm)`}
                              style={{
                                left: `${hLeftPct}%`,
                                top: `${hTopPct}%`,
                              }}
                              className="pointer-events-none absolute -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-amber-400 bg-amber-400/30 p-1"
                            />
                          )
                        })}
                      </div>
                    )
                  })}

                  {/* Active Rubberband Box while Drawing */}
                  {drawMode && dragStartMm && dragCurrMm && (
                    <div
                      style={{
                        left: `${
                          (Math.min(dragStartMm[0], dragCurrMm[0]) /
                            Math.max(1, activePage.width_mm)) *
                          100
                        }%`,
                        top: `${
                          (Math.min(dragStartMm[1], dragCurrMm[1]) /
                            Math.max(1, activePage.height_mm)) *
                          100
                        }%`,
                        width: `${
                          (Math.abs(dragCurrMm[0] - dragStartMm[0]) /
                            Math.max(1, activePage.width_mm)) *
                          100
                        }%`,
                        height: `${
                          (Math.abs(dragCurrMm[1] - dragStartMm[1]) /
                            Math.max(1, activePage.height_mm)) *
                          100
                        }%`,
                      }}
                      className="pointer-events-none absolute border-2 border-amber-400 bg-amber-400/20"
                    >
                      <span className="absolute -top-6 left-0 rounded bg-amber-500 px-1.5 py-0.5 text-[10px] font-semibold text-black tabular-nums">
                        {round2(Math.abs(dragCurrMm[0] - dragStartMm[0]))} ×{" "}
                        {round2(Math.abs(dragCurrMm[1] - dragStartMm[1]))} mm
                      </span>
                    </div>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Right Column: Candidate List, Dimension Fine-Tuning & Vector Surgical Controls */}
          <Card className="xl:col-span-4">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm">
                  3. Topilgan obyektlar ({selectedCandidates.length}/
                  {candidates.length})
                </CardTitle>
                <div className="flex gap-1">
                  <Button
                    variant="ghost"
                    size="xs"
                    onClick={() =>
                      setCandidates((prev) =>
                        prev.map((c) => ({ ...c, selected: true }))
                      )
                    }
                  >
                    Barchasi
                  </Button>
                  <Button
                    variant="ghost"
                    size="xs"
                    onClick={() =>
                      setCandidates((prev) =>
                        prev.map((c) => ({
                          ...c,
                          selected: c.role === "design",
                        }))
                      )
                    }
                  >
                    Faqat dizayn
                  </Button>
                </div>
              </div>
              <CardDescription className="text-xs">
                Ajratib olinadigan dizayn va shtantslarni belgilang
              </CardDescription>
            </CardHeader>

            <CardContent className="space-y-4">
              {/* Candidate List */}
              <div className="max-h-60 space-y-2 overflow-y-auto pr-1">
                {candidates.length === 0 ? (
                  <div className="rounded-lg border border-dashed p-4 text-center text-xs text-muted-foreground">
                    Obyektlar topilmadi. Yuqoridan o'lcham kiritib qo'shing yoki sichqoncha bilan chizing.
                  </div>
                ) : (
                  candidates.map((c) => {
                    const isDesign = c.role === "design"
                    const isFocused = c.id === focusedId
                    return (
                      <div
                        key={c.id}
                        onClick={() => {
                          setActivePageIndex(c.page_index)
                          setFocusedId(c.id)
                        }}
                        className={`flex cursor-pointer items-center justify-between gap-2 rounded-lg border p-2.5 text-xs transition-colors ${
                          isFocused
                            ? "border-primary bg-primary/5"
                            : "hover:bg-muted/50"
                        }`}
                      >
                        <div className="flex min-w-0 items-center gap-2">
                          <input
                            type="checkbox"
                            checked={c.selected}
                            onChange={(e) => {
                              e.stopPropagation()
                              setCandidates((prev) =>
                                prev.map((item) =>
                                  item.id === c.id
                                    ? { ...item, selected: e.target.checked }
                                    : item
                                )
                              )
                            }}
                            className="size-4 accent-emerald-600"
                          />
                          {c.fill_color_hex && (
                            <span
                              style={{ backgroundColor: c.fill_color_hex }}
                              className="size-3.5 shrink-0 rounded-full border"
                              title={`Fon rangi: ${c.fill_color_hex}`}
                            />
                          )}
                          <div className="min-w-0">
                            <div className="flex items-center gap-1.5 font-medium">
                              <span className="truncate">{c.label}</span>
                              <Badge
                                variant="outline"
                                className="px-1 py-0 text-[10px]"
                              >
                                {c.page_index + 1}-bet
                              </Badge>
                            </div>
                            <div className="flex items-center gap-2 text-[11px] text-muted-foreground tabular-nums">
                              <span>
                                {c.width_mm} × {c.height_mm} mm
                              </span>
                              {c.has_hole && (
                                <span className="inline-flex items-center gap-0.5 text-amber-600 dark:text-amber-400">
                                  <CircleDot className="size-3" />
                                  teshik ({c.holes[0]?.diameter_mm}mm)
                                </span>
                              )}
                            </div>
                          </div>
                        </div>

                        <div className="flex shrink-0 items-center gap-1">
                          <Badge
                            variant={isDesign ? "default" : "secondary"}
                            onClick={(e) => {
                              e.stopPropagation()
                              toggleCandidateRole(
                                c.id,
                                isDesign ? "dieline" : "design"
                              )
                            }}
                            title="Rolni almashtirish uchun bosing (Dizayn / Pichoq)"
                            className="cursor-pointer text-[10px]"
                          >
                            {isDesign ? "Dizayn" : "Pichoq"}
                          </Badge>
                          <Button
                            variant="ghost"
                            size="icon-xs"
                            onClick={(e) => {
                              e.stopPropagation()
                              removeCandidate(c.id)
                            }}
                            title="O'chirish"
                          >
                            <Trash2 className="size-3.5 text-muted-foreground hover:text-destructive" />
                          </Button>
                        </div>
                      </div>
                    )
                  })
                )}
              </div>

              {/* Fine-tune focused candidate coordinates/dimensions */}
              {focusedCandidate && (
                <div className="rounded-lg border bg-muted/30 p-3 space-y-2.5">
                  <div className="flex items-center justify-between text-xs font-medium">
                    <span>Tanlangan ramka o'lchamini sozlash:</span>
                    <Badge variant="outline" className="text-[10px]">
                      {focusedCandidate.label}
                    </Badge>
                  </div>
                  <div className="grid grid-cols-4 gap-2">
                    <div className="space-y-1">
                      <Label className="text-[10px] text-muted-foreground">
                        Eni (mm)
                      </Label>
                      <Input
                        type="number"
                        step="0.5"
                        className="h-8 text-xs tabular-nums"
                        value={focusedCandidate.width_mm}
                        onChange={(e) =>
                          updateCandidateDimension(
                            focusedCandidate.id,
                            "width",
                            e.target.value
                          )
                        }
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-[10px] text-muted-foreground">
                        Bo'yi (mm)
                      </Label>
                      <Input
                        type="number"
                        step="0.5"
                        className="h-8 text-xs tabular-nums"
                        value={focusedCandidate.height_mm}
                        onChange={(e) =>
                          updateCandidateDimension(
                            focusedCandidate.id,
                            "height",
                            e.target.value
                          )
                        }
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-[10px] text-muted-foreground">
                        X (mm)
                      </Label>
                      <Input
                        type="number"
                        step="0.5"
                        className="h-8 text-xs tabular-nums"
                        value={focusedCandidate.bbox_mm[0]}
                        onChange={(e) =>
                          updateCandidateDimension(
                            focusedCandidate.id,
                            "x0",
                            e.target.value
                          )
                        }
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-[10px] text-muted-foreground">
                        Y (mm)
                      </Label>
                      <Input
                        type="number"
                        step="0.5"
                        className="h-8 text-xs tabular-nums"
                        value={focusedCandidate.bbox_mm[1]}
                        onChange={(e) =>
                          updateCandidateDimension(
                            focusedCandidate.id,
                            "y0",
                            e.target.value
                          )
                        }
                      />
                    </div>
                  </div>
                </div>
              )}

              <Separator />

              {/* Surgical Vector Controls */}
              <div className="space-y-3">
                <div className="text-xs font-semibold">
                  Vektor tozalash va Bleed sozlamalari
                </div>

                <div className="divide-y rounded-lg border px-3">
                  <div className="flex items-center justify-between gap-3 py-2.5">
                    <div className="space-y-0.5">
                      <Label htmlFor="extRemoveBorder" className="text-xs">
                        Dizayn tashqi ramkasini o'chirish
                      </Label>
                      <p className="text-[11px] text-muted-foreground">
                        Kesim kontur chizig'ini olib tashlab toza fon qoldirish
                      </p>
                    </div>
                    <Switch
                      id="extRemoveBorder"
                      checked={removeBorder}
                      onCheckedChange={setRemoveBorder}
                    />
                  </div>

                  <div className="flex items-center justify-between gap-3 py-2.5">
                    <div className="space-y-0.5">
                      <Label htmlFor="extRemoveHole" className="text-xs">
                        Birka teshigini (perforatsiyani) o'chirish
                      </Label>
                      <p className="text-[11px] text-muted-foreground">
                        Bosmada teshik o'rni ham fon rangida bo'yalib chiqishi uchun
                      </p>
                    </div>
                    <Switch
                      id="extRemoveHole"
                      checked={removeHole}
                      onCheckedChange={setRemoveHole}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="extBleedMm" className="text-xs">
                      Fon Bleed / Vilet qo'shish
                    </Label>
                    <Select
                      value={bleedMm}
                      onValueChange={(v) => v && setBleedMm(v)}
                    >
                      <SelectTrigger id="extBleedMm" className="h-9 w-full">
                        <SelectValue>{bleedMm} mm</SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="0">0 mm (Asl o'lchamda)</SelectItem>
                        <SelectItem value="1.5">+1.5 mm (Har tomondan)</SelectItem>
                        <SelectItem value="2">+2.0 mm (Har tomondan)</SelectItem>
                        <SelectItem value="3">+3.0 mm (Har tomondan)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="extRotDeg" className="text-xs">
                      Aylantirish
                    </Label>
                    <Select
                      value={rotationDeg}
                      onValueChange={(v) => v && setRotationDeg(v)}
                    >
                      <SelectTrigger id="extRotDeg" className="h-9 w-full">
                        <SelectValue>{rotationDeg}°</SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="0">0° (Asl holatda)</SelectItem>
                        <SelectItem value="90">90°</SelectItem>
                        <SelectItem value="180">180°</SelectItem>
                        <SelectItem value="270">270°</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </div>

              <Button
                size="lg"
                className="w-full"
                disabled={running || selectedCandidates.length === 0}
                onClick={() => void handleRunExtraction()}
              >
                {running ? <Loader2 className="animate-spin" /> : <Scissors />}
                <span>
                  {running
                    ? "Vektor ajratilmoqda..."
                    : `Tanlanganlarni Ajratib Olish (${selectedCandidates.length} ta)`}
                </span>
              </Button>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Step 4: Extraction Result & 1-Click Handoff */}
      {result && (
        <Card ref={resultRef}>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckCircle2 className="size-5 text-emerald-600" />
              Ajratib Olingan Vektor Dizaynlar Tayyor ({result.items_count} ta)
            </CardTitle>
            <CardDescription>
              Har bir dizayn va pichoq tashqi shovqinlardan tozalanib, o'zining aniq o'lchamidagi alohida sahifaga joylandi.
            </CardDescription>
            <CardAction className="flex flex-wrap items-center gap-2">
              <Button
                variant="default"
                size="sm"
                onClick={() => {
                  const firstDesign =
                    result.items.find((i) => i.role === "design") ??
                    result.items[0]
                  onSendToPrintImp({
                    job_id: result.job_id,
                    front_filenames:
                      result.design_files.length > 0
                        ? result.design_files
                        : [result.primary_design_file],
                    dieline_filename: result.dieline_files[0] ?? null,
                    trim_w_mm: firstDesign ? firstDesign.width_mm : null,
                    trim_h_mm: firstDesign ? firstDesign.height_mm : null,
                    source_label: `${result.source_filename} (${result.design_files.length || 1} ta dizayn${result.dieline_files.length ? " + Pichoq" : ""})`,
                  })
                }}
              >
                <LayoutGrid />
                <span>Varaq Montajiga Yuborish →</span>
              </Button>

              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  onSendToLabelImp({
                    job_id: result.job_id,
                    filename: result.primary_design_file,
                    total_labels: result.design_files.length || result.items_count,
                    source_label: `Dizayn Ajratish (${result.source_filename})`,
                  })
                }}
              >
                <Cylinder />
                <span>Val Montajiga Yuborish →</span>
              </Button>

              {result.zip_file && (
                <Button
                  variant="outline"
                  size="sm"
                  nativeButton={false}
                  render={
                    <a
                      href={jobFileUrl(result.job_id, result.zip_file)}
                      download={result.zip_file}
                    />
                  }
                >
                  <Archive />
                  <span>ZIP yuklab olish</span>
                </Button>
              )}
            </CardAction>
          </CardHeader>

          <CardContent className="space-y-5">
            <CorelExportBar
              jobId={result.job_id}
              version={corel.version}
              onVersionChange={corel.setVersion}
              askOnRun={corel.askOnRun}
              onAskOnRunChange={corel.setAskOnRun}
            />

            {/* Individual & Combined File Download Buttons */}
            <div className="flex flex-wrap gap-2">
              {result.output_files.map((f) => (
                <div
                  key={f.filename}
                  className="inline-flex items-center gap-1"
                >
                  <Button
                    variant={
                      f.role?.startsWith("combined") ? "default" : "outline"
                    }
                    size="sm"
                    nativeButton={false}
                    render={
                      <a
                        href={jobFileUrl(result.job_id, f.filename)}
                        download={f.filename}
                      />
                    }
                  >
                    <Download />
                    <span>
                      {f.filename} ({f.size_kb} KB)
                    </span>
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    title={`${f.filename} faylini CorelDRAW (.cdr v${corel.version}) qilib ochish`}
                    nativeButton={false}
                    render={
                      <a
                        href={jobCdrBundleUrl(result.job_id, {
                          filename: f.filename,
                          version: corel.version,
                          ask: corel.askOnRun,
                        })}
                        download
                      />
                    }
                  >
                    <span>.CDR (v{corel.version})</span>
                  </Button>
                </div>
              ))}
            </div>

            {/* Visual Cards & Live Vector PDF Preview */}
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:col-span-5">
                {result.items.map((item, idx) => {
                  const isSelected = idx === previewItemIdx
                  return (
                    <div
                      key={item.filename}
                      onClick={() => setPreviewItemIdx(idx)}
                      className={`flex cursor-pointer flex-col justify-between rounded-lg border p-2.5 transition-all ${
                        isSelected
                          ? "border-primary bg-primary/5 ring-2 ring-primary"
                          : "hover:bg-muted/40"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-1 mb-2">
                        <Badge
                          variant={
                            item.role === "design" ? "default" : "secondary"
                          }
                          className="text-[10px]"
                        >
                          {item.role === "design" ? "Dizayn" : "Pichoq"}
                        </Badge>
                        <span className="text-[10px] font-medium tabular-nums text-muted-foreground">
                          {item.width_mm}×{item.height_mm} mm
                        </span>
                      </div>

                      <div className="flex aspect-[3/4] items-center justify-center overflow-hidden rounded border bg-neutral-100 p-2 dark:bg-neutral-900">
                        <img
                          src={jobFileUrl(
                            result.job_id,
                            item.thumb_file,
                            true
                          )}
                          alt={item.label}
                          className="max-h-full max-w-full object-contain shadow-xs"
                        />
                      </div>

                      <div className="mt-2 truncate text-[11px] font-medium">
                        {item.filename}
                      </div>
                    </div>
                  )
                })}
              </div>

              <div className="lg:col-span-7">
                {result.items[previewItemIdx] && (
                  <PdfPreview
                    src={jobFileUrl(
                      result.job_id,
                      result.items[previewItemIdx].filename,
                      true
                    )}
                    downloadUrl={jobFileUrl(
                      result.job_id,
                      result.items[previewItemIdx].filename
                    )}
                    downloadFilename={result.items[previewItemIdx].filename}
                    title={`Ajratilgan Vektor PDF: ${result.items[previewItemIdx].filename} (${result.items[previewItemIdx].width_mm} × ${result.items[previewItemIdx].height_mm} mm)`}
                  />
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
