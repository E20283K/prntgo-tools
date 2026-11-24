import { useCallback, useEffect, useRef, useState } from "react"
import { FitAddon } from "@xterm/addon-fit"
import { WebLinksAddon } from "@xterm/addon-web-links"
import { Terminal } from "@xterm/xterm"
import "@xterm/xterm/css/xterm.css"
import {
  AtSign,
  BookOpen,
  ClipboardPaste,
  Cylinder,
  Download,
  Eye,
  FolderOpen,
  ImagePlus,
  LayoutGrid,
  Loader2,
  PenTool,
  RefreshCw,
  RotateCcw,
  Send,
  Sparkles,
  TerminalSquare,
  Trash2,
} from "lucide-react"
import { toast } from "sonner"

import { PdfPreview } from "@/components/PdfPreview"
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
import {
  apiFetch,
  terminalOutputFileUrl,
  type AiAssetItem,
  type AiDesignGenerateResponse,
  type AiSkillSummary,
  type AiTerminalOutputItem,
  type LabelHandoff,
  type PrintHandoff,
  type VectorCraftHandoff,
} from "@/lib/api"

interface ClaudeTerminalProps {
  active: boolean
  skills: AiSkillSummary[]
  assets: AiAssetItem[]
  onOpenInVectorCraft: (handoff: VectorCraftHandoff) => void
  onSendToLabelImp: (handoff: LabelHandoff) => void
  onSendToPrintImp: (handoff: PrintHandoff) => void
}

