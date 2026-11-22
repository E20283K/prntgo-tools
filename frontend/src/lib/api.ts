export interface SelaTemplate {
  name: string
  size_kb: number
}

export interface SelaGeneralSetItem {
  name: string
  label: string
}

export interface SelaSostavGroup {
  key: string
  label: string
  files: string[]
}

export interface SelaConfigResponse {
  templates: SelaTemplate[]
  set_catalog: {
    general: SelaGeneralSetItem[]
    sostav_groups: SelaSostavGroup[]
  }
}

export interface SelaQueueItem {
  artikul: string
  colour: string
  size: string
  barcode: string
  qty: number
  general_sets?: string[]
  sostav_key?: string | null
}

export interface SelaGenerateResponse {
  job_id: string
  output_file: string
  preview_file: string
  total_labels: number
  page_count: number
  size_kb: number
}

export interface LabelHandoff {
  job_id: string
  filename: string
  total_labels: number
}

export interface LabelInspectDesign {
  display_name: string
  width_mm: number
  length_mm: number
  orig_width_mm?: number
  orig_length_mm?: number
  rotation_deg?: number
  recommended_gear: number | null
  recommended_copies: number | null
  printing_length_mm?: number | null
  film_length_mm?: number | null
}

export interface LabelInspectResponse {
  designs: LabelInspectDesign[]
}

export interface OutputFileItem {
  filename: string
  size_kb: number
  preview_file?: string | null
}

export interface LabelRunDesign {
  design_name: string
  width_mm: number
  length_mm: number
  rotation_deg?: number
  gear: number
  copies: number
  printing_length_mm: number
  film_length_mm: number
  colors: string[]
  grayscale_passed: boolean
}

export interface LabelRunResponse {
  job_id: string
  output_files: OutputFileItem[]
  zip_file?: string | null
  designs: LabelRunDesign[]
}

export interface PrintPreset {
  name: string
  description: string
  sheet_w: number
  sheet_h: number
  gripper: number
  inner_bleed: number
  outer_bleed: number
  gutter: number
  style: string
  category: string
  cut_style: string
}

export interface PrintPresetsResponse {
  presets: Record<string, PrintPreset>
}

export interface PrintPreflightIssue {
  severity: "ERROR" | "WARNING" | "INFO" | string
  message: string
}

export interface PrintPreflightResponse {
  page_count: number
  trim_box_mm: [number, number]
  detected_bleed_mm: number
  colors: Array<{ name: string }>
  issues: PrintPreflightIssue[]
  dieline_trim?: {
    trim_w_mm: number
    trim_h_mm: number
  } | null
}

export interface PrintRunResponse {
  job_id: string
  cols: number
  rows: number
  items_per_sheet: number
  rotation: number
  calculated_sheets: number
  output_files: OutputFileItem[]
  zip_file?: string | null
}

export interface GearItem {
  gear: number
  pitch_diameter: number
  plate_thickness: number
  cylinder_diameter: number
  film_length: number
  printing_length: number
  available: boolean
}

export interface GearsResponse {
  gears: GearItem[]
}

export interface AuthStatusResponse {
  auth_enabled: boolean
  authenticated: boolean
}

let unauthorizedHandler: (() => void) | null = null

export function setUnauthorizedHandler(fn: () => void) {
  unauthorizedHandler = fn
}

export async function apiFetch(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  const res = await fetch(url, options)
  if (res.status === 401) {
    unauthorizedHandler?.()
    throw new Error("Tizimga kirish talab qilinadi.")
  }
  if (!res.ok) {
    let detail = `Xatolik (${res.status})`
    try {
      const data = await res.json()
      if (data.detail) detail = String(data.detail)
    } catch {
      // ignore json parse errors
    }
    throw new Error(detail)
  }
  return res
}

export function jobFileUrl(
  jobId: string,
  filename: string,
  inline = false
): string {
  const base = `/api/jobs/${jobId}/files/${encodeURIComponent(filename)}`
  return inline ? `${base}?inline=true` : base
}

export function selaSetPreviewUrl(filename: string): string {
  return `/api/sela/set-preview/${encodeURIComponent(filename)}`
}

export function selaSetPreviewImgUrl(filename: string, dpi = 150): string {
  return `/api/sela/set-preview/${encodeURIComponent(filename)}?format=png&dpi=${dpi}`
}
