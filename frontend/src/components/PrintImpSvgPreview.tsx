import { useId, useMemo, useState } from "react"
import {
  AlertTriangle,
  Eye,
  FlipHorizontal2,
  Loader2,
  RotateCw,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"

export interface PrintImpSvgPreviewProps {
  sheetW: number
  sheetH: number
  trimW: number | null
  trimH: number | null
  detectedTrim?: [number, number] | null
  innerBleed: number
  outerBleed: number
  gutter: number
  gripper: number
  mode: string
  style: string
  orderQty: number
  waste: number
  orderNo: string
  jobName: string
  variantNames: string[]
  preflightLoading?: boolean
  hasFrontFiles: boolean
}

const DEFAULT_MARGIN_MM = 12
const SAMPLE_TRIM_W = 90
const SAMPLE_TRIM_H = 50

const VARIANT_PALETTE = [
  { fill: "rgba(59, 130, 246, 0.16)", stroke: "#3b82f6", text: "#1d4ed8" },
  { fill: "rgba(16, 185, 129, 0.16)", stroke: "#10b981", text: "#047857" },
  { fill: "rgba(139, 92, 246, 0.16)", stroke: "#8b5cf6", text: "#6d28d9" },
  { fill: "rgba(245, 158, 11, 0.16)", stroke: "#f59e0b", text: "#b45309" },
  { fill: "rgba(236, 72, 153, 0.16)", stroke: "#ec4899", text: "#be185d" },
  { fill: "rgba(6, 182, 212, 0.16)", stroke: "#06b6d4", text: "#0e7490" },
]

const CMYK_PATCHES = [
  "#00aeef",
  "#ec008c",
  "#fff200",
  "#111827",
  "#66cef6",
  "#f49ac1",
  "#fff799",
  "#6b7280",
  "#00aeef",
  "#ec008c",
  "#fff200",
  "#111827",
]

interface CellItem {
  col: number
  row: number
  x: number
  y: number
  w: number
  h: number
  slotNum: number
  variantIndex: number
  variantLabel: string
}

export function PrintImpSvgPreview({
  sheetW,
  sheetH,
  trimW,
  trimH,
  detectedTrim,
  innerBleed,
  outerBleed,
  gutter,
  gripper,
  mode,
  style,
  orderQty,
  waste,
  orderNo,
  jobName,
  variantNames,
  preflightLoading = false,
  hasFrontFiles,
}: PrintImpSvgPreviewProps) {
  const uid = useId().replace(/:/g, "")
  const [side, setSide] = useState<"front" | "back">("front")
  const [showBleed, setShowBleed] = useState(true)
  const [showCrops, setShowCrops] = useState(true)
  const [showGripper, setShowGripper] = useState(true)

  const hasBackSide =
    mode === "sheetwise" || mode === "turn" || mode === "tumble"
  const activeSide: "front" | "back" = hasBackSide ? side : "front"

  const validSheetW = Number.isFinite(sheetW) && sheetW > 10 ? sheetW : 500
  const validSheetH = Number.isFinite(sheetH) && sheetH > 10 ? sheetH : 350
  const validGripper = Number.isFinite(gripper) && gripper >= 0 ? gripper : 15
  const validGutter = Number.isFinite(gutter) && gutter >= 0 ? gutter : 0
  const validInnerBleed =
    Number.isFinite(innerBleed) && innerBleed >= 0 ? innerBleed : 0
  const validOuterBleed =
    Number.isFinite(outerBleed) && outerBleed >= 0 ? outerBleed : 0

  const trimInfo = useMemo(() => {
    if (trimW && trimH && trimW > 1 && trimH > 1) {
      return { w: trimW, h: trimH, source: "manual" as const }
    }
    if (detectedTrim && detectedTrim[0] > 1 && detectedTrim[1] > 1) {
      return {
        w: detectedTrim[0],
        h: detectedTrim[1],
        source: "detected" as const,
      }
    }
    return {
      w: SAMPLE_TRIM_W,
      h: SAMPLE_TRIM_H,
      source: "sample" as const,
    }
  }, [trimW, trimH, detectedTrim])

  const layout = useMemo(() => {
    const usableW = Math.max(0, validSheetW - DEFAULT_MARGIN_MM * 2)
    const usableH = Math.max(0, validSheetH - DEFAULT_MARGIN_MM - validGripper)

    const tw = trimInfo.w
    const th = trimInfo.h
    const gx = validGutter
    const gy = validGutter

    const cols0 =
      tw + gx > 0 ? Math.max(1, Math.floor((usableW + gx) / (tw + gx))) : 1
    const rows0 =
      th + gy > 0 ? Math.max(1, Math.floor((usableH + gy) / (th + gy))) : 1
    const total0 = cols0 * rows0

    const cols90 =
      th + gx > 0 ? Math.max(1, Math.floor((usableW + gx) / (th + gx))) : 1
    const rows90 =
      tw + gy > 0 ? Math.max(1, Math.floor((usableH + gy) / (tw + gy))) : 1
    const total90 = cols90 * rows90

    const useRot90 = total90 > total0
    const rotation = useRot90 ? 90 : 0
    const cols = useRot90 ? cols90 : cols0
    const rows = useRot90 ? rows90 : rows0
    const cellW = useRot90 ? th : tw
    const cellH = useRot90 ? tw : th
    const itemsPerSheet = cols * rows

    const gridW = cols * cellW + Math.max(0, cols - 1) * gx
    const gridH = rows * cellH + Math.max(0, rows - 1) * gy

    // Matches SheetAlignment.CENTER default in print_imp_service.py
    const startX = Math.max(0, (validSheetW - gridW) / 2)
    const startY = Math.max(0, (validSheetH - gridH) / 2)

    const fitsSheet = gridW <= validSheetW + 0.01 && gridH <= validSheetH + 0.01
    const overlapsGripper = startY + gridH > validSheetH - validGripper + 0.01

    const numVariants = Math.max(1, variantNames.length)
    const cells: CellItem[] = []

    // COL_BY_COL fill direction (default in backend)
    for (let c = 0; c < cols; c++) {
      for (let r = 0; r < rows; r++) {
        const seq = c * rows + r
        const vIdx =
          numVariants > 1
            ? Math.min(
                numVariants - 1,
                Math.floor((seq * numVariants) / itemsPerSheet)
              )
            : 0

        const drawCol =
          activeSide === "back" && (mode === "sheetwise" || mode === "turn")
            ? cols - 1 - c
            : c
        const drawRow =
          activeSide === "back" && mode === "tumble" ? rows - 1 - r : r

        const x = startX + drawCol * (cellW + gx)
        const y = startY + drawRow * (cellH + gy)

        cells.push({
          col: drawCol,
          row: drawRow,
          x,
          y,
          w: cellW,
          h: cellH,
          slotNum: seq + 1,
          variantIndex: vIdx,
          variantLabel: variantNames[vIdx] || "",
        })
      }
    }

    const totalArea = validSheetW * validSheetH
    const usedArea = itemsPerSheet * cellW * cellH
    const efficiencyPct =
      totalArea > 0 ? Math.min(100, (usedArea / totalArea) * 100) : 0

    const validQty = Number.isFinite(orderQty) && orderQty > 0 ? orderQty : 0
    const validWaste = Number.isFinite(waste) && waste > 0 ? waste : 0
    const netSheets =
      validQty > 0 && itemsPerSheet > 0
        ? Math.ceil(validQty / itemsPerSheet)
        : 0
    const totalSheets = netSheets + validWaste

    // Unique crop mark coordinates
    const xSet = new Set<number>()
    const ySet = new Set<number>()
    for (const item of cells) {
      xSet.add(Number(item.x.toFixed(2)))
      xSet.add(Number((item.x + item.w).toFixed(2)))
      ySet.add(Number(item.y.toFixed(2)))
      ySet.add(Number((item.y + item.h).toFixed(2)))
    }

    return {
      cols,
      rows,
      rotation,
      cellW,
      cellH,
      itemsPerSheet,
      gridW,
      gridH,
      startX,
      startY,
      usableW,
      usableH,
      fitsSheet,
      overlapsGripper,
      cells,
      efficiencyPct,
      netSheets,
      totalSheets,
      cropXs: Array.from(xSet).sort((a, b) => a - b),
      cropYs: Array.from(ySet).sort((a, b) => a - b),
    }
  }, [
    validSheetW,
    validSheetH,
    validGripper,
    validGutter,
    trimInfo,
    variantNames,
    activeSide,
    mode,
    orderQty,
    waste,
  ])

  // Responsive SVG scaling parameters (in mm)
  const maxDim = Math.max(validSheetW, validSheetH)
  const padTop = Math.max(22, maxDim * 0.065)
  const padLeft = Math.max(26, maxDim * 0.075)
  const padRight = Math.max(14, maxDim * 0.035)
  const padBottom = Math.max(18, maxDim * 0.045)

  const vbX = -padLeft
  const vbY = -padTop
  const vbW = validSheetW + padLeft + padRight
  const vbH = validSheetH + padTop + padBottom

  const dimFontSize = Math.max(7.5, maxDim * 0.023)
  const thinStroke = Math.max(0.35, maxDim * 0.0012)
  const medStroke = Math.max(0.6, maxDim * 0.002)

  const hasColorbar =
    style === "offset_standard" ||
    style === "packaging" ||
    style === "standard"

  const cropOff = Math.max(1, validOuterBleed + 1)
  const cropLen = Math.min(
    6,
    Math.max(2.5, Math.min(layout.startX, layout.startY) * 0.55)
  )

  const regR = Math.min(3.5, Math.max(2.0, maxDim * 0.007))
  const regCenters: Array<[number, number]> = [
    [validSheetW / 2, validSheetH - Math.max(4, validGripper / 2)],
    [validSheetW / 2, Math.max(4, DEFAULT_MARGIN_MM / 2)],
    [Math.max(4, DEFAULT_MARGIN_MM / 2), validSheetH / 2],
    [validSheetW - Math.max(4, DEFAULT_MARGIN_MM / 2), validSheetH / 2],
  ]

  const minCellSide = Math.min(layout.cellW, layout.cellH)
  const cellFontSize = Math.min(
    dimFontSize * 0.95,
    Math.max(4.5, minCellSide * 0.22)
  )
  const showCellIndex =
    layout.itemsPerSheet <= 80 && minCellSide >= cellFontSize * 1.9
  const showCellDims =
    layout.itemsPerSheet <= 36 &&
    layout.cellW >= cellFontSize * 5.2 &&
    layout.cellH >= cellFontSize * 3.4

  const passportText = `${orderNo || "№1001"}  •  ${jobName || variantNames[0] || "Montaj"}  •  ${validSheetW}×${validSheetH} mm  •  ${activeSide === "front" ? "OLDI" : "ORQA"}`

  return (
    <div className="rounded-xl border bg-card text-card-foreground">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <Eye className="size-4 text-muted-foreground" />
          <span className="text-sm font-medium">
            Taxminiy ko'rinish (SVG Preview)
          </span>
          {preflightLoading ? (
            <Badge variant="secondary" className="gap-1 text-xs">
              <Loader2 className="size-3 animate-spin" />
              O'lcham aniqlanmoqda...
            </Badge>
          ) : trimInfo.source === "sample" ? (
            <Badge variant="outline" className="text-xs font-normal">
              Namuna: {SAMPLE_TRIM_W}×{SAMPLE_TRIM_H} mm
              {hasFrontFiles ? " (Preflight bosing)" : ""}
            </Badge>
          ) : trimInfo.source === "detected" ? (
            <Badge variant="secondary" className="text-xs font-normal tabular-nums">
              Avto kesim: {trimInfo.w}×{trimInfo.h} mm
            </Badge>
          ) : (
            <Badge variant="secondary" className="text-xs font-normal tabular-nums">
              Kesim: {trimInfo.w}×{trimInfo.h} mm
            </Badge>
          )}
        </div>

        {/* Interactive toggles */}
        <div className="flex flex-wrap items-center gap-1.5">
          {hasBackSide && (
            <div className="mr-1 inline-flex rounded-md border bg-muted/40 p-0.5">
              <Button
                type="button"
                size="xs"
                variant={activeSide === "front" ? "secondary" : "ghost"}
                onClick={() => setSide("front")}
                className="h-6 px-2 text-xs"
              >
                Oldi
              </Button>
              <Button
                type="button"
                size="xs"
                variant={activeSide === "back" ? "secondary" : "ghost"}
                onClick={() => setSide("back")}
                className="h-6 gap-1 px-2 text-xs"
              >
                <FlipHorizontal2 className="size-3" />
                Orqa
              </Button>
            </div>
          )}

          <Button
            type="button"
            size="xs"
            variant={showBleed ? "secondary" : "ghost"}
            onClick={() => setShowBleed((v) => !v)}
            className="h-6 px-2 text-xs"
          >
            Bleed
          </Button>
          <Button
            type="button"
            size="xs"
            variant={showCrops ? "secondary" : "ghost"}
            onClick={() => setShowCrops((v) => !v)}
            className="h-6 px-2 text-xs"
          >
            Krop
          </Button>
          <Button
            type="button"
            size="xs"
            variant={showGripper ? "secondary" : "ghost"}
            onClick={() => setShowGripper((v) => !v)}
            className="h-6 px-2 text-xs"
          >
            Klapan
          </Button>
        </div>
      </div>

      {/* KPI Metrics Strip */}
      <div className="grid grid-cols-2 gap-px border-b bg-border sm:grid-cols-5">
        <div className="bg-card px-3 py-2">
          <div className="text-[11px] text-muted-foreground">Qolip (Grid)</div>
          <div className="text-sm font-semibold tabular-nums">
            {layout.cols}×{layout.rows}{" "}
            <span className="font-normal text-muted-foreground">
              ({layout.itemsPerSheet} dona)
            </span>
          </div>
        </div>
        <div className="bg-card px-3 py-2">
          <div className="text-[11px] text-muted-foreground">Aylantirish</div>
          <div className="flex items-center gap-1 text-sm font-semibold tabular-nums">
            <RotateCw className="size-3.5 text-muted-foreground" />
            {layout.rotation}°
          </div>
        </div>
        <div className="bg-card px-3 py-2">
          <div className="text-[11px] text-muted-foreground">Montaj bloki</div>
          <div className="text-sm font-semibold tabular-nums">
            {Number(layout.gridW.toFixed(1))}×{Number(layout.gridH.toFixed(1))}{" "}
            mm
          </div>
        </div>
        <div className="bg-card px-3 py-2">
          <div className="text-[11px] text-muted-foreground">Foydali maydon</div>
          <div className="text-sm font-semibold tabular-nums">
            {layout.efficiencyPct.toFixed(1)}%
          </div>
        </div>
        <div className="col-span-2 bg-card px-3 py-2 sm:col-span-1">
          <div className="text-[11px] text-muted-foreground">Taxminiy list</div>
          <div className="text-sm font-semibold tabular-nums">
            {layout.totalSheets > 0 ? `${layout.totalSheets} list` : "—"}
          </div>
        </div>
      </div>

      {/* Warnings */}
      {(!layout.fitsSheet || layout.overlapsGripper) && (
        <div className="flex items-center gap-2 border-b bg-amber-500/10 px-4 py-2 text-xs text-amber-600 dark:text-amber-400">
          <AlertTriangle className="size-3.5 shrink-0" />
          {!layout.fitsSheet ? (
            <span>
              Diqqat: Kesim o'lchami ({trimInfo.w}×{trimInfo.h} mm) tanlangan
              qog'oz ({validSheetW}×{validSheetH} mm) dan katta!
            </span>
          ) : (
            <span>
              Eslatma: Markazlashtirilgan montaj bloki pastki klapan ({validGripper}{" "}
              mm) zonasiga yaqinlashgan.
            </span>
          )}
        </div>
      )}

      {/* SVG Canvas */}
      <div className="flex items-center justify-center bg-muted/20 p-3 sm:p-5">
        <svg
          viewBox={`${vbX} ${vbY} ${vbW} ${vbH}`}
          className="max-h-[420px] w-full select-none"
          role="img"
          aria-label={`Varaq montaji SVG preview: ${validSheetW}×${validSheetH} mm, ${layout.cols}×${layout.rows} katak`}
        >
          <defs>
            <pattern
              id={`gripper-hatch-${uid}`}
              width={6}
              height={6}
              patternUnits="userSpaceOnUse"
              patternTransform="rotate(45)"
            >
              <line
                x1={0}
                y1={0}
                x2={0}
                y2={6}
                stroke="#f59e0b"
                strokeOpacity={0.38}
                strokeWidth={1.6}
              />
            </pattern>
            <filter
              id={`sheet-shadow-${uid}`}
              x="-5%"
              y="-5%"
              width="112%"
              height="112%"
            >
              <feDropShadow
                dx={0}
                dy={2}
                stdDeviation={3}
                floodColor="#000000"
                floodOpacity={0.22}
              />
            </filter>
          </defs>

          {/* Top Sheet Width Dimension */}
          <g className="text-muted-foreground" fill="currentColor" stroke="currentColor">
            <line
              x1={0}
              y1={-padTop * 0.48}
              x2={validSheetW}
              y2={-padTop * 0.48}
              strokeWidth={thinStroke}
              strokeOpacity={0.65}
            />
            <line
              x1={0}
              y1={-padTop * 0.68}
              x2={0}
              y2={-padTop * 0.28}
              strokeWidth={thinStroke}
              strokeOpacity={0.65}
            />
            <line
              x1={validSheetW}
              y1={-padTop * 0.68}
              x2={validSheetW}
              y2={-padTop * 0.28}
              strokeWidth={thinStroke}
              strokeOpacity={0.65}
            />
            <text
              x={validSheetW / 2}
              y={-padTop * 0.62}
              textAnchor="middle"
              stroke="none"
              fontSize={dimFontSize}
              fontWeight={500}
            >
              {validSheetW} mm
            </text>
          </g>

          {/* Left Sheet Height Dimension */}
          <g className="text-muted-foreground" fill="currentColor" stroke="currentColor">
            <line
              x1={-padLeft * 0.45}
              y1={0}
              x2={-padLeft * 0.45}
              y2={validSheetH}
              strokeWidth={thinStroke}
              strokeOpacity={0.65}
            />
            <line
              x1={-padLeft * 0.62}
              y1={0}
              x2={-padLeft * 0.28}
              y2={0}
              strokeWidth={thinStroke}
              strokeOpacity={0.65}
            />
            <line
              x1={-padLeft * 0.62}
              y1={validSheetH}
              x2={-padLeft * 0.28}
              y2={validSheetH}
              strokeWidth={thinStroke}
              strokeOpacity={0.65}
            />
            <text
              x={-padLeft * 0.6}
              y={validSheetH / 2}
              textAnchor="middle"
              stroke="none"
              fontSize={dimFontSize}
              fontWeight={500}
              transform={`rotate(-90 ${-padLeft * 0.6} ${validSheetH / 2})`}
            >
              {validSheetH} mm
            </text>
          </g>

          {/* Paper Sheet */}
          <rect
            x={0}
            y={0}
            width={validSheetW}
            height={validSheetH}
            rx={1}
            fill="#ffffff"
            stroke="#94a3b8"
            strokeWidth={medStroke}
            filter={`url(#sheet-shadow-${uid})`}
          />

          {/* Usable / Safe Margin Guide */}
          <rect
            x={DEFAULT_MARGIN_MM}
            y={DEFAULT_MARGIN_MM}
            width={Math.max(0, validSheetW - DEFAULT_MARGIN_MM * 2)}
            height={Math.max(
              0,
              validSheetH - DEFAULT_MARGIN_MM - validGripper
            )}
            fill="none"
            stroke="#cbd5e1"
            strokeWidth={thinStroke}
            strokeDasharray={`${thinStroke * 4} ${thinStroke * 3}`}
          />

          {/* Gripper / Klapan Zone */}
          {showGripper && validGripper > 0 && (
            <g>
              <rect
                x={0}
                y={Math.max(0, validSheetH - validGripper)}
                width={validSheetW}
                height={Math.min(validGripper, validSheetH)}
                fill={`url(#gripper-hatch-${uid})`}
              />
              <line
                x1={0}
                y1={Math.max(0, validSheetH - validGripper)}
                x2={validSheetW}
                y2={Math.max(0, validSheetH - validGripper)}
                stroke="#f59e0b"
                strokeWidth={thinStroke}
                strokeDasharray={`${thinStroke * 5} ${thinStroke * 3}`}
              />
              {validGripper >= 7 && (
                <text
                  x={validSheetW / 2}
                  y={validSheetH - validGripper / 2 + dimFontSize * 0.25}
                  textAnchor="middle"
                  fill="#b45309"
                  fontSize={Math.min(dimFontSize * 0.72, validGripper * 0.55)}
                  fontWeight={600}
                  letterSpacing={0.6}
                >
                  KLAPAN ({validGripper} mm)
                </text>
              )}
            </g>
          )}

          {/* CMYK Colorbar (for offset/standard/packaging styles) */}
          {hasColorbar && (
            <g>
              {(() => {
                const barH = Math.min(4.5, Math.max(2.5, DEFAULT_MARGIN_MM * 0.36))
                const patchW = Math.min(
                  8,
                  (validSheetW * 0.42) / CMYK_PATCHES.length
                )
                const totalBarW = patchW * CMYK_PATCHES.length
                const barX = (validSheetW - totalBarW) / 2
                const barY = Math.max(1.5, (DEFAULT_MARGIN_MM - barH) / 2)
                return CMYK_PATCHES.map((color, idx) => (
                  <rect
                    key={idx}
                    x={barX + idx * patchW}
                    y={barY}
                    width={patchW}
                    height={barH}
                    fill={color}
                    stroke="#cbd5e1"
                    strokeWidth={thinStroke * 0.4}
                  />
                ))
              })()}
            </g>
          )}

          {/* Side Passport Text */}
          <text
            x={Math.max(4, DEFAULT_MARGIN_MM * 0.48)}
            y={validSheetH - Math.max(validGripper + 8, 22)}
            fill="#64748b"
            fontSize={Math.max(4.5, dimFontSize * 0.52)}
            transform={`rotate(-90 ${Math.max(4, DEFAULT_MARGIN_MM * 0.48)} ${validSheetH - Math.max(validGripper + 8, 22)})`}
          >
            {passportText}
          </text>

          {/* 4 Registration Marks */}
          {showCrops && (
            <g stroke="#334155" strokeWidth={thinStroke * 0.85} fill="none">
              {regCenters.map(([cx, cy], idx) => (
                <g key={idx}>
                  <circle cx={cx} cy={cy} r={regR} />
                  <circle cx={cx} cy={cy} r={regR * 0.48} />
                  <line x1={cx - regR * 1.45} y1={cy} x2={cx + regR * 1.45} y2={cy} />
                  <line x1={cx} y1={cy - regR * 1.45} x2={cx} y2={cy + regR * 1.45} />
                </g>
              ))}
            </g>
          )}

          {/* Bleed Layer */}
          {showBleed && (validInnerBleed > 0 || validOuterBleed > 0) && (
            <g>
              {layout.cells.map((item) => {
                const bL =
                  item.col === 0
                    ? validOuterBleed
                    : Math.min(validInnerBleed, validGutter / 2)
                const bR =
                  item.col === layout.cols - 1
                    ? validOuterBleed
                    : Math.min(validInnerBleed, validGutter / 2)
                const bT =
                  item.row === 0
                    ? validOuterBleed
                    : Math.min(validInnerBleed, validGutter / 2)
                const bB =
                  item.row === layout.rows - 1
                    ? validOuterBleed
                    : Math.min(validInnerBleed, validGutter / 2)
                return (
                  <rect
                    key={`b-${item.col}-${item.row}`}
                    x={item.x - bL}
                    y={item.y - bT}
                    width={item.w + bL + bR}
                    height={item.h + bT + bB}
                    fill="rgba(244, 63, 94, 0.11)"
                    stroke="#f43f5e"
                    strokeOpacity={0.55}
                    strokeWidth={thinStroke * 0.7}
                    strokeDasharray={`${thinStroke * 3} ${thinStroke * 2}`}
                  />
                )
              })}
            </g>
          )}

          {/* Trim Cells */}
          <g>
            {layout.cells.map((item) => {
              const pal =
                VARIANT_PALETTE[item.variantIndex % VARIANT_PALETTE.length]
              return (
                <g key={`c-${item.col}-${item.row}`}>
                  <rect
                    x={item.x}
                    y={item.y}
                    width={item.w}
                    height={item.h}
                    fill={pal.fill}
                    stroke={pal.stroke}
                    strokeWidth={medStroke}
                  />
                  {/* Subtle orientation corner indicator */}
                  <polygon
                    points={`${item.x},${item.y} ${item.x + Math.min(5, item.w * 0.14)},${item.y} ${item.x},${item.y + Math.min(5, item.h * 0.14)}`}
                    fill={pal.stroke}
                    fillOpacity={0.55}
                  />
                  {showCellIndex && (
                    <text
                      x={item.x + item.w / 2}
                      y={
                        item.y +
                        item.h / 2 +
                        (showCellDims
                          ? -cellFontSize * 0.18
                          : cellFontSize * 0.35)
                      }
                      textAnchor="middle"
                      fill={pal.text}
                      fontSize={cellFontSize}
                      fontWeight={600}
                    >
                      {variantNames.length > 1
                        ? `V${item.variantIndex + 1} #${item.slotNum}`
                        : `#${item.slotNum}`}
                    </text>
                  )}
                  {showCellDims && (
                    <text
                      x={item.x + item.w / 2}
                      y={item.y + item.h / 2 + cellFontSize * 0.95}
                      textAnchor="middle"
                      fill={pal.text}
                      fillOpacity={0.78}
                      fontSize={cellFontSize * 0.72}
                    >
                      {Number(item.w.toFixed(1))}×{Number(item.h.toFixed(1))}
                    </text>
                  )}
                </g>
              )
            })}
          </g>

          {/* Outer Perimeter Crop Marks */}
          {showCrops && layout.cells.length > 0 && (
            <g stroke="#0f172a" strokeWidth={thinStroke * 0.9}>
              {layout.cropXs.map((x) => (
                <g key={`cx-${x}`}>
                  <line
                    x1={x}
                    y1={layout.startY - cropOff}
                    x2={x}
                    y2={layout.startY - cropOff - cropLen}
                  />
                  <line
                    x1={x}
                    y1={layout.startY + layout.gridH + cropOff}
                    x2={x}
                    y2={layout.startY + layout.gridH + cropOff + cropLen}
                  />
                </g>
              ))}
              {layout.cropYs.map((y) => (
                <g key={`cy-${y}`}>
                  <line
                    x1={layout.startX - cropOff}
                    y1={y}
                    x2={layout.startX - cropOff - cropLen}
                    y2={y}
                  />
                  <line
                    x1={layout.startX + layout.gridW + cropOff}
                    y1={y}
                    x2={layout.startX + layout.gridW + cropOff + cropLen}
                    y2={y}
                  />
                </g>
              ))}
            </g>
          )}
        </svg>
      </div>

      {/* Legend Footer */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-t px-4 py-2 text-[11px] text-muted-foreground">
        <div className="flex flex-wrap items-center gap-3">
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block size-2.5 rounded-[2px] border border-blue-500 bg-blue-500/20" />
            Kesim (Trim)
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block size-2.5 rounded-[2px] border border-dashed border-rose-500 bg-rose-500/15" />
            Bleed ({validInnerBleed}/{validOuterBleed} mm)
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block size-2.5 rounded-[2px] border border-amber-500 bg-amber-500/25" />
            Klapan ({validGripper} mm)
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-3 bg-slate-800 dark:bg-slate-200" />
            Krop + Privodka
          </span>
        </div>
        <span className="tabular-nums">
          Oraliq (Gutter): {validGutter} mm
          {hasBackSide
            ? ` • ${activeSide === "front" ? "Oldi tomon" : "Orqa tomon (oyna aksi)"}`
            : ""}
        </span>
      </div>
    </div>
  )
}
