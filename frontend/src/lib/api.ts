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
  source_label?: string
}

export interface PrintHandoff {
  job_id: string
  front_filenames: string[]
  dieline_filename?: string | null
  trim_w_mm?: number | null
  trim_h_mm?: number | null
  source_label?: string
}

export interface ExtractorHoleInfo {
  center_x_mm: number
  center_y_mm: number
  diameter_mm: number
}

export interface ExtractorCandidate {
  id: string
  page_index: number
  role: "design" | "dieline"
  label: string
  bbox_mm: [number, number, number, number]
  width_mm: number
  height_mm: number
  has_outer_border: boolean
  has_fill: boolean
  fill_color_hex?: string | null
  interior_paths_count: number
  interior_texts_count: number
  has_hole: boolean
  holes_count: number
  holes: ExtractorHoleInfo[]
  confidence: number
  matches_text_hint: boolean
  selected_by_default: boolean
}

export interface ExtractorPageMeta {
  page_index: number
  page_number: number
  width_mm: number
  height_mm: number
  preview_file: string
  preview_px: [number, number]
  dimension_hints: Array<[number, number]>
  candidates_count: number
  designs_count: number
  dielines_count: number
}

export interface ExtractorInspectResponse {
  source_job_id: string
  filename: string
  page_count: number
  pages: ExtractorPageMeta[]
  candidates: ExtractorCandidate[]
}

export interface ExtractorExtractedItem {
  index: number
  id: string
  label: string
  role: "design" | "dieline"
  page_index: number
  width_mm: number
  height_mm: number
  bleed_mm: number
  filename: string
  thumb_file: string
  size_kb: number
}

export interface ExtractorOutputFileItem extends OutputFileItem {
  role?: string
  width_mm?: number
  height_mm?: number
  thumb_file?: string | null
}

export interface ExtractorRunResponse {
  job_id: string
  source_job_id: string
  source_filename: string
  items_count: number
  items: ExtractorExtractedItem[]
  output_files: ExtractorOutputFileItem[]
  design_files: string[]
  dieline_files: string[]
  combined_designs_file?: string | null
  combined_all_file?: string | null
  primary_design_file: string
  zip_file?: string | null
}

export interface LabelInspectDesign {
  index?: number
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

export interface CorelExportOptions {
  filename?: string
  version?: number
  ask?: boolean
}

export function jobCdrBundleUrl(
  jobId: string,
  options: CorelExportOptions = {}
): string {
  const params = new URLSearchParams()
  if (options.filename) params.set("filename", options.filename)
  params.set("version", String(options.version ?? 18))
  if (options.ask) params.set("ask", "true")
  return `/api/jobs/${encodeURIComponent(jobId)}/cdr-bundle?${params.toString()}`
}

export function standaloneCdrConverterUrl(
  version = 18,
  ask = false
): string {
  const params = new URLSearchParams()
  params.set("version", String(version))
  if (ask) params.set("ask", "true")
  return `/api/corel/standalone-converter?${params.toString()}`
}

// ---------------------------------------------------------------------------
// AI Design Studio (Claude Code + VectorCraft MCP + Skills & Assets)
// ---------------------------------------------------------------------------
export interface ClaudeLoginSessionState {
  status: "idle" | "waiting_for_code" | "completed" | "error" | string
  oauth_url?: string | null
  message: string
  output: string
}

export interface AiDesignStatusResponse {
  claude_cli: {
    installed: boolean
    version: string
  }
  vectorcraft_cli: {
    installed: boolean
    version: string
  }
  vectorcraft_web: {
    installed: boolean
    url: string
  }
  auth: {
    authenticated: boolean
    auth_method: string
    account_info: string
    has_saved_oauth_token: boolean
    has_saved_api_key: boolean
    masked_oauth_token: string
    masked_api_key: string
    login_session: ClaudeLoginSessionState
  }
  workspace_dir: string
  skills_count: number
  assets_count: number
}

export interface AiSkillFileItem {
  name: string
  size_kb: number
}

export interface AiSkillSummary {
  slug: string
  name: string
  description: string
  has_skill_md: boolean
  extra_files: AiSkillFileItem[]
  updated_at: number
}

export interface AiSkillDetail {
  slug: string
  name: string
  description: string
  content: string
  extra_files: AiSkillFileItem[]
}

export interface AiAssetItem {
  name: string
  ext: string
  size_kb: number
  updated_at: number
}

export interface AiDesignOutputFile {
  filename: string
  ext: string
  size_kb: number
  preview_file?: string | null
}

export interface AiDesignGenerateResponse {
  job_id: string
  assistant_reply: string
  duration_sec: number
  cost_usd?: number | null
  num_turns?: number | null
  conversion_notes: string[]
  width_mm?: number | null
  height_mm?: number | null
  output_files: AiDesignOutputFile[]
  vectorcraft_file?: string | null
  pdf_file?: string | null
  svg_file?: string | null
  preview_file?: string | null
  zip_file?: string | null
}

export interface VectorCraftHandoff {
  filename: string
  downloadUrl: string
  sourceLabel?: string
}

export function aiAssetFileUrl(filename: string): string {
  return `/api/ai-design/assets/${encodeURIComponent(filename)}`
}

export interface AiTerminalUploadItem {
  name?: string
  filename?: string
  ext?: string
  rel_path?: string
  mention: string
  size_kb: number
  updated_at?: number
}

export interface AiTerminalOutputItem {
  filename: string
  stem: string
  ext: string
  size_kb: number
  updated_at: number
  preview_file?: string | null
}

export function terminalOutputFileUrl(filename: string, inline = false): string {
  const base = `/api/ai-design/terminal/outputs/${encodeURIComponent(filename)}`
  return inline ? `${base}?inline=true` : base
}



