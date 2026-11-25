import { useCallback, useEffect, useRef, useState } from "react"
import {
  AlertTriangle,
  Archive,
  CheckCircle2,
  Cylinder,
  Download,
  Eye,
  FileUp,
  Link2,
  Loader2,
  Play,
  RefreshCw,
  RotateCw,
  SlidersHorizontal,
  UploadCloud,
  Wrench,
  X,
} from "lucide-react"
import { toast } from "sonner"

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardAction,
  CardContent,
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
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { CorelExportBar, useCorelSettings } from "@/components/CorelExportBar"
import { PdfPreview } from "@/components/PdfPreview"
import {
  apiFetch,
  jobCdrBundleUrl,
  jobFileUrl,
  type LabelHandoff,
  type LabelInspectDesign,
  type LabelInspectResponse,
  type LabelRunResponse,
  type LabelRunStatusResponse,
} from "@/lib/api"

interface LabelImpTabProps {
  handoff: LabelHandoff | null
  onClearHandoff: () => void
}

const COLOR_MODE_LABELS: Record<string, string> = {
  side_by_side: "Yonma-yon ustunlarda (1 ta sahifada)",
  separate_files: "Alohida PDF fayllarda",
}

const ROTATION_MODE_LABELS: Record<string, string> = {
  auto: "Avto (kichik tomon = eni)",
  "0": "0° (Asl holatda)",
  "90": "90° (Soat yo'nalishida)",
  "180": "180° (Teskari)",
  "270": "270° (Soatga qarshi)",
}

