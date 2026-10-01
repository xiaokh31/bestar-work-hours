export interface AttendanceImportResponse {
  id: string;
  originalFilename: string;
  filenameReviewCode: string | null;
  fileSha256: string;
  mimeType: string | null;
  fileSizeBytes: string | null;
  importStatus: string;
  parseStatus: string;
  parserVersion: string | null;
  settlementMonth: string | null;
  periodStart: string | null;
  periodEnd: string | null;
  employeeCount: number;
  dayCount: number;
  warningCount: number;
  errorCount: number;
  errorMessage: string | null;
  dataRevision: number;
  createdAt: string;
  updatedAt: string;
}

export interface AttendanceImportListResponse {
  items: AttendanceImportResponse[];
  limit: number;
  offset: number;
}

export interface AttendanceImportListFilters {
  limit?: number;
  offset?: number;
  parseStatus?: string;
}

export interface AttendanceRowResponse {
  id: string;
  rowKey: string;
  employeeId: string | null;
  employeeName: string | null;
  department: string | null;
  workDate: string;
  dayNumber: number;
  punchTimes: unknown;
  calculationMethod:
    | "LEGACY_UNKNOWN"
    | "NO_PUNCHES"
    | "FIRST_LAST_FALLBACK"
    | "PAIRED_INTERVALS";
  workIntervals: unknown;
  pairedGrossHours: string | null;
  lunchHours: string;
  calculatedHours: string | null;
  firstPunch: string | null;
  lastPunch: string | null;
  rawJson: unknown;
  warnings: unknown;
  errors: unknown;
}

