import { useEffect, useState } from "react"
import { Download, FileCode2, HelpCircle, Layers } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { jobCdrBundleUrl, standaloneCdrConverterUrl } from "@/lib/api"

export interface CorelVersionChoice {
  version: number
  label: string
  short: string
}

export const COREL_VERSION_CHOICES: CorelVersionChoice[] = [
  { version: 18, label: "CorelDRAW X8 (v18) — Standart", short: "v18 (X8)" },
  { version: 17, label: "CorelDRAW X7 (v17)", short: "v17 (X7)" },
  { version: 16, label: "CorelDRAW X6 (v16)", short: "v16 (X6)" },
  { version: 15, label: "CorelDRAW X5 (v15)", short: "v15 (X5)" },
  { version: 14, label: "CorelDRAW X4 (v14)", short: "v14 (X4)" },
  { version: 19, label: "CorelDRAW 2017 (v19)", short: "v19 (2017)" },
  { version: 20, label: "CorelDRAW 2018 (v20)", short: "v20 (2018)" },
  { version: 21, label: "CorelDRAW 2019 (v21)", short: "v21 (2019)" },
  { version: 22, label: "CorelDRAW 2020 (v22)", short: "v22 (2020)" },
  { version: 23, label: "CorelDRAW 2021 (v23)", short: "v23 (2021)" },
  { version: 24, label: "CorelDRAW 2022/2023 (v24)", short: "v24 (2022/23)" },
  { version: 25, label: "CorelDRAW 2024 (v25)", short: "v25 (2024)" },
]

const STORAGE_VER_KEY = "printhub_corel_version"
const STORAGE_ASK_KEY = "printhub_corel_ask_version"

export function useCorelSettings() {
  const [version, setVersion] = useState<number>(() => {
    try {
      const saved = window.localStorage.getItem(STORAGE_VER_KEY)
      const parsed = saved ? parseInt(saved, 10) : 18
      return Number.isFinite(parsed) && parsed >= 14 && parsed <= 25
        ? parsed
        : 18
    } catch {
      return 18
    }
  })

  const [askOnRun, setAskOnRun] = useState<boolean>(() => {
    try {
      return window.localStorage.getItem(STORAGE_ASK_KEY) === "true"
    } catch {
      return false
    }
  })

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_VER_KEY, String(version))
    } catch {
      // ignore storage errors
    }
  }, [version])

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_ASK_KEY, String(askOnRun))
    } catch {
      // ignore storage errors
    }
  }, [askOnRun])

  return { version, setVersion, askOnRun, setAskOnRun }
}

interface CorelExportBarProps {
  jobId: string
  filename?: string
  version: number
  onVersionChange: (v: number) => void
  askOnRun: boolean
  onAskOnRunChange: (ask: boolean) => void
}

export function CorelExportBar({
  jobId,
  filename,
  version,
  onVersionChange,
  askOnRun,
  onAskOnRunChange,
}: CorelExportBarProps) {
  const activeChoice =
    COREL_VERSION_CHOICES.find((c) => c.version === version) ??
    COREL_VERSION_CHOICES[0]

  const bundleUrl = jobCdrBundleUrl(jobId, {
    filename,
    version,
    ask: askOnRun,
  })
  const universalUrl = standaloneCdrConverterUrl(version, askOnRun)

  return (
    <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3.5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <Layers className="size-4 text-emerald-600" />
            <span className="text-sm font-semibold">
              CorelDRAW (.cdr) Avto-Konverter Paketi
            </span>
            <Badge
              variant="secondary"
              className="border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
            >
              {askOnRun
                ? `So'raladi (Standart: v${version})`
                : `Version ${version} (${activeChoice.short})`}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            Linux serverdan tayyor vektor PDF + Windows CorelDRAW avto-skripti
            yuklanadi. Skriptni 1 marta bossangiz, kompyuteringizdagi CorelDRAW
            orqali avtomatik{" "}
            <code className="rounded bg-muted px-1 py-0.5 font-mono text-[11px]">
              .cdr (v{version})
            </code>{" "}
            faylga aylantiradi.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {/* Version Select */}
          <div className="flex items-center gap-2">
            <Label className="text-xs whitespace-nowrap text-muted-foreground">
              CDR versiyasi:
            </Label>
            <Select
              value={String(version)}
              onValueChange={(v) => v && onVersionChange(parseInt(v, 10) || 18)}
            >
              <SelectTrigger className="h-8 w-[190px] text-xs">
                <SelectValue>{activeChoice.label}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {COREL_VERSION_CHOICES.map((c) => (
                  <SelectItem
                    key={c.version}
                    value={String(c.version)}
                    className="text-xs"
                  >
                    {c.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Ask version toggle */}
          <div className="flex items-center gap-1.5 rounded-md border bg-background/80 px-2.5 py-1">
            <Switch
              id={`ask-cdr-${jobId}`}
              checked={askOnRun}
              onCheckedChange={onAskOnRunChange}
            />
            <Label
              htmlFor={`ask-cdr-${jobId}`}
              className="cursor-pointer text-xs whitespace-nowrap"
              title="Yoqilsa, skript ishga tushganda CorelDRAW versiyasini kiritish oynasi chiqadi (standart 18)"
            >
              Har safar so'rash
            </Label>
          </div>

          {/* Primary Download CDR Bundle Button */}
          <Button
            size="sm"
            className="bg-emerald-600 text-white hover:bg-emerald-700"
            nativeButton={false}
            render={<a href={bundleUrl} download />}
          >
            <Download className="size-3.5" />
            <span>CDR (v{version}) Paket yuklab olish</span>
          </Button>

          {/* Standalone Universal Drag & Drop Script */}
          <Button
            variant="outline"
            size="sm"
            title="Kompyuterga 1 marta yuklab olib, istalgan PDF faylni ustiga tashlab .cdr (v18) qilish uchun universal skript"
            nativeButton={false}
            render={<a href={universalUrl} download />}
          >
            <FileCode2 className="size-3.5" />
            <span>Universal CDR Skript</span>
          </Button>
        </div>
      </div>

      <div className="mt-2.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <HelpCircle className="size-3.5 shrink-0 text-emerald-600" />
        <span>
          <strong>Ishlatish:</strong> Yuklangan ZIP arxivni oching va ichidagi{" "}
          <code className="rounded bg-muted px-1 py-0.5 font-mono">
            1_Bosishda_CDR_v{version}_Qilish.vbs
          </code>{" "}
          faylini 2 marta bosing — CorelDRAW avtomatik ochilib,{" "}
          <strong>.cdr (v{version})</strong> faylni yoniga saqlaydi.
        </span>
      </div>
    </div>
  )
}