export function ClaudeTerminal({
  active,
  skills,
  assets,
  onOpenInVectorCraft,
  onSendToLabelImp,
  onSendToPrintImp,
}: ClaudeTerminalProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const termRef = useRef<Terminal | null>(null)
  const fitAddonRef = useRef<FitAddon | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  const [mode, setMode] = useState<"claude" | "bash">("claude")
  const [connected, setConnected] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [quickPrompt, setQuickPrompt] = useState("")
  const [outputs, setOutputs] = useState<AiTerminalOutputItem[]>([])
  const [outputsLoading, setOutputsLoading] = useState(false)
  const [previewPdfFile, setPreviewPdfFile] = useState<string | null>(null)
  const [promotingFile, setPromotingFile] = useState<string | null>(null)

  const sendToPty = useCallback((text: string) => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "input", data: text }))
      termRef.current?.focus()
    } else {
      toast.error("Terminal ulanmagan. Qayta ulanish tugmasini bosing.")
    }
  }, [])

  const loadOutputs = useCallback(async (sync = false) => {
    setOutputsLoading(true)
    try {
      const res = await apiFetch(
        `/api/ai-design/terminal/outputs?sync=${sync ? "true" : "false"}`
      )
      const data: { outputs: AiTerminalOutputItem[]; notes: string[] } =
        await res.json()
      setOutputs(data.outputs)
      if (sync && data.notes?.length) {
        toast.success(data.notes.join(" "))
      }
      const firstPdf = data.outputs.find((o) => o.ext === ".pdf")
      if (firstPdf) {
        setPreviewPdfFile((prev) => prev ?? firstPdf.filename)
      }
    } catch {
      // ignore background poll errors
    } finally {
      setOutputsLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadOutputs(false)
  }, [loadOutputs])

  // Initialize xterm.js and connect WebSocket
  const connectTerminal = useCallback(
    (targetMode: "claude" | "bash") => {
      if (!containerRef.current) return

      if (wsRef.current) {
        try {
          wsRef.current.close()
        } catch {
          // ignore
        }
        wsRef.current = null
      }

      if (!termRef.current) {
        const term = new Terminal({
          cursorBlink: true,
          fontFamily:
            "'JetBrains Mono', 'Cascadia Code', 'Fira Code', Consolas, monospace",
          fontSize: 13,
          lineHeight: 1.2,
          scrollback: 5000,
          theme: {
            background: "#090d16",
            foreground: "#e2e8f0",
            cursor: "#38bdf8",
            selectionBackground: "#334155",
            black: "#0f172a",
            red: "#f43f5e",
            green: "#10b981",
            yellow: "#f59e0b",
            blue: "#3b82f6",
            magenta: "#a855f7",
            cyan: "#06b6d4",
            white: "#f8fafc",
          },
        })
        const fitAddon = new FitAddon()
        term.loadAddon(fitAddon)
        term.loadAddon(new WebLinksAddon())
        term.open(containerRef.current)
        fitAddon.fit()

        term.onData((data) => {
          const ws = wsRef.current
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "input", data }))
          }
        })

        termRef.current = term
        fitAddonRef.current = fitAddon
      } else {
        termRef.current.clear()
        fitAddonRef.current?.fit()
      }

      const cols = termRef.current.cols || 120
      const rows = termRef.current.rows || 34
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:"
      const wsUrl = `${proto}//${window.location.host}/api/ai-design/terminal/ws?mode=${targetMode}&cols=${cols}&rows=${rows}`

      const ws = new WebSocket(wsUrl)
      ws.binaryType = "arraybuffer"

      ws.onopen = () => {
        setConnected(true)
        fitAddonRef.current?.fit()
        const c = termRef.current?.cols || 120
        const r = termRef.current?.rows || 34
        ws.send(JSON.stringify({ type: "resize", cols: c, rows: r }))
      }

      ws.onmessage = (ev) => {
        if (ev.data instanceof ArrayBuffer) {
          termRef.current?.write(new Uint8Array(ev.data))
        } else if (typeof ev.data === "string") {
          termRef.current?.write(ev.data)
        }
      }

      ws.onclose = () => {
        setConnected(false)
      }

      ws.onerror = () => {
        setConnected(false)
      }

      wsRef.current = ws
    },
    []
  )

  useEffect(() => {
    connectTerminal(mode)
    return () => {
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
      if (termRef.current) {
        termRef.current.dispose()
        termRef.current = null
      }
    }
  }, [connectTerminal, mode])

  // Re-fit when tab becomes active or window resizes
  useEffect(() => {
    if (!active) return
    const timer = setTimeout(() => {
      fitAddonRef.current?.fit()
      const ws = wsRef.current
      const term = termRef.current
      if (ws && ws.readyState === WebSocket.OPEN && term) {
        ws.send(
          JSON.stringify({
            type: "resize",
            cols: term.cols,
            rows: term.rows,
          })
        )
      }
    }, 80)

    const onResize = () => {
      fitAddonRef.current?.fit()
      const ws = wsRef.current
      const term = termRef.current
      if (ws && ws.readyState === WebSocket.OPEN && term) {
        ws.send(
          JSON.stringify({
            type: "resize",
            cols: term.cols,
            rows: term.rows,
          })
        )
      }
    }
    window.addEventListener("resize", onResize)
    return () => {
      clearTimeout(timer)
      window.removeEventListener("resize", onResize)
    }
  }, [active])

  async function handleRestartSession(newMode: "claude" | "bash") {
    try {
      const cols = termRef.current?.cols || 120
      const rows = termRef.current?.rows || 34
      await apiFetch("/api/ai-design/terminal/restart", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: newMode, cols, rows }),
      })
      setMode(newMode)
      connectTerminal(newMode)
      toast.success(
        newMode === "claude"
          ? "Yangi Claude Code terminal sessiyasi ochildi!"
          : "Bash shell ochildi!"
      )
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Qayta ishga tushirishda xato")
    }
  }

  async function handleUploadFileToTerminal(file: File) {
    setUploading(true)
    try {
      const fd = new FormData()
      fd.append("file", file)
      const res = await apiFetch("/api/ai-design/terminal/upload", {
        method: "POST",
        body: fd,
      })
      const data: { filename: string; mention: string } = await res.json()
      sendToPty(data.mention)
      toast.success(`Yuklandi va terminalga biriktirildi: ${data.mention}`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Fayl yuklashda xato")
    } finally {
      setUploading(false)
    }
  }

  async function handlePasteClipboardImage() {
    try {
      if (!navigator.clipboard?.read) {
        toast.info(
          "Brauzeringiz bevosita rasm o'qishni qo'llab-quvvatlamaydi. 'Fayl / Skrinshot biriktirish' tugmasidan foydalaning."
        )
        return
      }
      const items = await navigator.clipboard.read()
      for (const item of items) {
        const imgType = item.types.find((t) => t.startsWith("image/"))
        if (imgType) {
          const blob = await item.getType(imgType)
          const ext = imgType.split("/")[1] || "png"
          const file = new File([blob], `screenshot_${Date.now()}.${ext}`, {
            type: imgType,
          })
          await handleUploadFileToTerminal(file)
          return
        }
      }
      const text = await navigator.clipboard.readText()
      if (text) {
        sendToPty(text)
      } else {
        toast.info("Buferda rasm yoki matn topilmadi.")
      }
    } catch {
      toast.info(
        "Buferdan o'qish uchun ruxsat bering yoki 'Fayl / Skrinshot' tugmasi orqali tanlang."
      )
    }
  }

  async function handleDeleteOutput(filename: string) {
    try {
      const res = await apiFetch(
        `/api/ai-design/terminal/outputs/${encodeURIComponent(filename)}`,
        { method: "DELETE" }
      )
      const data: { outputs: AiTerminalOutputItem[] } = await res.json()
      setOutputs(data.outputs)
      if (previewPdfFile === filename) setPreviewPdfFile(null)
      toast.success(`O'chirildi: ${filename}`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "O'chirishda xato")
    }
  }

  async function handleSendOutputToMontaj(
    filename: string,
    target: "label-imp" | "print-imp"
  ) {
    setPromotingFile(filename)
    try {
      const res = await apiFetch(
        `/api/ai-design/terminal/outputs/${encodeURIComponent(filename)}/to-job`,
        { method: "POST" }
      )
      const job: AiDesignGenerateResponse = await res.json()
      if (!job.pdf_file) {
        throw new Error(
          "PDF fayl topilmadi. Avval 'PDF/VectorCraft Sinxronlash' tugmasini bosing."
        )
      }
      if (target === "label-imp") {
        onSendToLabelImp({
          job_id: job.job_id,
          filename: job.pdf_file,
          total_labels: 1,
          source_label: `Claude Terminal (${job.pdf_file})`,
        })
      } else {
        onSendToPrintImp({
          job_id: job.job_id,
          front_filenames: [job.pdf_file],
          source_label: `Claude Terminal (${job.pdf_file})`,
        })
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Montajga yuborishda xato")
    } finally {
      setPromotingFile(null)
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-12">
      {/* LEFT / MAIN: Live Interactive Claude Code Terminal */}
      <div className="min-w-0 space-y-3 lg:col-span-8">
        <Card className="overflow-hidden border-slate-800 bg-[#090d16] text-slate-100">
          {/* Terminal Top Control Bar */}
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 bg-slate-900/90 px-3 py-2">
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex items-center gap-1.5">
                <span
                  className={`size-2.5 rounded-full ${
                    connected ? "bg-emerald-400" : "bg-rose-500"
                  }`}
                />
                <span className="text-xs font-semibold">
                  {mode === "claude" ? "Claude Code TUI" : "Bash Terminal"}
                </span>
              </div>

              {/* Mode Switcher */}
              <div className="flex rounded-md border border-slate-700 bg-slate-950 p-0.5">
                <button
                  type="button"
                  onClick={() => void handleRestartSession("claude")}
                  className={`rounded px-2 py-0.5 text-xs font-medium transition-colors ${
                    mode === "claude"
                      ? "bg-primary text-primary-foreground"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  Claude TUI
                </button>
                <button
                  type="button"
                  onClick={() => void handleRestartSession("bash")}
                  className={`rounded px-2 py-0.5 text-xs font-medium transition-colors ${
                    mode === "bash"
                      ? "bg-primary text-primary-foreground"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  Bash Shell
                </button>
              </div>

              {/* Quick Slash Commands for Claude Code */}
              <div className="flex flex-wrap items-center gap-1">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-6 border-slate-700 bg-slate-800/80 px-2 font-mono text-[11px] text-slate-200 hover:bg-slate-700"
                  onClick={() => sendToPty("/login\r")}
                  title="Claude obunasiga kirish"
                >
                  /login
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-6 border-slate-700 bg-slate-800/80 px-2 font-mono text-[11px] text-slate-200 hover:bg-slate-700"
                  onClick={() => sendToPty("/mcp\r")}
                  title="VectorCraft MCP holatini ko'rish"
                >
                  /mcp
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-6 border-slate-700 bg-slate-800/80 px-2 font-mono text-[11px] text-slate-200 hover:bg-slate-700"
                  onClick={() => sendToPty("/clear\r")}
                  title="Yangi chat boshlash"
                >
                  /clear
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-6 border-slate-700 bg-slate-800/80 px-2 font-mono text-[11px] text-slate-200 hover:bg-slate-700"
                  onClick={() => sendToPty("/resume\r")}
                  title="Oldingi suhbatni davom ettirish"
                >
                  /resume
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-6 border-slate-700 bg-slate-800/80 px-2 font-mono text-[11px] text-amber-300 hover:bg-slate-700"
                  onClick={() => sendToPty("\x1b")}
                  title="Esc yuborish"
                >
                  Esc
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-6 border-slate-700 bg-slate-800/80 px-2 font-mono text-[11px] text-rose-300 hover:bg-slate-700"
                  onClick={() => sendToPty("\x03")}
                  title="Ctrl+C yuborish"
                >
                  Ctrl+C
                </Button>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-1.5">
              {/* Upload File / Screenshot into @uploads/ */}
              <label className="cursor-pointer">
                <input
                  type="file"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0]
                    if (f) void handleUploadFileToTerminal(f)
                    e.target.value = ""
                  }}
                />
                <span className="inline-flex h-7 items-center gap-1 rounded-md border border-slate-700 bg-slate-800 px-2.5 text-xs font-medium text-slate-100 hover:bg-slate-700">
                  {uploading ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <ImagePlus className="size-3.5 text-sky-400" />
                  )}
                  Fayl / Skrinshot (@)
                </span>
              </label>

              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 gap-1 border-slate-700 bg-slate-800 px-2 text-xs text-slate-100 hover:bg-slate-700"
                onClick={() => void handlePasteClipboardImage()}
                title="Buferdagi skrinshot yoki matnni terminalga qo'yish"
              >
                <ClipboardPaste className="size-3.5 text-emerald-400" />
                Buferdan Qo'yish
              </Button>

              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 gap-1 border-slate-700 bg-slate-800 px-2 text-xs text-slate-100 hover:bg-slate-700"
                onClick={() => void handleRestartSession(mode)}
                title="Terminalni yangidan ishga tushirish"
              >
                <RotateCcw className="size-3.5" />
                Restart
              </Button>
            </div>
          </div>

          {/* 1-Click @Mention Bar for Skills & Server Assets */}
          <div className="flex flex-wrap items-center gap-1.5 border-b border-slate-800/80 bg-slate-900/50 px-3 py-1.5 text-xs">
            <span className="flex items-center gap-1 text-[11px] text-slate-400">
              <AtSign className="size-3 text-sky-400" />
              Tez biriktirish:
            </span>

            {skills.map((sk) => (
              <button
                key={sk.slug}
                type="button"
                onClick={() =>
                  sendToPty(`@.claude/skills/${sk.slug}/SKILL.md `)
                }
                className="inline-flex items-center gap-1 rounded border border-indigo-500/30 bg-indigo-500/10 px-2 py-0.5 font-mono text-[11px] text-indigo-300 hover:bg-indigo-500/20"
                title={`Skillni chatga biriktirish: @.claude/skills/${sk.slug}/SKILL.md`}
              >
                <BookOpen className="size-2.5" />@{sk.slug}
              </button>
            ))}

            {assets.slice(0, 8).map((as) => (
              <button
                key={as.name}
                type="button"
                onClick={() => sendToPty(`@assets/${as.name} `)}
                className="inline-flex items-center gap-1 rounded border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 font-mono text-[11px] text-emerald-300 hover:bg-emerald-500/20"
                title={`Server faylini chatga biriktirish: @assets/${as.name}`}
              >
                <FolderOpen className="size-2.5" />
                @assets/{as.name}
              </button>
            ))}
          </div>

          {/* Xterm.js Canvas */}
          <div
            ref={containerRef}
            className="h-[540px] w-full px-2 py-1.5"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault()
              const f = e.dataTransfer.files?.[0]
              if (f) void handleUploadFileToTerminal(f)
            }}
          />

          {/* Quick Prompt Bar (for pasting multi-line Uzbek prompts cleanly) */}
          <div className="flex items-center gap-2 border-t border-slate-800 bg-slate-900/90 px-3 py-2">
            <TerminalSquare className="size-4 shrink-0 text-slate-400" />
            <Input
              value={quickPrompt}
              onChange={(e) => setQuickPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && quickPrompt.trim()) {
                  e.preventDefault()
                  sendToPty(quickPrompt + "\r")
                  setQuickPrompt("")
                }
              }}
              placeholder="Terminalga matn yoki buyruq yuborish (yoki to'g'ridan-to'g'ri yuqoridagi qora terminal ichiga yozing, faylni Drag & Drop qiling)..."
              className="h-8 border-slate-700 bg-slate-950 text-xs text-slate-100 placeholder:text-slate-500"
            />
            <Button
              size="sm"
              className="h-8 gap-1 px-3 text-xs"
              onClick={() => {
                if (!quickPrompt.trim()) return
                sendToPty(quickPrompt + "\r")
                setQuickPrompt("")
              }}
            >
              <Send className="size-3.5" />
              Yuborish
            </Button>
          </div>
        </Card>
      </div>

      {/* RIGHT: Live Workspace Outputs (`outputs/*.vectorcraft` & `*.pdf`) */}
      <div className="min-w-0 space-y-4 lg:col-span-4">
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between gap-2">
              <div>
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Sparkles className="size-4 text-primary" />
                  Terminalda Yaratilgan Fayllar (<code>outputs/</code>)
                </CardTitle>
                <CardDescription className="text-xs">
                  Claude Code <code>outputs/</code> papkasiga saqlagan{" "}
                  <code>.vectorcraft</code> va <code>.pdf</code> fayllar.
                </CardDescription>
              </div>

              <Button
                variant="outline"
                size="sm"
                className="h-7 gap-1 px-2 text-xs"
                onClick={() => void loadOutputs(true)}
                disabled={outputsLoading}
                title="Ro'yxatni yangilash va .vectorcraft <-> .pdf juftligini avtomatik yaratish"
              >
                <RefreshCw
                  className={`size-3.5 ${outputsLoading ? "animate-spin" : ""}`}
                />
                Sinxronlash
              </Button>
            </div>
          </CardHeader>

          <CardContent className="space-y-2.5">
            {outputs.length === 0 ? (
              <div className="rounded-lg border border-dashed p-5 text-center text-xs text-muted-foreground">
                Hozircha <code>outputs/</code> papkasida fayl yo'q. Terminalda
                Claude'ga:{" "}
                <span className="font-mono text-foreground">
                  "outputs/etiketka.vectorcraft va outputs/etiketka.pdf qilib
                  dizayn yarat"
                </span>{" "}
                deb yozing va <strong>Sinxronlash</strong> tugmasini bosing.
              </div>
            ) : (
              <div className="max-h-[280px] space-y-2 overflow-y-auto pr-1">
                {outputs.map((item) => (
                  <div
                    key={item.filename}
                    className="space-y-2 rounded-lg border bg-muted/20 p-2.5"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <div
                          className="truncate font-mono text-xs font-semibold"
                          title={item.filename}
                        >
                          {item.filename}
                        </div>
                        <div className="text-[11px] text-muted-foreground">
                          {item.size_kb} KB • {item.ext}
                        </div>
                      </div>

                      <div className="flex items-center gap-1">
                        <Button
                          size="sm"
                          variant={
                            item.ext === ".vectorcraft" ? "default" : "secondary"
                          }
                          className="h-7 gap-1 px-2 text-xs"
                          nativeButton={false}
                          render={
                            <a
                              href={terminalOutputFileUrl(item.filename)}
                              download={item.filename}
                            />
                          }
                        >
                          <Download className="size-3" />
                          Yuklash
                        </Button>

                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 w-7 p-0 text-destructive"
                          onClick={() => void handleDeleteOutput(item.filename)}
                        >
                          <Trash2 className="size-3.5" />
                        </Button>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-1.5">
                      {[".vectorcraft", ".svg", ".pdf"].includes(item.ext) && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-6 gap-1 px-2 text-[11px]"
                          onClick={() =>
                            onOpenInVectorCraft({
                              filename: item.filename,
                              downloadUrl: terminalOutputFileUrl(item.filename),
                              sourceLabel: "Claude Terminal",
                            })
                          }
                        >
                          <PenTool className="size-3" />
                          VectorCraft Web'da
                        </Button>
                      )}

                      {item.ext === ".pdf" && (
                        <>
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-6 gap-1 px-2 text-[11px]"
                            onClick={() => setPreviewPdfFile(item.filename)}
                          >
                            <Eye className="size-3" />
                            Ko'rish
                          </Button>

                          <Button
                            size="sm"
                            variant="outline"
                            className="h-6 gap-1 px-2 text-[11px]"
                            disabled={promotingFile === item.filename}
                            onClick={() =>
                              void handleSendOutputToMontaj(
                                item.filename,
                                "label-imp"
                              )
                            }
                          >
                            <Cylinder className="size-3" />
                            Val Montaji
                          </Button>

                          <Button
                            size="sm"
                            variant="outline"
                            className="h-6 gap-1 px-2 text-[11px]"
                            disabled={promotingFile === item.filename}
                            onClick={() =>
                              void handleSendOutputToMontaj(
                                item.filename,
                                "print-imp"
                              )
                            }
                          >
                            <LayoutGrid className="size-3" />
                            Varaq Montaji
                          </Button>
                        </>
                      )}

                      <Badge
                        variant="outline"
                        className="cursor-pointer font-mono text-[10px]"
                        onClick={() => sendToPty(`@outputs/${item.filename} `)}
                        title="Terminalga @outputs/... sifatida biriktirish"
                      >
                        @mention
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Live PDF Preview for selected output */}
        {previewPdfFile && (
          <PdfPreview
            src={terminalOutputFileUrl(previewPdfFile, true)}
            title={previewPdfFile}
            downloadUrl={terminalOutputFileUrl(previewPdfFile)}
            downloadFilename={previewPdfFile}
            iframeClassName="h-[320px]"
          />
        )}
      </div>
    </div>
  )
}