export interface WageGeneratedFileResponse {
  id: string;
  attendanceImportId: string | null;
  fileType: string;
  storagePath: string;
  fileSha256: string | null;
  mimeType: string | null;
  fileSizeBytes: string | null;
  status: string;
  errorMessage: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface AttendanceParseResultResponse {
  attendanceImport: AttendanceImportResponse;
  rows: AttendanceRowResponse[];
  warnings: unknown[];
  errors: unknown[];
  activeRowCount: number;
  deletedRowCount: number;
}

export interface AttendanceRowAuditEventResponse {
  id: string;
  eventCode: "DELETED" | "CORRECTED";
  attendanceImportId: string;
  attendanceRowId: string | null;
  rowKey: string;
  employeeId: string | null;
  employeeName: string | null;
  department: string | null;
  workDate: string;
  rowSnapshot: Record<string, unknown>;
  afterSnapshot?: Record<string, unknown> | null;
  actor: { id: string | null; displayLabel: string };
  reason: string;
  occurredAt: string;
}

export interface AttendanceRowHistoryResponse {
  items: AttendanceRowAuditEventResponse[];
  limit: number;
  offset: number;
  total: number;
}

export interface DeleteAttendanceRowResponse {
  code: "ATTENDANCE_ROW_DELETED" | "ATTENDANCE_ROW_ALREADY_DELETED";
  deleted: boolean;
  alreadyDeleted: boolean;
  activeRowCount: number;
  deletedRowCount: number;
  row: AttendanceRowResponse;
  event: AttendanceRowAuditEventResponse;
  affectedGeneratedFiles: Array<{ id: string; status: "SUPERSEDED" }>;
}

export interface AttendanceImportFileImpact {
  id: string;
  fileType: string;
  previousStatus: string;
  nextStatus: string;
}

export interface AttendanceImportDeletionImpactResponse {
  attendanceImportId: string;
  originalFilename: string;
  settlementMonth: string | null;
  periodStart: string | null;
  periodEnd: string | null;
  employeeCount: number;
  dayCount: number;
  activeRowCount: number;
  deletedRowCount: number;
  warningCount: number;
  errorCount: number;
  generatedFileCount: number;
  generatedFileSummary: Array<{
    fileType: string;
    status: string;
    count: number;
  }>;
}

export interface AttendanceImportAuditEventResponse {
  id: string;
  eventCode: "DELETED" | "CORRECTED";
  attendanceImportId: string;
  originalFilename: string;
  fileSha256: string;
  importStatus: string;
  parseStatus: string;
  settlementMonth: string | null;
  periodStart: string | null;
  periodEnd: string | null;
  employeeCount: number;
  dayCount: number;
  activeRowCount: number;
  deletedRowCount: number;
  warningCount: number;
  errorCount: number;
  generatedFiles: AttendanceImportFileImpact[];
  actor: { id: string | null; displayLabel: string };
  reason: string;
  occurredAt: string;
}

export interface AttendanceImportDeletionHistoryResponse {
  items: AttendanceImportAuditEventResponse[];
  limit: number;
  offset: number;
  total: number;
}

export interface DeleteAttendanceImportResponse {
  code:
    | "ATTENDANCE_IMPORT_DELETED"
    | "ATTENDANCE_IMPORT_ALREADY_DELETED";
  deleted: boolean;
  alreadyDeleted: boolean;
  event: AttendanceImportAuditEventResponse;
  affectedGeneratedFiles: AttendanceImportFileImpact[];
  fallbackImport: AttendanceImportResponse | null;
}

export interface WageGeneratedFileListResponse {
  items: WageGeneratedFileResponse[];
}

export interface GenerateWageRecordResponse {
  generatedFile: WageGeneratedFileResponse;
  taskReport: WageGeneratedFileResponse | null;
  warnings: unknown[];
  errors: unknown[];
}


export function listAttendanceImports(
  filters: AttendanceImportListFilters = {},
  options: ApiClientOptions = {},
): Promise<AttendanceImportListResponse> {
  return createApiClient(options).get<AttendanceImportListResponse>(
    `/attendance-imports${toAttendanceImportListQueryString(filters)}`,
  );
}

export function getAttendanceImport(
  id: string,
  options: ApiClientOptions = {},
): Promise<AttendanceImportResponse> {
  return createApiClient(options).get<AttendanceImportResponse>(
    `/attendance-imports/${encodeURIComponent(id)}`,
  );
}

export function getAttendanceImportDeletionImpact(
  id: string,
  options: ApiClientOptions = {},
): Promise<AttendanceImportDeletionImpactResponse> {
  return createApiClient(options).get<AttendanceImportDeletionImpactResponse>(
    `/attendance-imports/${encodeURIComponent(id)}/deletion-impact`,
  );
}

export function deleteAttendanceImport(
  id: string,
  reason: string,
  options: ApiClientOptions = {},
): Promise<DeleteAttendanceImportResponse> {
  return createApiClient(options).request<DeleteAttendanceImportResponse>(
    `/attendance-imports/${encodeURIComponent(id)}`,
    { method: "DELETE", body: { reason } },
  );
}

export function getAttendanceImportDeletionHistory(
  filters: { limit?: number; offset?: number } = {},
  options: ApiClientOptions = {},
): Promise<AttendanceImportDeletionHistoryResponse> {
  const params = new URLSearchParams();
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters.offset !== undefined) params.set("offset", String(filters.offset));
  const suffix = params.size > 0 ? `?${params.toString()}` : "";
  return createApiClient(options).get<AttendanceImportDeletionHistoryResponse>(
    `/attendance-imports/deletion-history${suffix}`,
  );
}

export function parseAttendanceImport(
  id: string,
  options: ApiClientOptions = {},
): Promise<AttendanceParseResultResponse> {
  return createApiClient(options).post<AttendanceParseResultResponse>(
    `/attendance-imports/${encodeURIComponent(id)}/parse`,
  );
}

export function getAttendanceParseResult(
  id: string,
  options: ApiClientOptions = {},
): Promise<AttendanceParseResultResponse> {
  return createApiClient(options).get<AttendanceParseResultResponse>(
    `/attendance-imports/${encodeURIComponent(id)}/parse-result`,
  );
}

export function deleteAttendanceRow(
  attendanceImportId: string,
  rowId: string,
  reason: string,
  options: ApiClientOptions = {},
): Promise<DeleteAttendanceRowResponse> {
  return createApiClient(options).request<DeleteAttendanceRowResponse>(
    `/attendance-imports/${encodeURIComponent(attendanceImportId)}/rows/${encodeURIComponent(rowId)}`,
    { method: "DELETE", body: { reason } },
  );
}

