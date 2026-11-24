import { useCallback, useEffect, useRef, useState } from "react"
import {
  Cylinder,
  Download,
  FileText,
  LayoutGrid,
  Loader2,
  Maximize2,
  PenTool,
  RefreshCw,
  Save,
  Upload,
} from "lucide-react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  apiFetch,
  jobFileUrl,
  type AiDesignGenerateResponse,
  type AiDesignStatusResponse,
  type LabelHandoff,
  type PrintHandoff,
  type VectorCraftHandoff,
} from "@/lib/api"

interface VectorCraftWindowApi {
  openFile: (name: string, bytes: Uint8Array) => boolean
  execute: (
    command: string,
    params?: Record<string, unknown>
  ) => Promise<Record<string, unknown>>
  screenshot?: () => Promise<{ data?: string }>
}

interface VectorCraftTabProps {
  ready: boolean
  active: boolean
  handoff: VectorCraftHandoff | null
  onClearHandoff: () => void
  onSendToLabelImp: (handoff: LabelHandoff) => void
  onSendToPrintImp: (handoff: PrintHandoff) => void
}

function base64ToUint8Array(b64: string): Uint8Array {
  const bin = window.atob(b64)
  const arr = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) {
    arr[i] = bin.charCodeAt(i)
  }
  return arr
}

