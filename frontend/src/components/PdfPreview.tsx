import { Download, ExternalLink, FileText } from "lucide-react"

import { Button } from "@/components/ui/button"
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
  const viewerSrc = src.includes("#")
    ? src
    : showToolbar
      ? `${src}#toolbar=1&navpanes=0&view=FitH`
      : `${src}#toolbar=0&navpanes=0&scrollbar=0&view=Fit`

  return (
    <div
      className={cn(
        "flex flex-col overflow-hidden rounded-lg border bg-background shadow-xs",
        className
      )}
    >
      {showHeader && (
        <div className="flex items-center justify-between gap-2 border-b bg-muted/40 px-3 py-2">
          <div className="flex min-w-0 items-center gap-2 text-xs font-medium text-foreground">
            <FileText className="size-3.5 shrink-0 text-muted-foreground" />
            <span className="truncate font-mono" title={title}>
              {title}
            </span>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs"
              nativeButton={false}
              render={
                <a href={src} target="_blank" rel="noopener noreferrer" />
              }
            >
              <ExternalLink className="size-3.5" />
              <span className="hidden sm:inline">Yangi oynada</span>
            </Button>
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

      <iframe
        src={viewerSrc}
        title={title}
        className={cn(
          "w-full border-0 bg-white",
          !interactive && "pointer-events-none",
          iframeClassName ?? "h-[520px]"
        )}
      />
    </div>
  )
}
