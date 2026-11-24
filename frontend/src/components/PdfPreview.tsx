import { useEffect, useRef, useState } from "react"
import {
  ChevronLeft,
  ChevronRight,
  Download,
  ExternalLink,
  FileText,
  Image as ImageIcon,
  Loader2,
  ZoomIn,
  ZoomOut,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { apiFetch } from "@/lib/api"
import { cn } from "@/lib/utils"

interface PdfPreviewProps {
  src: string
  title?: string
  downloadUrl?: string
  downloadFilename?: string
  showToolbar?: boolean
  showHeader?: boolean
  interactive?: boolean
  className?: string
  iframeClassName?: string
}

function buildServerPngUrl(rawSrc: string, page: number, dpi: number): string {
  const base = rawSrc.split("#")[0]
  const sep = base.includes("?") ? "&" : "?"
  return `${base}${sep}format=png&page=${page}&dpi=${dpi}`
}

export function PdfPreview({
  src,
  title = "PDF Preview",
  downloadUrl,
  downloadFilename,
  showToolbar = true,
  showHeader = true,
  interactive = true,
  className,
  iframeClassName,
}: PdfPreviewProps) {
  // Default to server-rendered PNG mode so Telegram Mini App (Android/iOS/Desktop WebView)
  // and all mobile/desktop browsers always display crisp vector previews reliably.
  const [viewMode, setViewMode] = useState<"image" | "iframe">("image")
  const [pageIndex, setPageIndex] = useState(0)
  const [pageCount, setPageCount] = useState(1)
  const [zoomPct, setZoomPct] = useState(100)
  const [imgUrl, setImgUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const imgUrlRef = useRef<string | null>(null)

  const cleanSrc = src.split("#")[0]

  // Reset page index when `src` changes
  useEffect(() => {
    setPageIndex(0)
  }, [cleanSrc])

  // Render current PDF page to PNG via FastAPI PyMuPDF
  useEffect(() => {
    if (viewMode !== "image" || !cleanSrc) return

    let cancelled = false
    const controller = new AbortController()

    async function loadPageImage() {
      setLoading(true)
      setError(null)
      try {
        let res: Response
        if (cleanSrc.startsWith("blob:")) {
          const blobRes = await fetch(cleanSrc, { signal: controller.signal })
          const pdfBlob = await blobRes.blob()
          const fd = new FormData()
          fd.append("file", pdfBlob, "preview.pdf")
          res = await apiFetch(
            `/api/pdf/render-page?page=${pageIndex}&dpi=180`,
            {
              method: "POST",
              body: fd,
              signal: controller.signal,
            }
          )
        } else {
          const pngEndpoint = buildServerPngUrl(cleanSrc, pageIndex, 180)
          res = await apiFetch(pngEndpoint, { signal: controller.signal })
        }

        if (cancelled) return
        const totalHeader = parseInt(
          res.headers.get("X-Page-Count") || "1",
          10
        )
        const pngBlob = await res.blob()
        if (cancelled) return

        const nextObjUrl = URL.createObjectURL(pngBlob)
        if (imgUrlRef.current) {
          URL.revokeObjectURL(imgUrlRef.current)
        }
        imgUrlRef.current = nextObjUrl
        setImgUrl(nextObjUrl)
        setPageCount(
          Number.isFinite(totalHeader) && totalHeader > 0 ? totalHeader : 1
        )
      } catch (err) {
        if (cancelled) return
        if (err instanceof DOMException && err.name === "AbortError") return
        setError(
          err instanceof Error ? err.message : "PDF ko'rinishni yuklashda xato"
        )
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void loadPageImage()

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [cleanSrc, pageIndex, viewMode])

  useEffect(() => {
    return () => {
      if (imgUrlRef.current) {
        URL.revokeObjectURL(imgUrlRef.current)
        imgUrlRef.current = null
      }
    }
  }, [])

  const viewerSrc = src.includes("#")
    ? src
    : showToolbar
      ? `${src}#toolbar=1&navpanes=0&view=FitH`
      : `${src}#toolbar=0&navpanes=0&scrollbar=0&view=Fit`

  const openHref = downloadUrl || cleanSrc

  return (
    <div
      className={cn(
        "flex flex-col overflow-hidden rounded-lg border bg-background shadow-xs",
        className
      )}
    >
      {showHeader && (
        <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-muted/40 px-3 py-2">
          <div className="flex min-w-0 items-center gap-2 text-xs font-medium text-foreground">
            <FileText className="size-3.5 shrink-0 text-muted-foreground" />
            <span className="truncate font-mono" title={title}>
              {title}
            </span>
          </div>

          <div className="flex flex-wrap shrink-0 items-center gap-1">
            {viewMode === "image" && pageCount > 1 && (
              <div className="mr-1 flex items-center gap-0.5 rounded-md border bg-background px-1 py-0.5 text-xs">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-6 w-6 p-0"
                  disabled={pageIndex <= 0 || loading}
                  onClick={() => setPageIndex((p) => Math.max(0, p - 1))}
                >
                  <ChevronLeft className="size-3.5" />
                </Button>
                <span className="px-1.5 font-mono text-[11px]">
                  {pageIndex + 1}/{pageCount}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-6 w-6 p-0"
                  disabled={pageIndex >= pageCount - 1 || loading}
                  onClick={() =>
                    setPageIndex((p) => Math.min(pageCount - 1, p + 1))
                  }
                >
                  <ChevronRight className="size-3.5" />
                </Button>
              </div>
            )}

            {viewMode === "image" && (
              <div className="mr-1 flex items-center gap-0.5 rounded-md border bg-background px-1 py-0.5 text-xs">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-6 w-6 p-0"
                  onClick={() => setZoomPct((z) => Math.max(50, z - 25))}
                  title="Kichraytirish"
                >
                  <ZoomOut className="size-3.5" />
                </Button>
                <button
                  type="button"
                  onClick={() => setZoomPct(100)}
                  className="px-1 font-mono text-[11px] hover:underline"
                  title="100% ga qaytarish"
                >
                  {zoomPct}%
                </button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-6 w-6 p-0"
                  onClick={() => setZoomPct((z) => Math.min(300, z + 25))}
                  title="Kattalashtirish"
                >
                  <ZoomIn className="size-3.5" />
                </Button>
              </div>
            )}

            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 gap-1 px-2 text-xs"
              onClick={() =>
                setViewMode((m) => (m === "image" ? "iframe" : "image"))
              }
              title="Ko'rish rejimini almashtirish (Rasm / Brauzer PDF)"
            >
              <ImageIcon className="size-3.5" />
              <span className="hidden sm:inline">
                {viewMode === "image" ? "PDF rejim" : "Rasm rejim"}
              </span>
            </Button>

            {!openHref.startsWith("blob:") && (
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-xs"
                nativeButton={false}
                render={
                  <a
                    href={openHref}
                    target="_blank"
                    rel="noopener noreferrer"
                  />
                }
              >
                <ExternalLink className="size-3.5" />
                <span className="hidden sm:inline">Yangi oynada</span>
              </Button>
            )}

            {downloadUrl && (
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-xs"
                nativeButton={false}
                render={
                  <a
                    href={downloadUrl}
                    download={downloadFilename || title}
                  />
                }
              >
                <Download className="size-3.5" />
                <span className="hidden sm:inline">Yuklab olish</span>
              </Button>
            )}
          </div>
        </div>
      )}

      {viewMode === "iframe" ? (
        <iframe
          src={viewerSrc}
          title={title}
          className={cn(
            "w-full border-0 bg-white",
            !interactive && "pointer-events-none",
            iframeClassName ?? "h-[520px]"
          )}
        />
      ) : (
        <div
          className={cn(
            "relative flex w-full items-center justify-center overflow-auto bg-neutral-100/80 p-3 dark:bg-neutral-900/60",
            !interactive && "pointer-events-none",
            iframeClassName ?? "h-[520px]"
          )}
        >
          {loading && (
            <div className="absolute top-2.5 right-2.5 z-10 flex items-center gap-1.5 rounded-md border bg-background/90 px-2 py-1 text-xs text-muted-foreground shadow-2xs backdrop-blur-xs">
              <Loader2 className="size-3.5 animate-spin" />
              <span>Yuklanmoqda...</span>
            </div>
          )}

          {error ? (
            <div className="p-4 text-center text-xs text-destructive">
              {error}
            </div>
          ) : imgUrl ? (
            <img
              src={imgUrl}
              alt={title}
              style={
                zoomPct === 100
                  ? undefined
                  : {
                      width: `${zoomPct}%`,
                      maxWidth: "none",
                      maxHeight: "none",
                    }
              }
              className={cn(
                "rounded bg-white shadow-sm transition-all",
                zoomPct === 100 && "max-h-full max-w-full object-contain"
              )}
            />
          ) : null}

          {!showHeader && pageCount > 1 && (
            <div className="absolute bottom-2 left-1/2 z-10 flex -translate-x-1/2 items-center gap-1 rounded-full border bg-background/90 px-2 py-0.5 text-xs shadow-sm backdrop-blur-xs">
              <button
                type="button"
                disabled={pageIndex <= 0}
                onClick={() => setPageIndex((p) => Math.max(0, p - 1))}
                className="px-1 disabled:opacity-40"
              >
                ‹
              </button>
              <span className="font-mono text-[11px]">
                {pageIndex + 1}/{pageCount}
              </span>
              <button
                type="button"
                disabled={pageIndex >= pageCount - 1}
                onClick={() =>
                  setPageIndex((p) => Math.min(pageCount - 1, p + 1))
                }
                className="px-1 disabled:opacity-40"
              >
                ›
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