export function getAttendanceRowHistory(
  attendanceImportId: string,
  filters: { limit?: number; offset?: number } = {},
  options: ApiClientOptions = {},
): Promise<AttendanceRowHistoryResponse> {
  const params = new URLSearchParams();
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters.offset !== undefined) params.set("offset", String(filters.offset));
  const suffix = params.size > 0 ? `?${params.toString()}` : "";
  return createApiClient(options).get<AttendanceRowHistoryResponse>(
    `/attendance-imports/${encodeURIComponent(attendanceImportId)}/row-history${suffix}`,
  );
}

export function generateAttendanceWageRecord(
  id: string,
  options: ApiClientOptions = {},
): Promise<GenerateWageRecordResponse> {
  return createApiClient(options).post<GenerateWageRecordResponse>(
    `/attendance-imports/${encodeURIComponent(id)}/generate-wage-record`,
  );
}

export function listAttendanceImportFiles(
  id: string,
  options: ApiClientOptions = {},
  filters: {limit?: number;offset?: number} = {},
): Promise<WageGeneratedFileListResponse> {
  const params = new URLSearchParams({limit:String(filters.limit ?? 100),offset:String(filters.offset ?? 0)});
  return createApiClient(options).get<WageGeneratedFileListResponse>(
    "/attendance-imports/" + encodeURIComponent(id) + "/files?" + params,
  );
}


export interface ApiClientOptions { baseUrl?: string; serviceKey?: string; deploymentBypass?: string }
export class ApiClientError extends Error {
  code: string; status: number;
  constructor(value: {code: string; status: number; message: string}) { super(value.message); this.code=value.code; this.status=value.status; }
}
export function createApiClient(options: ApiClientOptions = {}) {
  async function request<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
    const headers = new Headers();
    if (options.serviceKey) headers.set("X-Service-Key", options.serviceKey);
    if (options.deploymentBypass) headers.set("x-vercel-protection-bypass", options.deploymentBypass);
    const body = init.body instanceof FormData ? init.body : init.body === undefined ? undefined : JSON.stringify(init.body);
    if (body && !(body instanceof FormData)) headers.set("Content-Type", "application/json");
    let response: Response;
    try { response = await fetch(`${options.baseUrl ?? "/api"}${path}`, { method: init.method ?? "GET", headers, body, cache: "no-store", redirect: "error", signal: AbortSignal.timeout(65000) }); }
    catch { throw new ApiClientError({code:"API_UNAVAILABLE",status:503,message:"API unavailable"}); }
    const value = await response.json().catch(() => ({}));
    if (!response.ok) throw new ApiClientError({ code: value.code ?? "REQUEST_FAILED", message: value.message ?? "The request failed.", status: response.status });
    return value as T;
  }
  return { request, get: <T>(path: string) => request<T>(path), post: <T>(path: string, body?: unknown) => request<T>(path,{method:"POST",body}) };
}
function toAttendanceImportListQueryString(filters: AttendanceImportListFilters) {
  const params = new URLSearchParams();
  for (const [key,value] of Object.entries(filters)) if (value !== undefined) params.set(key,String(value));
  return params.size ? `?${params}` : "";
}
export const uploadAttendanceImportFile = (file: File) => { const body=new FormData(); body.set("file",file); return createApiClient().post<AttendanceImportResponse>("/attendance-imports",body); };
export const getAttendanceGeneratedFileDownloadUrl = (_importId: string, fileId: string) => `/api/attendance-files/${encodeURIComponent(fileId)}/download`;
export const getApiHealth = (options: ApiClientOptions) => createApiClient(options).get<{status:"ok"|"degraded";database:{status:"up"|"down"};serverTime:string;version:string}>("/health");
export const correctAttendanceRow = (id: string, rowId: string, punchTimes: string[], reason: string, expectedRevision: number) => createApiClient().request(`/attendance-imports/${encodeURIComponent(id)}/rows/${encodeURIComponent(rowId)}`, {method:"PATCH",body:{punchTimes,reason,expectedRevision}});
