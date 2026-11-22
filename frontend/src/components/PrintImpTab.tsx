import { useCallback, useEffect, useRef, useState } from "react"
import {
  Archive,
  CheckCircle2,
  Download,
  FolderUp,
  LayoutGrid,
  Loader2,
  Play,
  ScanSearch,
  SlidersHorizontal,
  Wrench,
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
import { PdfPreview } from "@/components/PdfPreview"
import { PrintImpSvgPreview } from "@/components/PrintImpSvgPreview"
import {
  apiFetch,
  jobFileUrl,
  type PrintPreflightResponse,
  type PrintPreset,
  type PrintPresetsResponse,
  type PrintRunResponse,
} from "@/lib/api"

interface PrintImpTabProps {
  ready: boolean
}

const PRINT_MODE_LABELS: Record<string, string> = {
  single: "Bir tomonlama (Oldi)",
  sheetwise: "Oldi-Orqa alohida (Sheetwise)",
  turn: "Svoj (Work & Turn)",
  tumble: "Bosh-oyoq (Work & Tumble)",
}

const PRINT_STYLE_LABELS: Record<string, string> = {
  offset_standard: "Gilotin Ofset (CMYK + Krest)",
  packaging: "Qadoqlash / Pichoqli",
  digital_compact: "Raqamli ixcham",
  standard: "Standart rang shkalasi",
  compact: "Ixcham yon pasport",
}

const PRINT_STRATEGY_LABELS: Record<string, string> = {
  smart: "Smart (1 tur 1 formada)",
  split: "Maksimal tejamkor (Bo'lish)",
  single: "1 ta formaga majburlash",
}

export function PrintImpTab({ ready }: PrintImpTabProps) {
  const [presets, setPresets] = useState<Record<string, PrintPreset>>({})
  const [selectedPresetKey, setSelectedPresetKey] = useState<string>("")

  const [frontFiles, setFrontFiles] = useState<File[]>([])
  const [backFile, setBackFile] = useState<File | null>(null)
  const [dielineFile, setDielineFile] = useState<File | null>(null)

  const [sheetW, setSheetW] = useState("500")
  const [sheetH, setSheetH] = useState("350")
  const [trimW, setTrimW] = useState("")
  const [trimH, setTrimH] = useState("")

  const [mode, setMode] = useState("single")
  const [qty, setQty] = useState("1000")
  const [orderNo, setOrderNo] = useState("№1001")
  const [jobName, setJobName] = useState("")

  const [innerBleed, setInnerBleed] = useState("1.5")
  const [outerBleed, setOuterBleed] = useState("3.0")
  const [gutter, setGutter] = useState("3.0")
  const [gripper, setGripper] = useState("15.0")
  const [style, setStyle] = useState("offset_standard")
  const [strategy, setStrategy] = useState("smart")
  const [quantitiesCsv, setQuantitiesCsv] = useState("")
  const [waste, setWaste] = useState("0")
  const [separateFiles, setSeparateFiles] = useState(false)

  const [preflightLoading, setPreflightLoading] = useState(false)
  const [preflight, setPreflight] = useState<PrintPreflightResponse | null>(
    null
  )

  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<PrintRunResponse | null>(null)
  const resultCardRef = useRef<HTMLDivElement>(null)
  const preflightReqIdRef = useRef(0)

  const loadPresets = useCallback(async () => {
    try {
      const res = await apiFetch("/api/print-imp/presets")
      const data: PrintPresetsResponse = await res.json()
      setPresets(data.presets)
      const firstKey = Object.keys(data.presets)[0]
      if (firstKey) {
        setSelectedPresetKey(firstKey)
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Shablonlar yuklanmadi")
    }
  }, [])

  useEffect(() => {
    if (ready) {
      void loadPresets()
    }
  }, [ready, loadPresets])

  function applyPreset(key: string, p: PrintPreset) {
    setSelectedPresetKey(key)
    setSheetW(String(p.sheet_w))
    setSheetH(String(p.sheet_h))
    setGripper(String(p.gripper))
    setInnerBleed(String(p.inner_bleed))
    setOuterBleed(String(p.outer_bleed))
    setGutter(String(p.gutter))
    setStyle(p.style)
  }

  async function executePreflight(
    files: File[],
    dieline: File | null,
    options?: { silent?: boolean; forceTrim?: boolean }
  ) {
    if (!files.length) {
      if (!options?.silent) {
        toast.error("Avval Oldi PDF faylni tanlang.")
      }
      return
    }
    const reqId = ++preflightReqIdRef.current
    setPreflightLoading(true)
    try {
      const fd = new FormData()
      files.forEach((f) => fd.append("front_files", f))
      if (dieline) fd.append("dieline_file", dieline)

      const res = await apiFetch("/api/print-imp/preflight", {
        method: "POST",
        body: fd,
      })
      const data: PrintPreflightResponse = await res.json()
      if (reqId !== preflightReqIdRef.current) return
      setPreflight(data)

      const shouldFillTrim =
        options?.forceTrim || (!trimW.trim() && !trimH.trim())
      if (shouldFillTrim) {
        if (data.dieline_trim) {
          setTrimW(String(data.dieline_trim.trim_w_mm))
          setTrimH(String(data.dieline_trim.trim_h_mm))
        } else if (data.trim_box_mm[0] > 0) {
          setTrimW(String(data.trim_box_mm[0]))
          setTrimH(String(data.trim_box_mm[1]))
        }
      }
      if (!options?.silent) {
        toast.success("Preflight tahlili yakunlandi")
      }
    } catch (err) {
      if (reqId !== preflightReqIdRef.current) return
      if (!options?.silent) {
        toast.error(err instanceof Error ? err.message : "Preflight xatosi")
      }
    } finally {
      if (reqId === preflightReqIdRef.current) {
        setPreflightLoading(false)
      }
    }
  }

  async function handlePreflight() {
    await executePreflight(frontFiles, dielineFile, {
      silent: false,
      forceTrim: true,
    })
  }

  async function handleRun() {
    if (!frontFiles.length) {
      toast.error("Avval Oldi PDF faylni tanlang.")
      return
    }
    setRunning(true)
    try {
      const selectedPreset = presets[selectedPresetKey]
      const fd = new FormData()
      frontFiles.forEach((f) => fd.append("front_files", f))
      if (backFile) fd.append("back_file", backFile)
      if (dielineFile) fd.append("dieline_file", dielineFile)

      fd.append("sheet_w_mm", sheetW)
      fd.append("sheet_h_mm", sheetH)
      if (trimW.trim()) fd.append("trim_w_mm", trimW.trim())
      if (trimH.trim()) fd.append("trim_h_mm", trimH.trim())
      fd.append("inner_bleed_mm", innerBleed)
      fd.append("outer_bleed_mm", outerBleed)
      fd.append("gutter_mm", gutter)
      fd.append("gripper_mm", gripper)
      fd.append("mode", mode)
      fd.append("style", style)
      fd.append("category", selectedPreset?.category || "guillotine")
      fd.append("cut_style", selectedPreset?.cut_style || "double")
      fd.append("order_number", orderNo)
      if (jobName.trim()) fd.append("job_name", jobName.trim())
      fd.append("order_quantity", qty)
      fd.append("waste_sheets", waste)
      fd.append("separate_files", String(separateFiles))
      fd.append("strategy", strategy)
      if (quantitiesCsv.trim()) {
        fd.append("quantities_csv", quantitiesCsv.trim())
      }

      const res = await apiFetch("/api/print-imp/run", {
        method: "POST",
        body: fd,
      })
      const data: PrintRunResponse = await res.json()
      setResult(data)
      toast.success("Varaq montaji muvaffaqiyatli yakunlandi")
      window.setTimeout(() => {
        resultCardRef.current?.scrollIntoView({ behavior: "smooth" })
      }, 100)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Montaj xatosi")
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
          <LayoutGrid className="size-5 text-muted-foreground" />
          Varaq Montaji va Preflight
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Vizitka, flayer, qadoqlash (pichoqli) va ko'p dizaynli to'plamlar uchun 100% vektorli varaq montaji.
        </p>
      </div>

      {/* Step 1: Files & Preflight */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FolderUp className="size-4 text-muted-foreground" />
            1. Dizayn fayllarini yuklash
          </CardTitle>
          <CardDescription>
            Oldi, ixtiyoriy Orqa va Pichoq (Dieline) PDF fayllari
          </CardDescription>
          <CardAction>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void handlePreflight()}
              disabled={preflightLoading}
            >
              {preflightLoading ? (
                <Loader2 className="animate-spin" />
              ) : (
                <ScanSearch />
              )}
              <span>Preflight tekshirish</span>
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="printFrontFiles">Oldi (Front) PDF(lar) *</Label>
              <Input
                id="printFrontFiles"
                type="file"
                accept=".pdf"
                multiple
                onChange={(e) => {
                  const files = Array.from(e.target.files ?? [])
                  setFrontFiles(files)
                  if (files.length > 0) {
                    void executePreflight(files, dielineFile, {
                      silent: true,
                      forceTrim: false,
                    })
                  } else {
                    setPreflight(null)
                  }
                }}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="printBackFile">
                Orqa (Back) PDF (ixtiyoriy)
              </Label>
              <Input
                id="printBackFile"
                type="file"
                accept=".pdf"
                onChange={(e) => setBackFile(e.target.files?.[0] ?? null)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="printDielineFile">
                Pichoq (Dieline) PDF (ixtiyoriy)
              </Label>
              <Input
                id="printDielineFile"
                type="file"
                accept=".pdf"
                onChange={(e) => {
                  const file = e.target.files?.[0] ?? null
                  setDielineFile(file)
                  if (file && frontFiles.length > 0) {
                    void executePreflight(frontFiles, file, {
                      silent: true,
                      forceTrim: true,
                    })
                  }
                }}
              />
            </div>
          </div>

          {preflight && (
            <Alert>
              <ScanSearch />
              <AlertTitle className="tabular-nums">
                Preflight: {preflight.page_count} sahifa | O'lcham:{" "}
                {preflight.trim_box_mm[0]}×{preflight.trim_box_mm[1]} mm |
                Bleed: {preflight.detected_bleed_mm} mm | Ranglar:{" "}
                {preflight.colors.map((c) => c.name).join(", ") || "-"}
              </AlertTitle>
              <AlertDescription className="mt-2 space-y-1.5">
                {preflight.issues.length === 0 ? (
                  <Badge variant="secondary">Xatoliklar topilmadi</Badge>
                ) : (
                  preflight.issues.map((issue, idx) => (
                    <div key={idx} className="flex items-center gap-2">
                      <Badge
                        variant={
                          issue.severity === "ERROR"
                            ? "destructive"
                            : issue.severity === "WARNING"
                              ? "outline"
                              : "secondary"
                        }
                      >
                        {issue.severity}
                      </Badge>
                      <span>{issue.message}</span>
                    </div>
                  ))
                )}
              </AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>

      {/* Step 2: Presets & Parameters */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <SlidersHorizontal className="size-4 text-muted-foreground" />
            2. Shablon va parametrlar
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          {/* Presets */}
          {Object.keys(presets).length > 0 && (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {Object.entries(presets).map(([key, p]) => {
                const isSelected = key === selectedPresetKey
                return (
                  <Card
                    key={key}
                    size="sm"
                    role="button"
                    tabIndex={0}
                    onClick={() => applyPreset(key, p)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault()
                        applyPreset(key, p)
                      }
                    }}
                    className={`cursor-pointer transition-all outline-none focus-visible:ring-3 focus-visible:ring-ring/50 ${
                      isSelected
                        ? "bg-muted/60 ring-2 ring-primary"
                        : "hover:bg-muted/30"
                    }`}
                  >
                    <CardHeader>
                      <CardTitle className="flex items-center justify-between gap-2 text-sm">
                        <span>{p.name}</span>
                        {isSelected && (
                          <Badge variant="default">Tanlangan</Badge>
                        )}
                      </CardTitle>
                      <CardDescription className="text-xs">
                        {p.description}
                      </CardDescription>
                    </CardHeader>
                  </Card>
                )
              })}
            </div>
          )}

          {/* Dimensions */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="space-y-2">
              <Label htmlFor="printSheetW">Qog'oz eni (mm)</Label>
              <Input
                id="printSheetW"
                type="number"
                className="tabular-nums"
                value={sheetW}
                onChange={(e) => setSheetW(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="printSheetH">Qog'oz bo'yi (mm)</Label>
              <Input
                id="printSheetH"
                type="number"
                className="tabular-nums"
                value={sheetH}
                onChange={(e) => setSheetH(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="printTrimW">Kesim eni (mm, Avto)</Label>
              <Input
                id="printTrimW"
                type="number"
                step="0.1"
                placeholder="Avto"
                className="tabular-nums"
                value={trimW}
                onChange={(e) => setTrimW(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="printTrimH">Kesim bo'yi (mm, Avto)</Label>
              <Input
                id="printTrimH"
                type="number"
                step="0.1"
                placeholder="Avto"
                className="tabular-nums"
                value={trimH}
                onChange={(e) => setTrimH(e.target.value)}
              />
            </div>
          </div>

          {/* Order info */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="space-y-2">
              <Label>Bosma rejimi</Label>
              <Select value={mode} onValueChange={(v) => v && setMode(v)}>
                <SelectTrigger className="w-full">
                  <SelectValue>{PRINT_MODE_LABELS[mode]}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(PRINT_MODE_LABELS).map(([k, label]) => (
                    <SelectItem key={k} value={k}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="printQty">Buyurtma soni (dona)</Label>
              <Input
                id="printQty"
                type="number"
                min={1}
                className="tabular-nums"
                value={qty}
                onChange={(e) => setQty(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="printOrderNo">Buyurtma raqami</Label>
              <Input
                id="printOrderNo"
                value={orderNo}
                onChange={(e) => setOrderNo(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="printJobName">Ish nomi (ixtiyoriy)</Label>
              <Input
                id="printJobName"
                placeholder="Avto fayl nomidan"
                value={jobName}
                onChange={(e) => setJobName(e.target.value)}
              />
            </div>
          </div>

          {/* Advanced Accordion */}
          <Accordion className="rounded-lg border px-3">
            <AccordionItem value="advanced" className="border-none">
              <AccordionTrigger className="hover:no-underline">
                <span className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                  <Wrench className="size-3.5" />
                  Kengaytirilgan sozlamalar (Bleed, Gutter, Klapan, Ko'p dizayn)
                </span>
              </AccordionTrigger>
              <AccordionContent className="space-y-4 pt-2">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  <div className="space-y-1.5">
                    <Label htmlFor="printInnerBleed">Ichki bleed (mm)</Label>
                    <Input
                      id="printInnerBleed"
                      type="number"
                      step="0.5"
                      value={innerBleed}
                      onChange={(e) => setInnerBleed(e.target.value)}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="printOuterBleed">Tashqi bleed (mm)</Label>
                    <Input
                      id="printOuterBleed"
                      type="number"
                      step="0.5"
                      value={outerBleed}
                      onChange={(e) => setOuterBleed(e.target.value)}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="printGutter">Oraliq / Gutter (mm)</Label>
                    <Input
                      id="printGutter"
                      type="number"
                      step="0.5"
                      value={gutter}
                      onChange={(e) => setGutter(e.target.value)}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="printGripper">Klapan / Gripper (mm)</Label>
                    <Input
                      id="printGripper"
                      type="number"
                      step="1"
                      value={gripper}
                      onChange={(e) => setGripper(e.target.value)}
                    />
                  </div>

                  <div className="space-y-1.5">
                    <Label>Texnik shablon uslubi</Label>
                    <Select
                      value={style}
                      onValueChange={(v) => v && setStyle(v)}
                    >
                      <SelectTrigger className="w-full">
                        <SelectValue>{PRINT_STYLE_LABELS[style]}</SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        {Object.entries(PRINT_STYLE_LABELS).map(
                          ([k, label]) => (
                            <SelectItem key={k} value={k}>
                              {label}
                            </SelectItem>
                          )
                        )}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-1.5">
                    <Label>To'plam strategiyasi</Label>
                    <Select
                      value={strategy}
                      onValueChange={(v) => v && setStrategy(v)}
                    >
                      <SelectTrigger className="w-full">
                        <SelectValue>
                          {PRINT_STRATEGY_LABELS[strategy]}
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        {Object.entries(PRINT_STRATEGY_LABELS).map(
                          ([k, label]) => (
                            <SelectItem key={k} value={k}>
                              {label}
                            </SelectItem>
                          )
                        )}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="printQuantitiesCsv">
                      Har tur tirajlari (vergul bilan)
                    </Label>
                    <Input
                      id="printQuantitiesCsv"
                      placeholder="1000, 2000, 1500"
                      value={quantitiesCsv}
                      onChange={(e) => setQuantitiesCsv(e.target.value)}
                    />
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="printWaste">Priladka / brak (list)</Label>
                    <Input
                      id="printWaste"
                      type="number"
                      min={0}
                      value={waste}
                      onChange={(e) => setWaste(e.target.value)}
                    />
                  </div>
                </div>

                <Separator />

                <div className="flex items-center justify-between gap-4">
                  <Label htmlFor="printSeparateFiles">
                    Oldi, Orqa va Pichoqni alohida PDF fayllarga saqlash
                  </Label>
                  <Switch
                    id="printSeparateFiles"
                    checked={separateFiles}
                    onCheckedChange={setSeparateFiles}
                  />
                </div>
              </AccordionContent>
            </AccordionItem>
          </Accordion>

          {/* Live SVG Preview */}
          <PrintImpSvgPreview
            sheetW={Number(sheetW)}
            sheetH={Number(sheetH)}
            trimW={trimW.trim() ? Number(trimW) : null}
            trimH={trimH.trim() ? Number(trimH) : null}
            detectedTrim={
              preflight?.dieline_trim
                ? [
                    preflight.dieline_trim.trim_w_mm,
                    preflight.dieline_trim.trim_h_mm,
                  ]
                : preflight?.trim_box_mm && preflight.trim_box_mm[0] > 0
                  ? preflight.trim_box_mm
                  : null
            }
            innerBleed={Number(innerBleed)}
            outerBleed={Number(outerBleed)}
            gutter={Number(gutter)}
            gripper={Number(gripper)}
            mode={mode}
            style={style}
            orderQty={Number(qty)}
            waste={Number(waste)}
            orderNo={orderNo}
            jobName={jobName}
            variantNames={frontFiles.map((f) => f.name.replace(/\.pdf$/i, ""))}
            preflightLoading={preflightLoading}
            hasFrontFiles={frontFiles.length > 0}
          />

          <Button size="lg" onClick={() => void handleRun()} disabled={running}>
            {running ? <Loader2 className="animate-spin" /> : <Play />}
            <span>
              {running ? "Montaj bajarilmoqda..." : "Varaq Montajini Bajarish"}
            </span>
          </Button>
        </CardContent>
      </Card>

      {/* Step 3: Result */}
      {result && (
        <Card ref={resultCardRef}>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckCircle2 className="size-4 text-emerald-600" />
              Varaq Montaji Tayyor
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
                  <span>ZIP yuklab olish</span>
                </Button>
              </CardAction>
            )}
          </CardHeader>
          <CardContent className="space-y-4">
            <Alert>
              <CheckCircle2 className="text-emerald-600" />
              <AlertTitle className="tabular-nums">
                Qolip: {result.cols}×{result.rows} ({result.items_per_sheet}{" "}
                dona/list) | Aylantirish: {result.rotation}° | Jami:{" "}
                {result.calculated_sheets} list
              </AlertTitle>
            </Alert>

            <div className="flex flex-wrap gap-2">
              {result.output_files.map((f) => (
                <Button
                  key={f.filename}
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
              ))}
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
                      iframeClassName="h-[580px]"
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