export function LabelImpTab({ handoff, onClearHandoff }: LabelImpTabProps) {
  const corel = useCorelSettings()
  const [files, setFiles] = useState<File[]>([])
  const [dragOver, setDragOver] = useState(false)
  const [inspected, setInspected] = useState<LabelInspectDesign[]>([])
  const [selectedDesignIndex, setSelectedDesignIndex] = useState<number>(0)

  const [customGear, setCustomGear] = useState("")
  const [customCopies, setCustomCopies] = useState("")
  const [rotationMode, setRotationMode] = useState("auto")
  const [colorMode, setColorMode] = useState("side_by_side")
  const [combineGear, setCombineGear] = useState(true)
  const [separateByFile, setSeparateByFile] = useState(false)
  const [separateColors, setSeparateColors] = useState(true)
  const [removeBorder, setRemoveBorder] = useState(true)
  const [regmark, setRegmark] = useState(true)

  const [gapMm, setGapMm] = useState("5.0")
  const [maxWidthMm, setMaxWidthMm] = useState("0")
  const [regStroke, setRegStroke] = useState("0.2")
  const [regTick, setRegTick] = useState("0.7")
  const [regWidthMm, setRegWidthMm] = useState("")
  const [exportSvg, setExportSvg] = useState(false)
  const [exportEps, setExportEps] = useState(false)

  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [previewPages, setPreviewPages] = useState<number>(1)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)

  const [running, setRunning] = useState(false)
  const [runProgress, setRunProgress] = useState<{
    current: number
    total: number
    percent: number
    message: string
    elapsedSec: number
  } | null>(null)
  const [result, setResult] = useState<LabelRunResponse | null>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const resultCardRef = useRef<HTMLDivElement>(null)
  const previewUrlRef = useRef<string | null>(null)
  const previewAbortRef = useRef<AbortController | null>(null)
  const runSeqRef = useRef(0)

  const hasSource = Boolean(handoff || files.length > 0)

  const clearPreview = useCallback(() => {
    previewAbortRef.current?.abort()
    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current)
      previewUrlRef.current = null
    }
    setPreviewUrl(null)
    setPreviewPages(1)
    setPreviewError(null)
  }, [])

  const inspectSource = useCallback(async () => {
    if (!handoff && files.length === 0) {
      setInspected([])
      return
    }
    const fd = new FormData()
    if (handoff) {
      fd.append("from_job_id", handoff.job_id)
      fd.append("from_filename", handoff.filename)
    }
    files.forEach((f) => fd.append("files", f))
    fd.append("rotation_mode", rotationMode)
    if (customGear.trim()) fd.append("custom_gear", customGear.trim())
    if (customCopies.trim()) fd.append("custom_copies", customCopies.trim())

    try {
      const res = await apiFetch("/api/label-imp/inspect", {
        method: "POST",
        body: fd,
      })
      const data: LabelInspectResponse = await res.json()
      setInspected(data.designs)
      setSelectedDesignIndex((prev) =>
        data.designs.length === 0 ? 0 : Math.min(prev, data.designs.length - 1)
      )
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Tekshirishda xatolik")
    }
  }, [handoff, files, rotationMode, customGear, customCopies])

  const refreshLivePreview = useCallback(async () => {
    if (!handoff && files.length === 0) {
      clearPreview()
      return
    }

    previewAbortRef.current?.abort()
    const controller = new AbortController()
    previewAbortRef.current = controller

    setPreviewLoading(true)
    setPreviewError(null)

    const fd = new FormData()
    if (handoff) {
      fd.append("from_job_id", handoff.job_id)
      fd.append("from_filename", handoff.filename)
    }
    files.forEach((f) => fd.append("files", f))
    if (customGear.trim()) fd.append("custom_gear", customGear.trim())
    if (customCopies.trim()) fd.append("custom_copies", customCopies.trim())
    fd.append("rotation_mode", rotationMode)
    fd.append("combine_same_gear", String(combineGear))
    fd.append("separate_by_file", String(separateByFile))
    fd.append("separate_colors", String(separateColors))
    fd.append("color_output_mode", colorMode)
    fd.append("remove_outer_border", String(removeBorder))
    fd.append("regmark_enabled", String(regmark))
    fd.append("regmark_stroke_mm", regStroke)
    fd.append("regmark_tick_mm", regTick)
    if (regWidthMm.trim()) {
      fd.append("regmark_custom_width_mm", regWidthMm.trim())
    }
    fd.append("column_gap_mm", gapMm)
    fd.append("max_cylinder_width_mm", maxWidthMm)
    fd.append("design_index", String(selectedDesignIndex))

    try {
      const res = await apiFetch("/api/label-imp/preview", {
        method: "POST",
        body: fd,
        signal: controller.signal,
      })
      const pagesHeader = parseInt(res.headers.get("X-Preview-Pages") || "1", 10)
      const blob = await res.blob()
      if (controller.signal.aborted) return

      const nextUrl = URL.createObjectURL(blob)
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current)
      previewUrlRef.current = nextUrl
      setPreviewUrl(nextUrl)
      setPreviewPages(Number.isFinite(pagesHeader) && pagesHeader > 0 ? pagesHeader : 1)
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return
      setPreviewError(
        err instanceof Error ? err.message : "Ko'rinishni yaratishda xatolik"
      )
    } finally {
      if (!controller.signal.aborted) {
        setPreviewLoading(false)
      }
    }
  }, [
    handoff,
    files,
    customGear,
    customCopies,
    rotationMode,
    combineGear,
    separateByFile,
    separateColors,
    colorMode,
    removeBorder,
    regmark,
    regStroke,
    regTick,
    regWidthMm,
    gapMm,
    maxWidthMm,
    selectedDesignIndex,
    clearPreview,
  ])

  useEffect(() => {
    if (handoff) {
      setFiles([])
      setSelectedDesignIndex(0)
    }
  }, [handoff])

  useEffect(() => {
    if (!hasSource) {
      setInspected([])
      setSelectedDesignIndex(0)
      return
    }
    const timer = window.setTimeout(() => {
      void inspectSource()
    }, 220)
    return () => window.clearTimeout(timer)
  }, [hasSource, inspectSource])

  useEffect(() => {
    if (!hasSource) {
      clearPreview()
      return
    }
    const timer = window.setTimeout(() => {
      void refreshLivePreview()
    }, 450)
    return () => window.clearTimeout(timer)
  }, [hasSource, refreshLivePreview, clearPreview])

  useEffect(() => {
    return () => {
      runSeqRef.current += 1
      previewAbortRef.current?.abort()
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current)
    }
  }, [])

  function handleSelectFiles(incoming: File[]) {
    const pdfs = incoming.filter((f) => f.name.toLowerCase().endsWith(".pdf"))
    if (!pdfs.length) return
    setFiles(pdfs)
    setSelectedDesignIndex(0)
  }

  function handleQuickRotate90() {
    const currentDeg =
      rotationMode === "auto"
        ? ((inspected[selectedDesignIndex] ?? inspected[0])?.rotation_deg ?? 0)
        : parseInt(rotationMode, 10) || 0
    const nextDeg = (currentDeg + 90) % 360
    setRotationMode(String(nextDeg))
  }

  async function handleRun() {
    const seq = ++runSeqRef.current
    setRunning(true)
    setRunProgress({
      current: 0,
      total: 1,
      percent: 0,
      message: "Fayllar serverga yuborilmoqda...",
      elapsedSec: 0,
    })
    try {
      const fd = new FormData()
      if (handoff) {
        fd.append("from_job_id", handoff.job_id)
        fd.append("from_filename", handoff.filename)
      }
      files.forEach((f) => fd.append("files", f))
      if (customGear.trim()) fd.append("custom_gear", customGear.trim())
      if (customCopies.trim()) fd.append("custom_copies", customCopies.trim())
      fd.append("rotation_mode", rotationMode)
      fd.append("combine_same_gear", String(combineGear))
      fd.append("separate_by_file", String(separateByFile))
      fd.append("separate_colors", String(separateColors))
      fd.append("color_output_mode", colorMode)
      fd.append("remove_outer_border", String(removeBorder))
      fd.append("regmark_enabled", String(regmark))
      fd.append("regmark_stroke_mm", regStroke)
      fd.append("regmark_tick_mm", regTick)
      if (regWidthMm.trim()) {
        fd.append("regmark_custom_width_mm", regWidthMm.trim())
      }
      fd.append("column_gap_mm", gapMm)
      fd.append("max_cylinder_width_mm", maxWidthMm)
      fd.append("export_svg", String(exportSvg))
      fd.append("export_eps", String(exportEps))

      const startRes = await apiFetch("/api/label-imp/run/start", {
        method: "POST",
        body: fd,
      })
      const { run_id } = (await startRes.json()) as { run_id: string }

      let pollErrors = 0
      while (runSeqRef.current === seq) {
        await new Promise((r) => window.setTimeout(r, 350))
        if (runSeqRef.current !== seq) return

        let statusData: LabelRunStatusResponse
        try {
          const pollRes = await apiFetch(
            `/api/label-imp/runs/${encodeURIComponent(run_id)}`
          )
          statusData = (await pollRes.json()) as LabelRunStatusResponse
          pollErrors = 0
        } catch (pollErr) {
          pollErrors += 1
          if (pollErrors >= 5) throw pollErr
          continue
        }

        if (runSeqRef.current !== seq) return

        setRunProgress({
          current: statusData.current,
          total: statusData.total,
          percent: statusData.percent,
          message: statusData.message,
          elapsedSec: statusData.elapsed_sec,
        })

        if (statusData.status === "done" && statusData.result) {
          setResult(statusData.result)
          toast.success("Val montaji muvaffaqiyatli yakunlandi")
          window.setTimeout(() => {
            resultCardRef.current?.scrollIntoView({ behavior: "smooth" })
          }, 100)
          return
        }
        if (statusData.status === "error") {
          throw new Error(statusData.error || statusData.message || "Montaj xatosi")
        }
      }
    } catch (err) {
      if (runSeqRef.current === seq) {
        toast.error(err instanceof Error ? err.message : "Montaj xatosi")
      }
    } finally {
      if (runSeqRef.current === seq) {
        setRunning(false)
        setRunProgress(null)
      }
    }
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
          <Cylinder className="size-5 text-muted-foreground" />
          Stiker Val Montaji
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Neylon/Satin stikerlarni yoki Sela A4 varag'ini avtomatik ajratish, rangga bo'lish va mos Valga joylashtirish.
        </p>
      </div>

      {/* Handoff Banner */}
      {handoff && (
        <Alert>
          <Link2 />
          <AlertTitle>
            {handoff.source_label || "Sela Generator natijasi"} ulandi
          </AlertTitle>
          <AlertDescription className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <span>
              {handoff.filename} ({handoff.total_labels} ta dizayn/stiker)
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                onClearHandoff()
                setInspected([])
              }}
            >
              <X />
              <span>Bekor qilish</span>
            </Button>
          </AlertDescription>
        </Alert>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.25fr)]">
        {/* Upload Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileUp className="size-4 text-muted-foreground" />
              Stiker PDF fayl(lar)ini yuklash
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
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
                handleSelectFiles(Array.from(e.dataTransfer.files))
              }}
              className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-8 text-center transition-colors ${
                dragOver
                  ? "border-primary bg-muted"
                  : "border-border bg-muted/30 hover:border-foreground/40 hover:bg-muted/60"
              }`}
            >
              <div className="flex size-10 items-center justify-center rounded-lg border bg-background text-muted-foreground">
                <UploadCloud className="size-5" />
              </div>
              <div className="text-sm font-medium">
                {files.length > 0
                  ? `Tanlandi (${files.length} ta): ${files.map((f) => f.name).join(", ")}`
                  : handoff
                    ? "Qo'shimcha PDF fayl qo'shish (ixtiyoriy)"
                    : "PDF fayllarni shu yerga tashlang yoki tanlang"}
              </div>
              <div className="text-xs text-muted-foreground">
                Bitta stiker, ko'p betli PDF yoki 26 talik Sela A4 varag'i
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf"
                multiple
                className="hidden"
                onChange={(e) =>
                  handleSelectFiles(Array.from(e.target.files ?? []))
                }
              />
            </div>

            {inspected.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-2 text-xs font-medium text-muted-foreground">
                  <span>
                    Aniqlangan stikerlar ({inspected.length} ta) — oldindan ko'rish uchun ustiga bosing
                  </span>
                </div>
                <div className="max-h-[420px] overflow-y-auto rounded-lg border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Dizayn</TableHead>
                        <TableHead>Eni × Bo'yi</TableHead>
                        <TableHead>Avto Val</TableHead>
                        <TableHead>Nusxa</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {inspected.map((d, i) => {
                        const isSelected = i === selectedDesignIndex
                        return (
                          <TableRow
                            key={`${d.display_name}-${i}`}
                            data-state={isSelected ? "selected" : undefined}
                            onClick={() => setSelectedDesignIndex(i)}
                            className={`cursor-pointer transition-colors ${
                              isSelected
                                ? "bg-primary/10 font-medium hover:bg-primary/15"
                                : "hover:bg-muted/60"
                            }`}
                          >
                            <TableCell>
                              <span className="inline-flex items-center gap-1.5">
                                {isSelected && (
                                  <Eye className="size-3.5 shrink-0 text-primary" />
                                )}
                                <span className="truncate">{d.display_name}</span>
                              </span>
                            </TableCell>
                            <TableCell className="tabular-nums">
                              <span className="inline-flex items-center gap-1.5">
                                <span>
                                  {d.width_mm} × {d.length_mm} mm
                                </span>
                                {d.rotation_deg ? (
                                  <Badge
                                    variant="outline"
                                    className="px-1.5 py-0 text-[10px] font-normal text-muted-foreground"
                                  >
                                    {d.rotation_deg}°
                                  </Badge>
                                ) : null}
                              </span>
                            </TableCell>
                            <TableCell>
                              <Badge variant="secondary" className="tabular-nums">
                                {d.recommended_gear ?? "-"} val
                              </Badge>
                            </TableCell>
                            <TableCell className="tabular-nums">
                              {d.recommended_copies ?? "-"}x
                            </TableCell>
                          </TableRow>
                        )
                      })}
                    </TableBody>
                  </Table>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Settings Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <SlidersHorizontal className="size-4 text-muted-foreground" />
              Val va rang sozlamalari
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="labelCustomGear">Val (bo'sh = Avto)</Label>
                <Input
                  id="labelCustomGear"
                  type="number"
                  placeholder="Avto (masalan: 59)"
                  className="tabular-nums"
                  value={customGear}
                  onChange={(e) => setCustomGear(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="labelCustomCopies">
                  Nusxa soni N (bo'sh = Avto)
                </Label>
                <Input
                  id="labelCustomCopies"
                  type="number"
                  placeholder="Avto (masalan: 2)"
                  className="tabular-nums"
                  value={customCopies}
                  onChange={(e) => setCustomCopies(e.target.value)}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label>Etiketka yo'nalishi (Aylantirish)</Label>
              <div className="flex items-center gap-2">
                <Select
                  value={rotationMode}
                  onValueChange={(v) => v && setRotationMode(v)}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue>{ROTATION_MODE_LABELS[rotationMode]}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">
                      {ROTATION_MODE_LABELS.auto}
                    </SelectItem>
                    <SelectItem value="0">{ROTATION_MODE_LABELS["0"]}</SelectItem>
                    <SelectItem value="90">
                      {ROTATION_MODE_LABELS["90"]}
                    </SelectItem>
                    <SelectItem value="180">
                      {ROTATION_MODE_LABELS["180"]}
                    </SelectItem>
                    <SelectItem value="270">
                      {ROTATION_MODE_LABELS["270"]}
                    </SelectItem>
                  </SelectContent>
                </Select>
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  title="90° aylantirish"
                  onClick={handleQuickRotate90}
                >
                  <RotateCw className="size-4" />
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Avto rejimda kichik tomon eni, katta tomon bo'yi (val aylanasi) sifatida olinadi.
              </p>
            </div>

            <div className="space-y-2">
              <Label>Ko'p rangli stiker rejimi</Label>
              <Select
                value={colorMode}
                onValueChange={(v) => v && setColorMode(v)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue>{COLOR_MODE_LABELS[colorMode]}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="side_by_side">
                    {COLOR_MODE_LABELS.side_by_side}
                  </SelectItem>
                  <SelectItem value="separate_files">
                    {COLOR_MODE_LABELS.separate_files}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="divide-y rounded-lg border px-3">
              <div className="flex items-center justify-between gap-4 py-3">
                <div className="space-y-0.5">
                  <Label htmlFor="labelCombineGear">
                    Bir xil valni birlashtirish
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    Bir xil valga tushadiganlarni yonma-yon terish
                  </p>
                </div>
                <Switch
                  id="labelCombineGear"
                  checked={combineGear}
                  onCheckedChange={setCombineGear}
                />
              </div>

              <div className="flex items-center justify-between gap-4 py-3">
                <div className="space-y-0.5">
                  <Label
                    htmlFor="labelSeparateByFile"
                    className={!combineGear ? "text-muted-foreground" : undefined}
                  >
                    Har bir faylni alohida montaj qilish
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    Har bir yuklangan PDF fayl o'z nomi bilan alohida montaj qilinadi
                  </p>
                </div>
                <Switch
                  id="labelSeparateByFile"
                  checked={separateByFile}
                  disabled={!combineGear}
                  onCheckedChange={setSeparateByFile}
                />
              </div>

              <div className="flex items-center justify-between gap-4 py-3">
                <div className="space-y-0.5">
                  <Label htmlFor="labelSeparateColors">
                    Ranglarga ajratish
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    Spot/CMYK qatlamlarni 100% qora klishega ajratish
                  </p>
                </div>
                <Switch
                  id="labelSeparateColors"
                  checked={separateColors}
                  onCheckedChange={setSeparateColors}
                />
              </div>

              <div className="flex items-center justify-between gap-4 py-3">
                <div className="space-y-0.5">
                  <Label htmlFor="labelRemoveBorder">
                    Tashqi ramkani o'chirish
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    Stiker tashqi hoshiyasini avtomatik olib tashlash
                  </p>
                </div>
                <Switch
                  id="labelRemoveBorder"
                  checked={removeBorder}
                  onCheckedChange={setRemoveBorder}
                />
              </div>

              <div className="flex items-center justify-between gap-4 py-3">
                <div className="space-y-0.5">
                  <Label htmlFor="labelRegmark">Regmark chizish</Label>
                  <p className="text-xs text-muted-foreground">
                    0.2 mm qalinlik, 0.7 mm vertikal chiziqcha
                  </p>
                </div>
                <Switch
                  id="labelRegmark"
                  checked={regmark}
                  onCheckedChange={setRegmark}
                />
              </div>
            </div>

            <Accordion className="rounded-lg border px-3">
              <AccordionItem value="advanced" className="border-none">
                <AccordionTrigger className="hover:no-underline">
                  <span className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                    <Wrench className="size-3.5" />
                    Qo'shimcha sozlamalar (Oraliq, SVG/EPS, Regmark)
                  </span>
                </AccordionTrigger>
                <AccordionContent className="space-y-4 pt-2">
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div className="space-y-1.5">
                      <Label htmlFor="labelGapMm">Ustunlar oralig'i (mm)</Label>
                      <Input
                        id="labelGapMm"
                        type="number"
                        step="0.5"
                        value={gapMm}
                        onChange={(e) => setGapMm(e.target.value)}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="labelMaxWidthMm">
                        Maks. val eni (mm, 0=cheksiz)
                      </Label>
                      <Input
                        id="labelMaxWidthMm"
                        type="number"
                        step="1"
                        value={maxWidthMm}
                        onChange={(e) => setMaxWidthMm(e.target.value)}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="labelRegStroke">
                        Regmark qalinligi (mm)
                      </Label>
                      <Input
                        id="labelRegStroke"
                        type="number"
                        step="0.05"
                        value={regStroke}
                        onChange={(e) => setRegStroke(e.target.value)}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="labelRegTick">
                        Regmark uzunligi (mm)
                      </Label>
                      <Input
                        id="labelRegTick"
                        type="number"
                        step="0.1"
                        value={regTick}
                        onChange={(e) => setRegTick(e.target.value)}
                      />
                    </div>
                    <div className="space-y-1.5 sm:col-span-2">
                      <Label htmlFor="labelRegWidthMm">
                        Regmark eni (mm, bo'sh = stiker eni)
                      </Label>
                      <Input
                        id="labelRegWidthMm"
                        type="number"
                        step="0.5"
                        min="0"
                        placeholder="Avto (stiker eni bilan bir xil)"
                        className="tabular-nums"
                        value={regWidthMm}
                        onChange={(e) => setRegWidthMm(e.target.value)}
                      />
                    </div>
                  </div>
                  <Separator />
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <Label htmlFor="labelExportSvg">
                        SVG formatda ham saqlash
                      </Label>
                      <Switch
                        id="labelExportSvg"
                        checked={exportSvg}
                        onCheckedChange={setExportSvg}
                      />
                    </div>
                    <div className="flex items-center justify-between">
                      <Label htmlFor="labelExportEps">
                        EPS formatda ham saqlash
                      </Label>
                      <Switch
                        id="labelExportEps"
                        checked={exportEps}
                        onCheckedChange={setExportEps}
                      />
                    </div>
                  </div>
                </AccordionContent>
              </AccordionItem>
            </Accordion>

            <Button
              size="lg"
              className="w-full"
              onClick={() => void handleRun()}
              disabled={running}
            >
              {running ? <Loader2 className="animate-spin" /> : <Play />}
              <span>
                {running
                  ? `Montaj bajarilmoqda...${runProgress ? ` ${runProgress.percent}%` : ""}`
                  : "Valga Joylashtirish"}
              </span>
            </Button>

            {running && runProgress && (
              <div className="space-y-2 rounded-lg border bg-muted/40 p-3">
                <div className="flex items-center justify-between gap-2 text-xs">
                  <span className="truncate font-medium text-foreground" title={runProgress.message}>
                    {runProgress.message}
                  </span>
                  <span className="shrink-0 tabular-nums text-muted-foreground">
                    {runProgress.percent}% · {Math.floor(runProgress.elapsedSec)}s
                  </span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-primary transition-all duration-300 ease-out"
                    style={{ width: `${Math.max(4, Math.min(100, runProgress.percent))}%` }}
                  />
                </div>
                {runProgress.total > 1 && (
                  <div className="text-[11px] tabular-nums text-muted-foreground">
                    Bosqich: {runProgress.current} / {runProgress.total}
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Live Pre-Generation Preview Card */}
        <Card className="lg:col-span-2 xl:sticky xl:top-16 xl:col-span-1 xl:self-start">
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-2">
              <Eye className="size-4 text-muted-foreground" />
              <span>Jonli ko'rinish (Montajdan oldin)</span>
              {inspected[selectedDesignIndex] && (
                <Badge variant="outline" className="max-w-[240px] truncate font-normal">
                  {inspected[selectedDesignIndex].display_name}
                </Badge>
              )}
              {previewUrl && previewPages > 1 && (
                <Badge variant="secondary" className="tabular-nums">
                  {previewPages} ta sahifa
                </Badge>
              )}
            </CardTitle>
            {hasSource && (
              <CardAction>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void refreshLivePreview()}
                  disabled={previewLoading}
                >
                  <RefreshCw
                    className={previewLoading ? "animate-spin" : undefined}
                  />
                  <span>Yangilash</span>
                </Button>
              </CardAction>
            )}
          </CardHeader>
          <CardContent>
            {previewError ? (
              <Alert variant="destructive">
                <AlertTriangle />
                <AlertTitle>Ko'rinish xatosi</AlertTitle>
                <AlertDescription>{previewError}</AlertDescription>
              </Alert>
            ) : !hasSource ? (
              <div className="flex min-h-[220px] flex-col items-center justify-center gap-2 rounded-lg border border-dashed bg-muted/30 p-6 text-center xl:min-h-[540px]">
                <Eye className="size-6 text-muted-foreground/60" />
                <span className="text-sm text-muted-foreground">
                  PDF fayl yuklanganda yoki Sela'dan yuborilganda val montaji ko'rinishi generatsiyadan oldin shu yerda chiqadi
                </span>
              </div>
            ) : previewLoading && !previewUrl ? (
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Loader2 className="size-3.5 animate-spin" />
                  <span>Val montaji ko'rinishi tayyorlanmoqda...</span>
                </div>
                <Skeleton className="h-[460px] w-full rounded-lg xl:h-[calc(100vh-14rem)] xl:min-h-[540px]" />
              </div>
            ) : previewUrl ? (
              <div className="relative">
                {previewLoading && (
                  <div className="absolute top-12 right-3 z-10 flex items-center gap-1.5 rounded-md border bg-background/95 px-2.5 py-1 text-xs text-muted-foreground shadow-sm backdrop-blur-xs">
                    <Loader2 className="size-3.5 animate-spin" />
                    <span>Yangilanmoqda...</span>
                  </div>
                )}
                <PdfPreview
                  src={previewUrl}
                  title={
                    inspected[selectedDesignIndex]
                      ? `Val Montaji — ${inspected[selectedDesignIndex].display_name}`
                      : previewPages > 1
                        ? `Val Montaji — Oldindan ko'rish (${previewPages} ta sahifa)`
                        : "Val Montaji — Oldindan ko'rish"
                  }
                  iframeClassName="h-[540px] xl:h-[calc(100vh-14rem)] xl:min-h-[540px]"
                />
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>

      {/* Results Card */}
      {result && (
        <Card ref={resultCardRef}>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckCircle2 className="size-4 text-emerald-600" />
              Montaj Natijasi
            </CardTitle>
            {result.zip_file && (
              <CardAction>
                <Button
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
                  <span>Barchasini ZIP yuklab olish</span>
                </Button>
              </CardAction>
            )}
          </CardHeader>
          <CardContent className="space-y-4">
            <CorelExportBar
              jobId={result.job_id}
              version={corel.version}
              onVersionChange={corel.setVersion}
              askOnRun={corel.askOnRun}
              onAskOnRunChange={corel.setAskOnRun}
            />

            <div className="flex flex-wrap gap-2">
              {result.output_files.map((f) => {
                const isPdf = f.filename.toLowerCase().endsWith(".pdf")
                return (
                  <div key={f.filename} className="inline-flex items-center gap-1">
                    <Button
                      variant="outline"
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
                    {isPdf && result.output_files.length > 1 && (
                      <Button
                        variant="secondary"
                        size="sm"
                        title={`${f.filename} faylini CorelDRAW (.cdr v${corel.version}) avto-konverteri bilan yuklab olish`}
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
                    )}
                  </div>
                )
              })}
            </div>

            <div className="rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Dizayn</TableHead>
                    <TableHead>Eni × Bo'yi</TableHead>
                    <TableHead>Val / Nusxa</TableHead>
                    <TableHead>Printing → Film</TableHead>
                    <TableHead>Ranglar</TableHead>
                    <TableHead>Audit</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {result.designs.map((d, idx) => (
                    <TableRow key={`${d.design_name}-${idx}`}>
                      <TableCell>{d.design_name}</TableCell>
                      <TableCell className="tabular-nums">
                        <span className="inline-flex items-center gap-1.5">
                          <span>
                            {d.width_mm} × {d.length_mm} mm
                          </span>
                          {d.rotation_deg ? (
                            <Badge
                              variant="outline"
                              className="px-1.5 py-0 text-[10px] font-normal text-muted-foreground"
                            >
                              {d.rotation_deg}°
                            </Badge>
                          ) : null}
                        </span>
                      </TableCell>
                      <TableCell className="tabular-nums">
                        <strong>{d.gear} val</strong> ({d.copies}x)
                      </TableCell>
                      <TableCell className="tabular-nums">
                        {d.printing_length_mm} → {d.film_length_mm} mm
                      </TableCell>
                      <TableCell>{d.colors.join(", ")}</TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            d.grayscale_passed ? "secondary" : "destructive"
                          }
                        >
                          {d.grayscale_passed ? "100% Black" : "Ogohlantirish"}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            {(() => {
              const pdfOutputs = result.output_files.filter((f) =>
                f.filename.toLowerCase().endsWith(".pdf")
              )
              if (pdfOutputs.length === 0) return null
              return (
                <div
                  className={
                    pdfOutputs.length === 1
                      ? "grid grid-cols-1 gap-4"
                      : "grid grid-cols-1 gap-4 xl:grid-cols-2"
                  }
                >
                  {pdfOutputs.map((f) => (
                    <PdfPreview
                      key={f.filename}
                      src={jobFileUrl(result.job_id, f.filename, true)}
                      downloadUrl={jobFileUrl(result.job_id, f.filename)}
                      downloadFilename={f.filename}
                      title={f.filename}
                      iframeClassName="h-[540px]"
                    />
                  ))}
                </div>
              )
            })()}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
