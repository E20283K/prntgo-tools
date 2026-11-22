import { useCallback, useEffect, useRef, useState } from "react"
import {
  AlertTriangle,
  ArrowRight,
  Ban,
  Barcode,
  Check,
  CheckCircle2,
  Download,
  ExternalLink,
  Eye,
  FileCheck,
  FileSliders,
  FileSpreadsheet,
  Layers,
  Loader2,
  PenLine,
  Plus,
  RefreshCw,
  Sparkles,
  Tag,
  Trash2,
  Upload,
  UploadCloud,
  X,
  ZoomIn,
} from "lucide-react"
import { toast } from "sonner"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
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
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { PdfPreview } from "@/components/PdfPreview"
import {
  apiFetch,
  jobFileUrl,
  selaSetPreviewImgUrl,
  selaSetPreviewUrl,
  type LabelHandoff,
  type SelaConfigResponse,
  type SelaGenerateResponse,
  type SelaQueueItem,
} from "@/lib/api"

interface SelaTabProps {
  ready: boolean
  onSendToLabelImp: (handoff: LabelHandoff) => void
}

const ORIENTATION_LABELS: Record<string, string> = {
  portrait: "Tik (Portrait — 26 dona/sahifa)",
  landscape: "Yotiq (Landscape — 27 dona/sahifa)",
}

const SET_MODE_LABELS: Record<string, string> = {
  end: "Artikul oxirida (ketma-ket)",
  start: "Artikul boshida (ketma-ket)",
  end_pages: "Artikul oxirida (yangi sahifa)",
  start_pages: "Artikul boshida (yangi sahifa)",
  interleaved: "Har dona uchun ketma-ket",
}