export function VectorCraftTab({
  ready,
  active,
  handoff,
  onClearHandoff,
  onSendToLabelImp,
  onSendToPrintImp,
}: VectorCraftTabProps) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null)
  const [webInstalled, setWebInstalled] = useState<boolean | null>(null)
  const [installingWeb, setInstallingWeb] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [activeDocName, setActiveDocName] = useState<string>("design.vectorcraft")
  const [exportedJob, setExportedJob] =
    useState<AiDesignGenerateResponse | null>(null)

  const checkWebStatus = useCallback(async () => {
    if (!ready) return
    try {
      const res = await apiFetch("/api/ai-design/status")
      const data: AiDesignStatusResponse = await res.json()
      setWebInstalled(data.vectorcraft_web.installed)
    } catch {
      setWebInstalled(false)
    }
  }, [ready])

  useEffect(() => {
    void checkWebStatus()
  }, [checkWebStatus])

  const getVectorCraftApi = useCallback((): VectorCraftWindowApi | null => {
    try {
      const win = iframeRef.current?.contentWindow as
        | (Window & { vectorcraft?: VectorCraftWindowApi })
        | null
      return win?.vectorcraft ?? null
    } catch {
      return null
    }
  }, [])

  const waitForVectorCraftApi = useCallback(
    async (timeoutMs = 15000): Promise<VectorCraftWindowApi | null> => {
      const deadline = Date.now() + timeoutMs
      while (Date.now() < deadline) {
        const api = getVectorCraftApi()
        if (api && typeof api.openFile === "function") {
          return api
        }
        await new Promise((r) => setTimeout(r, 250))
      }
      return null
    },
    [getVectorCraftApi]
  )

  // Automatically load handoff file into VectorCraft Web canvas when received
  useEffect(() => {
    if (!handoff || !webInstalled) return
    const currentHandoff = handoff

    async function openHandoffInCanvas() {
      try {
        const res = await apiFetch(currentHandoff.downloadUrl)
        const buf = await res.arrayBuffer()
        const bytes = new Uint8Array(buf)
        const api = await waitForVectorCraftApi(18000)
        if (!api) {
          toast.error(
            "VectorCraft Web yuklanishini kuting va qayta urinib ko'ring."
          )
          return
        }
        api.openFile(currentHandoff.filename, bytes)
        setActiveDocName(currentHandoff.filename)
        toast.success(
          `'${currentHandoff.filename}' VectorCraft muharririda ochildi!`
        )
        onClearHandoff()
      } catch (err) {
        toast.error(
          err instanceof Error
            ? err.message
            : "Faylni VectorCraft'da ochishda xato"
        )
      }
    }

    void openHandoffInCanvas()
  }, [handoff, webInstalled, waitForVectorCraftApi, onClearHandoff])

  async function handleInstallVectorCraftWeb() {
    setInstallingWeb(true)
    try {
      const res = await apiFetch("/api/ai-design/install-vectorcraft-web", {
        method: "POST",
      })
      const data: AiDesignStatusResponse = await res.json()
      setWebInstalled(data.vectorcraft_web.installed)
      toast.success("VectorCraft Web (WASM) serverga muvaffaqiyatli o'rnatildi!")
    } catch (err) {
      toast.error(
        err instanceof Error
          ? err.message
          : "VectorCraft Web yuklab olishda xato"
      )
    } finally {
      setInstallingWeb(false)
    }
  }

  async function handleOpenLocalFile(file: File) {
    try {
      const buf = await file.arrayBuffer()
      const api = await waitForVectorCraftApi(5000)
      if (!api) {
        toast.error("VectorCraft Web hali to'liq yuklanmagan.")
        return
      }
      api.openFile(file.name, new Uint8Array(buf))
      setActiveDocName(file.name)
      toast.success(`'${file.name}' muharrirga yuklandi!`)
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Faylni ochishda xatolik"
      )
    }
  }

  async function handleExportFromCanvas(saveToAssets = false) {
    setExporting(true)
    try {
      const api = await waitForVectorCraftApi(5000)
      if (!api) {
        throw new Error("VectorCraft Web oynasi bilan aloqa topilmadi.")
      }

      const stem =
        activeDocName.replace(/\.[^.]+$/, "").trim() || "vectorcraft_design"

      // Export native .vectorcraft bytes from the live WASM canvas
      const vcExport = (await api.execute("document.export", {
        format: "vectorcraft",
      })) as { dataBase64?: string }

      if (!vcExport?.dataBase64) {
        throw new Error(
          "VectorCraft hujjatini eksport qilib bo'lmadi (ochiq hujjat borligini tekshiring)."
        )
      }

      const vcBytes = base64ToUint8Array(vcExport.dataBase64)
      const vcBlob = new Blob([vcBytes.buffer as ArrayBuffer], {
        type: "application/octet-stream",
      })

      const fd = new FormData()
      fd.append("file", vcBlob, `${stem}.vectorcraft`)
      fd.append("save_to_assets", saveToAssets ? "true" : "false")

      const res = await apiFetch("/api/ai-design/editor-export", {
        method: "POST",
        body: fd,
      })
      const jobData: AiDesignGenerateResponse = await res.json()

      // If server didn't have vectorcraft-cli (e.g. local dev without Docker), also export PDF directly from WASM!
      if (!jobData.pdf_file) {
        try {
          const pdfExport = (await api.execute("document.export", {
            format: "pdf",
          })) as { dataBase64?: string }
          if (pdfExport?.dataBase64) {
            const pdfBytes = base64ToUint8Array(pdfExport.dataBase64)
            const pdfBlob = new Blob([pdfBytes.buffer as ArrayBuffer], {
              type: "application/pdf",
            })
            const fdPdf = new FormData()
            fdPdf.append("file", pdfBlob, `${stem}.pdf`)
            fdPdf.append("save_to_assets", "false")
            const resPdf = await apiFetch("/api/ai-design/editor-export", {
              method: "POST",
              body: fdPdf,
            })
            const pdfJobData: AiDesignGenerateResponse = await resPdf.json()
            setExportedJob({
              ...jobData,
              pdf_file: pdfJobData.pdf_file,
            })
          } else {
            setExportedJob(jobData)
          }
        } catch {
          setExportedJob(jobData)
        }
      } else {
        setExportedJob(jobData)
      }

      toast.success(
        saveToAssets
          ? "Dizayn .vectorcraft + .pdf qilib olindi va Server Assets'ga saqlandi!"
          : "Dizayn .vectorcraft va .pdf formatlarida tayyorlandi!"
      )
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Eksport qilishda xatolik"
      )
    } finally {
      setExporting(false)
    }
  }

  if (webInstalled === false) {
    return (
      <Card className="mx-auto max-w-2xl">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <PenTool className="size-5 text-primary" />
            VectorCraft Web (WebAssembly) Muharriri
          </CardTitle>
          <CardDescription>
            Docker konteynerda VectorCraft Web avtomatik o'rnatiladi. Agar lokal
            muhitda ishlayotgan bo'lsangiz, quyidagi tugma orqali rasmiy{" "}
            <code>vectorcraft-web-0.24.1.zip</code> paketini serverga bir
            bosishda o'rnatishingiz mumkin.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex items-center gap-3">
          <Button
            onClick={() => void handleInstallVectorCraftWeb()}
            disabled={installingWeb}
            className="gap-2"
          >
            {installingWeb ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                GitHub'dan yuklab olinmoqda (~38 MB)...
              </>
            ) : (
              <>
                <Download className="size-4" />
                VectorCraft Web'ni Serverga O'rnatish
              </>
            )}
          </Button>
          <Button
            variant="outline"
            onClick={() => void checkWebStatus()}
            disabled={installingWeb}
          >
            <RefreshCw className="mr-1.5 size-4" />
            Tekshirish
          </Button>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Top Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border bg-card px-3.5 py-2.5 shadow-2xs">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="default" className="gap-1.5">
            <PenTool className="size-3.5" />
            VectorCraft Web Studio
          </Badge>
          <span className="font-mono text-xs text-muted-foreground">
            {activeDocName}
          </span>

          <label className="cursor-pointer">
            <input
              type="file"
              accept=".vectorcraft,.svg,.pdf,.ai,.eps,.png,.jpg"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) void handleOpenLocalFile(f)
              }}
            />
            <span className="inline-flex h-8 items-center gap-1.5 rounded-md border bg-background px-2.5 text-xs font-medium hover:bg-muted">
              <Upload className="size-3.5" />
              Kompyuterdan Fayl Ochish
            </span>
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="default"
            className="h-8 gap-1.5 text-xs"
            onClick={() => void handleExportFromCanvas(false)}
            disabled={exporting}
          >
            {exporting ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Download className="size-3.5" />
            )}
            .vectorcraft + .pdf qilib olish
          </Button>

          <Button
            size="sm"
            variant="outline"
            className="h-8 gap-1.5 text-xs"
            onClick={() => void handleExportFromCanvas(true)}
            disabled={exporting}
          >
            <Save className="size-3.5" />
            Server Assets'ga Saqlash
          </Button>

          <Button
            size="sm"
            variant="ghost"
            className="h-8 gap-1 px-2 text-xs"
            nativeButton={false}
            render={
              <a
                href="/vectorcraft/"
                target="_blank"
                rel="noopener noreferrer"
              />
            }
          >
            <Maximize2 className="size-3.5" />
            To'liq ekran
          </Button>
        </div>
      </div>

      {/* Exported Files Action Strip */}
      {exportedJob && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-primary/30 bg-primary/5 px-3.5 py-2.5 text-xs">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold">Tayyor eksport:</span>
            {exportedJob.vectorcraft_file && (
              <Button
                size="sm"
                className="h-7 gap-1 px-2.5 text-xs"
                nativeButton={false}
                render={
                  <a
                    href={jobFileUrl(
                      exportedJob.job_id,
                      exportedJob.vectorcraft_file
                    )}
                    download={exportedJob.vectorcraft_file}
                  />
                }
              >
                <Download className="size-3" />
                {exportedJob.vectorcraft_file} (.vectorcraft)
              </Button>
            )}
            {exportedJob.pdf_file && (
              <Button
                size="sm"
                variant="secondary"
                className="h-7 gap-1 px-2.5 text-xs"
                nativeButton={false}
                render={
                  <a
                    href={jobFileUrl(exportedJob.job_id, exportedJob.pdf_file)}
                    download={exportedJob.pdf_file}
                  />
                }
              >
                <FileText className="size-3" />
                {exportedJob.pdf_file} (.pdf)
              </Button>
            )}
          </div>

          {exportedJob.pdf_file && (
            <div className="flex items-center gap-1.5">
              <Button
                size="sm"
                variant="outline"
                className="h-7 gap-1 px-2.5 text-xs"
                onClick={() =>
                  onSendToLabelImp({
                    job_id: exportedJob.job_id,
                    filename: exportedJob.pdf_file!,
                    total_labels: 1,
                    source_label: `VectorCraft Editor (${exportedJob.pdf_file})`,
                  })
                }
              >
                <Cylinder className="size-3" />
                Val Montajiga
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="h-7 gap-1 px-2.5 text-xs"
                onClick={() =>
                  onSendToPrintImp({
                    job_id: exportedJob.job_id,
                    front_filenames: [exportedJob.pdf_file!],
                    source_label: `VectorCraft Editor (${exportedJob.pdf_file})`,
                  })
                }
              >
                <LayoutGrid className="size-3" />
                Varaq Montajiga
              </Button>
            </div>
          )}
        </div>
      )}

      {/* Embedded VectorCraft WASM Application */}
      <div className="overflow-hidden rounded-xl border bg-black shadow-sm">
        {(active || webInstalled) && (
          <iframe
            ref={iframeRef}
            src="/vectorcraft/"
            title="VectorCraft Web Editor"
            className="h-[calc(100vh-170px)] min-h-[640px] w-full border-0"
            allow="fullscreen; clipboard-read; clipboard-write"
            allowFullScreen
          />
        )}
      </div>
    </div>
  )
}