export function SelaTab({ ready, onSendToLabelImp }: SelaTabProps) {
  const [config, setConfig] = useState<SelaConfigResponse | null>(null)
  const [templateName, setTemplateName] = useState<string>("")
  const [orientation, setOrientation] = useState<string>("portrait")
  const [setMode, setSetMode] = useState<string>("end")
  const [inputMode, setInputMode] = useState<string>("manual")

  const [artikul, setArtikul] = useState("SI7804050205")
  const [colour, setColour] = useState("33")
  const [size, setSize] = useState("104/ 4-5 YEARS")
  const [barcode, setBarcode] = useState("4620544686957")
  const [qty, setQty] = useState("26")

  const [selectedGeneral, setSelectedGeneral] = useState<string[]>([])
  const [selectedSostav, setSelectedSostav] = useState<string>("__none__")
  const [zoomPreview, setZoomPreview] = useState<{
    title: string
    files: string[]
  } | null>(null)
  const [queue, setQueue] = useState<SelaQueueItem[]>([])

  const [csvFile, setCsvFile] = useState<File | null>(null)
  const [csvDragOver, setCsvDragOver] = useState(false)

  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)

  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<SelaGenerateResponse | null>(null)

  const templateInputRef = useRef<HTMLInputElement>(null)
  const csvInputRef = useRef<HTMLInputElement>(null)
  const resultCardRef = useRef<HTMLDivElement>(null)
  const previewUrlRef = useRef<string | null>(null)

  const loadConfig = useCallback(async () => {
    try {
      const res = await apiFetch("/api/sela/config")
      const data: SelaConfigResponse = await res.json()
      setConfig(data)
      if (data.templates.length > 0) {
        setTemplateName((prev) =>
          prev && data.templates.some((t) => t.name === prev)
            ? prev
            : data.templates[0].name
        )
      } else {
        setTemplateName("")
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Konfiguratsiya yuklanmadi")
    }
  }, [])

  useEffect(() => {
    if (ready) {
      void loadConfig()
    }
  }, [ready, loadConfig])

  const refreshLivePreview = useCallback(async () => {
    if (!templateName) return
    setPreviewLoading(true)
    setPreviewError(null)
    const qs = new URLSearchParams({
      artikul,
      colour,
      size,
      barcode,
      template_name: templateName,
      _t: String(Date.now()),
    })
    try {
      const res = await apiFetch(`/api/sela/preview?${qs}`)
      const blob = await res.blob()
      const nextUrl = URL.createObjectURL(blob)
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current)
      previewUrlRef.current = nextUrl
      setPreviewUrl(nextUrl)
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : "Ko'rinish xatosi")
    } finally {
      setPreviewLoading(false)
    }
  }, [artikul, colour, size, barcode, templateName])

  useEffect(() => {
    if (!templateName) return
    const timer = window.setTimeout(() => {
      void refreshLivePreview()
    }, 350)
    return () => window.clearTimeout(timer)
  }, [refreshLivePreview, templateName])

  useEffect(() => {
    return () => {
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current)
    }
  }, [])

  async function handleTemplateUpload(file: File | undefined) {
    if (!file) return
    const fd = new FormData()
    fd.append("file", file)
    try {
      await apiFetch("/api/sela/template", { method: "POST", body: fd })
      toast.success(`Shablon yuklandi: ${file.name}`)
      await loadConfig()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Shablon yuklanmadi")
    } finally {
      if (templateInputRef.current) templateInputRef.current.value = ""
    }
  }

  function handleAddToQueue() {
    const sostavKey = selectedSostav === "__none__" ? null : selectedSostav
    setQueue((prev) => [
      ...prev,
      {
        artikul: artikul.trim(),
        colour: colour.trim(),
        size: size.trim(),
        barcode: barcode.trim(),
        qty: parseInt(qty, 10) || 26,
        general_sets: [...selectedGeneral],
        sostav_key: sostavKey,
      },
    ])
    toast.success("Ro'yxatga qo'shildi")
  }

  async function handleGenerate(useCurrentSingleOnly: boolean) {
    setSubmitting(true)
    try {
      const fd = new FormData()
      fd.append("template_name", templateName)
      fd.append("orientation", orientation)
      fd.append("set_mode", setMode)
      fd.append("general_sets_json", JSON.stringify(selectedGeneral))
      if (selectedSostav && selectedSostav !== "__none__") {
        fd.append("sostav_key", selectedSostav)
      }

      if (inputMode === "csv") {
        if (!csvFile) {
          throw new Error("Iltimos, CSV faylni tanlang.")
        }
        fd.append("csv_file", csvFile)
      } else {
        const items: SelaQueueItem[] =
          !useCurrentSingleOnly && queue.length > 0
            ? queue
            : [
                {
                  artikul: artikul.trim(),
                  colour: colour.trim(),
                  size: size.trim(),
                  barcode: barcode.trim(),
                  qty: parseInt(qty, 10) || 26,
                },
              ]
        fd.append("items_json", JSON.stringify(items))
      }

      const res = await apiFetch("/api/sela/generate", {
        method: "POST",
        body: fd,
      })
      const data: SelaGenerateResponse = await res.json()
      setResult(data)
      toast.success("Sela A4 PDF muvaffaqiyatli yaratildi")
      window.setTimeout(() => {
        resultCardRef.current?.scrollIntoView({ behavior: "smooth" })
      }, 100)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Yaratishda xatolik")
    } finally {
      setSubmitting(false)
    }
  }

  const templates = config?.templates ?? []
  const generalSets = config?.set_catalog.general ?? []
  const sostavGroups = config?.set_catalog.sostav_groups ?? []

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
            <Tag className="size-5 text-muted-foreground" />
            Sela Etiketka Generatori
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Artikul, rang, o'lcham va EAN-13 barkod asosida A4 PDF yarating, so'ngra Val Montajiga o'tkazing.
          </p>
        </div>
        <div>
          <input
            ref={templateInputRef}
            type="file"
            accept=".pdf,.svg"
            className="hidden"
            onChange={(e) => void handleTemplateUpload(e.target.files?.[0])}
          />
          <Button
            variant="outline"
            size="sm"
            onClick={() => templateInputRef.current?.click()}
          >
            <Upload />
            <span>Shablon yuklash</span>
          </Button>
        </div>
      </div>

      {/* No template warning */}
      {config && templates.length === 0 && (
        <Alert>
          <AlertTriangle />
          <AlertTitle>Shablon topilmadi</AlertTitle>
          <AlertDescription>
            Serverda hali Sela shabloni (.pdf yoki .svg) mavjud emas. Yuqoridagi tugma orqali shablonni bir marta yuklang.
          </AlertDescription>
        </Alert>
      )}

      {/* Template & Layout Settings */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileSliders className="size-4 text-muted-foreground" />
            Shablon va sahifa sozlamalari
          </CardTitle>
          <CardDescription>
            A4 varaq yo'nalishi va qo'shimcha etiketkalar joylashuvi
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <Label>Faol shablon</Label>
              <Select
                value={templateName}
                onValueChange={(v) => v && setTemplateName(v)}
                disabled={templates.length === 0}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Shablon yuklanmagan" />
                </SelectTrigger>
                <SelectContent>
                  {templates.map((t) => (
                    <SelectItem key={t.name} value={t.name}>
                      {t.name} ({t.size_kb} KB)
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>A4 yo'nalishi</Label>
              <Select
                value={orientation}
                onValueChange={(v) => v && setOrientation(v)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue>{ORIENTATION_LABELS[orientation]}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="portrait">
                    {ORIENTATION_LABELS.portrait}
                  </SelectItem>
                  <SelectItem value="landscape">
                    {ORIENTATION_LABELS.landscape}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Qo'shimcha etiketkalar tartibi</Label>
              <Select
                value={setMode}
                onValueChange={(v) => v && setSetMode(v)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue>{SET_MODE_LABELS[setMode]}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(SET_MODE_LABELS).map(([k, label]) => (
                    <SelectItem key={k} value={k}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Mode Tabs: Manual / CSV */}
      <Tabs value={inputMode} onValueChange={(v) => setInputMode(String(v))}>
        <TabsList>
          <TabsTrigger value="manual">
            <PenLine />
            <span>Qo'lda kiritish</span>
          </TabsTrigger>
          <TabsTrigger value="csv">
            <FileSpreadsheet />
            <span>CSV fayldan yuklash</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="manual" className="mt-4">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Barcode className="size-4 text-muted-foreground" />
                  Etiketka ma'lumotlari
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="selaArtikul">Artikul</Label>
                    <Input
                      id="selaArtikul"
                      value={artikul}
                      onChange={(e) => setArtikul(e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="selaColour">Rang (Colour)</Label>
                    <Input
                      id="selaColour"
                      value={colour}
                      onChange={(e) => setColour(e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="selaSize">O'lcham (Size)</Label>
                    <Input
                      id="selaSize"
                      value={size}
                      onChange={(e) => setSize(e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="selaBarcode">Barkod (EAN-13)</Label>
                    <Input
                      id="selaBarcode"
                      className="tabular-nums"
                      value={barcode}
                      onChange={(e) => setBarcode(e.target.value)}
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="selaQty">Soni (dona)</Label>
                  <Input
                    id="selaQty"
                    type="number"
                    min={1}
                    className="tabular-nums"
                    value={qty}
                    onChange={(e) => setQty(e.target.value)}
                  />
                </div>

                <div className="flex flex-wrap gap-2">
                  <Button variant="outline" onClick={handleAddToQueue}>
                    <Plus />
                    <span>Ro'yxatga qo'shish</span>
                  </Button>
                  <Button
                    onClick={() => void handleGenerate(true)}
                    disabled={submitting}
                  >
                    {submitting ? (
                      <Loader2 className="animate-spin" />
                    ) : (
                      <Sparkles />
                    )}
                    <span>Hozir yaratish</span>
                  </Button>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Eye className="size-4 text-muted-foreground" />
                  Jonli ko'rinish (PDF)
                </CardTitle>
                <CardDescription>78.2 × 20.2 mm · Vektor PDF</CardDescription>
                <CardAction>
                  <div className="flex items-center gap-1.5">
                    {previewUrl && (
                      <Button
                        variant="outline"
                        size="sm"
                        nativeButton={false}
                        render={
                          <a
                            href={previewUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                          />
                        }
                      >
                        <ExternalLink />
                        <span className="hidden sm:inline">PDF ochish</span>
                      </Button>
                    )}
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => void refreshLivePreview()}
                      disabled={!templateName || previewLoading}
                    >
                      <RefreshCw
                        className={previewLoading ? "animate-spin" : ""}
                      />
                      <span>Yangilash</span>
                    </Button>
                  </div>
                </CardAction>
              </CardHeader>
              <CardContent>
                {previewLoading && !previewUrl ? (
                  <div className="flex min-h-[220px] items-center justify-center rounded-lg border bg-muted/40 p-4">
                    <Skeleton className="h-24 w-full max-w-sm rounded-md" />
                  </div>
                ) : previewError ? (
                  <div className="flex min-h-[220px] items-center justify-center rounded-lg border bg-muted/40 p-4">
                    <span className="text-sm text-destructive">
                      {previewError}
                    </span>
                  </div>
                ) : previewUrl ? (
                  <PdfPreview
                    src={previewUrl}
                    title={`${artikul || "sela"}_preview.pdf`}
                    showHeader={false}
                    showToolbar={false}
                    iframeClassName="h-[220px]"
                  />
                ) : (
                  <div className="flex min-h-[220px] items-center justify-center rounded-lg border bg-muted/40 p-4">
                    <span className="text-sm text-muted-foreground">
                      Shablon tanlanganda jonli PDF ko'rinish chiqadi
                    </span>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="csv" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileSpreadsheet className="size-4 text-muted-foreground" />
                CSV fayl yuklash
              </CardTitle>
              <CardDescription>
                Ustunlar:{" "}
                <code className="rounded bg-muted px-1 py-0.5 text-xs">
                  artikul, colour, size, barcode, qty
                </code>{" "}
                (ixtiyoriy:{" "}
                <code className="rounded bg-muted px-1 py-0.5 text-xs">set</code>
                )
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div
                role="button"
                tabIndex={0}
                onClick={() => csvInputRef.current?.click()}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    csvInputRef.current?.click()
                  }
                }}
                onDragOver={(e) => {
                  e.preventDefault()
                  setCsvDragOver(true)
                }}
                onDragLeave={() => setCsvDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault()
                  setCsvDragOver(false)
                  const f = e.dataTransfer.files[0]
                  if (f) setCsvFile(f)
                }}
                className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-8 text-center transition-colors ${
                  csvDragOver
                    ? "border-primary bg-muted"
                    : "border-border bg-muted/30 hover:border-foreground/40 hover:bg-muted/60"
                }`}
              >
                <div className="flex size-10 items-center justify-center rounded-lg border bg-background text-muted-foreground">
                  <UploadCloud className="size-5" />
                </div>
                <div className="text-sm font-medium">
                  {csvFile
                    ? `Tanlandi: ${csvFile.name}`
                    : "CSV faylni shu yerga tashlang yoki tanlang"}
                </div>
                <div className="text-xs text-muted-foreground">
                  UTF-8 formatdagi .csv fayl
                </div>
                <input
                  ref={csvInputRef}
                  type="file"
                  accept=".csv"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0]
                    if (f) setCsvFile(f)
                  }}
                />
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Care & Composition Sets */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Layers className="size-4 text-muted-foreground" />
            Qo'shimcha etiketkalar (Umumiy va Sostavnik)
          </CardTitle>
          {(selectedGeneral.length > 0 || selectedSostav !== "__none__") && (
            <CardAction>
              <Badge variant="secondary">
                {[
                  selectedGeneral.length > 0
                    ? `${selectedGeneral.length} ta umumiy`
                    : null,
                  selectedSostav !== "__none__"
                    ? `Sostavnik: ${selectedSostav}`
                    : null,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </Badge>
            </CardAction>
          )}
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-2.5">
            <Label>Umumiy etiketkalar</Label>
            <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
              {generalSets.map((item) => {
                const isSelected = selectedGeneral.includes(item.name)
                const toggleGeneral = () =>
                  setSelectedGeneral((prev) =>
                    prev.includes(item.name)
                      ? prev.filter((n) => n !== item.name)
                      : [...prev, item.name]
                  )
                return (
                  <div
                    key={item.name}
                    role="button"
                    tabIndex={0}
                    onClick={toggleGeneral}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault()
                        toggleGeneral()
                      }
                    }}
                    className={`group flex cursor-pointer flex-col gap-2 rounded-lg border p-2.5 text-left transition-all select-none ${
                      isSelected
                        ? "border-primary bg-primary/[0.04] ring-1 ring-primary"
                        : "border-border bg-card hover:border-foreground/30 hover:bg-accent/40"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1.5">
                      <div className="flex min-w-0 items-center gap-2">
                        <span
                          className={`flex size-4 shrink-0 items-center justify-center rounded border transition-colors ${
                            isSelected
                              ? "border-primary bg-primary text-primary-foreground"
                              : "border-muted-foreground/40 bg-background text-transparent"
                          }`}
                        >
                          <Check className="size-3 stroke-[2.5]" />
                        </span>
                        <span
                          className="truncate text-xs font-semibold"
                          title={item.label}
                        >
                          {item.label}
                        </span>
                      </div>
                      <button
                        type="button"
                        title="Kattalashtirish"
                        onClick={(e) => {
                          e.stopPropagation()
                          setZoomPreview({
                            title: item.label,
                            files: [item.name],
                          })
                        }}
                        className="flex size-6 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                      >
                        <ZoomIn className="size-3.5" />
                      </button>
                    </div>
                    <div className="overflow-hidden rounded-md border bg-white p-1">
                      <img
                        src={selaSetPreviewImgUrl(item.name, 150)}
                        alt={item.label}
                        loading="lazy"
                        className="pointer-events-none block h-[80px] w-full object-contain bg-white"
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          <div className="space-y-2.5">
            <Label>Sostavnik (tarkib guruhi)</Label>
            <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
              {/* None option */}
              <div
                role="button"
                tabIndex={0}
                onClick={() => setSelectedSostav("__none__")}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault()
                    setSelectedSostav("__none__")
                  }
                }}
                className={`flex cursor-pointer flex-col gap-2 rounded-lg border p-2.5 text-left transition-all select-none ${
                  selectedSostav === "__none__"
                    ? "border-primary bg-primary/[0.04] ring-1 ring-primary"
                    : "border-border bg-card hover:border-foreground/30 hover:bg-accent/40"
                }`}
              >
                <div className="flex items-center gap-2">
                  <span
                    className={`flex size-4 shrink-0 items-center justify-center rounded-full border transition-colors ${
                      selectedSostav === "__none__"
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-muted-foreground/40 bg-background text-transparent"
                    }`}
                  >
                    <Check className="size-3 stroke-[2.5]" />
                  </span>
                  <span className="text-xs font-semibold">Yo'q</span>
                </div>
                <div className="flex flex-1 min-h-[60px] flex-col items-center justify-center gap-1 rounded-md border border-dashed bg-muted/30 p-3 text-center text-xs text-muted-foreground">
                  <Ban className="size-4 opacity-70" />
                  <span>Sostavnik qo'shilmaydi</span>
                </div>
              </div>

              {sostavGroups.map((grp) => {
                const isSelected = selectedSostav === grp.key
                const files = grp.files ?? []
                return (
                  <div
                    key={grp.key}
                    role="button"
                    tabIndex={0}
                    onClick={() => setSelectedSostav(grp.key)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault()
                        setSelectedSostav(grp.key)
                      }
                    }}
                    className={`group flex cursor-pointer flex-col gap-2 rounded-lg border p-2.5 text-left transition-all select-none ${
                      isSelected
                        ? "border-primary bg-primary/[0.04] ring-1 ring-primary"
                        : "border-border bg-card hover:border-foreground/30 hover:bg-accent/40"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1.5">
                      <div className="flex min-w-0 items-center gap-2">
                        <span
                          className={`flex size-4 shrink-0 items-center justify-center rounded-full border transition-colors ${
                            isSelected
                              ? "border-primary bg-primary text-primary-foreground"
                              : "border-muted-foreground/40 bg-background text-transparent"
                          }`}
                        >
                          <Check className="size-3 stroke-[2.5]" />
                        </span>
                        <span
                          className="truncate text-xs font-semibold"
                          title={grp.label}
                        >
                          {grp.label}
                        </span>
                      </div>
                      {files.length > 0 && (
                        <button
                          type="button"
                          title="Kattalashtirish"
                          onClick={(e) => {
                            e.stopPropagation()
                            setZoomPreview({
                              title: grp.label,
                              files,
                            })
                          }}
                          className="flex size-6 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                        >
                          <ZoomIn className="size-3.5" />
                        </button>
                      )}
                    </div>
                    <div className="flex flex-col gap-1.5">
                      {files.map((fn) => (
                        <div
                          key={fn}
                          className="overflow-hidden rounded-md border bg-white p-1"
                        >
                          <img
                            src={selaSetPreviewImgUrl(fn, 150)}
                            alt={fn}
                            loading="lazy"
                            className="pointer-events-none block h-[72px] w-full object-contain bg-white"
                          />
                        </div>
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Queued Items */}
      {queue.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              Ro'yxatdagi etiketkalar
              <Badge variant="secondary" className="tabular-nums">
                {queue.length}
              </Badge>
            </CardTitle>
            <CardAction>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => setQueue([])}
              >
                <Trash2 />
                <span>Tozalash</span>
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent>
            <div className="rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Artikul</TableHead>
                    <TableHead>Rang</TableHead>
                    <TableHead>O'lcham</TableHead>
                    <TableHead>Barkod</TableHead>
                    <TableHead>Soni</TableHead>
                    <TableHead className="w-12" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {queue.map((it, idx) => (
                    <TableRow key={`${it.artikul}-${it.barcode}-${idx}`}>
                      <TableCell className="font-medium">{it.artikul}</TableCell>
                      <TableCell>{it.colour}</TableCell>
                      <TableCell>{it.size}</TableCell>
                      <TableCell>
                        <code className="rounded bg-muted px-1.5 py-0.5 text-xs tabular-nums">
                          {it.barcode}
                        </code>
                      </TableCell>
                      <TableCell className="tabular-nums">{it.qty}</TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          title="O'chirish"
                          onClick={() =>
                            setQueue((prev) => prev.filter((_, i) => i !== idx))
                          }
                        >
                          <X />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Main Submit */}
      <div>
        <Button
          size="lg"
          onClick={() => void handleGenerate(false)}
          disabled={submitting}
        >
          {submitting ? <Loader2 className="animate-spin" /> : <FileCheck />}
          <span>{submitting ? "Yaratilmoqda..." : "A4 PDF Yaratish"}</span>
        </Button>
      </div>

      {/* Result Card */}
      {result && (
        <Card ref={resultCardRef}>
          <CardContent className="space-y-4">
            <Alert>
              <CheckCircle2 className="text-emerald-600" />
              <AlertTitle>Tayyor</AlertTitle>
              <AlertDescription className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <span className="tabular-nums">
                  Jami {result.total_labels} ta stiker ({result.page_count} ta A4 sahifa, {result.size_kb} KB)
                </span>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    nativeButton={false}
                    render={
                      <a
                        href={jobFileUrl(result.job_id, result.output_file)}
                        download={result.output_file}
                      />
                    }
                  >
                    <Download />
                    <span>A4 PDF yuklab olish</span>
                  </Button>
                  <Button
                    size="sm"
                    onClick={() =>
                      onSendToLabelImp({
                        job_id: result.job_id,
                        filename: result.output_file,
                        total_labels: result.total_labels,
                      })
                    }
                  >
                    <span>Keyingi qadam: Val Montaji</span>
                    <ArrowRight />
                  </Button>
                </div>
              </AlertDescription>
            </Alert>

            <PdfPreview
              src={jobFileUrl(result.job_id, result.output_file, true)}
              downloadUrl={jobFileUrl(result.job_id, result.output_file)}
              downloadFilename={result.output_file}
              title={result.output_file}
              iframeClassName="h-[620px]"
            />
          </CardContent>
        </Card>
      )}

      {/* Zoom Preview Dialog */}
      <Dialog
        open={zoomPreview !== null}
        onOpenChange={(open) => {
          if (!open) setZoomPreview(null)
        }}
      >
        <DialogContent className="sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>{zoomPreview?.title}</DialogTitle>
          </DialogHeader>
          <div className="max-h-[75vh] space-y-3 overflow-y-auto pr-1">
            {zoomPreview?.files.map((fn) => (
              <div
                key={fn}
                className="overflow-hidden rounded-lg border bg-card"
              >
                <div className="flex items-center justify-between gap-2 border-b bg-muted/40 px-3 py-1.5 text-xs">
                  <span className="truncate font-medium text-muted-foreground">
                    {fn}
                  </span>
                  <a
                    href={selaSetPreviewUrl(fn)}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-primary hover:underline"
                  >
                    <ExternalLink className="size-3" />
                    PDF ochish
                  </a>
                </div>
                <div className="flex items-center justify-center bg-white p-3">
                  <img
                    src={selaSetPreviewImgUrl(fn, 260)}
                    alt={fn}
                    className="max-h-[260px] w-full object-contain"
                  />
                </div>
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
