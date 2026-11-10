/** Client HTTP de l'API ImmoGest (session Django + CSRF, même origine). */

export const API_BASE = '/api/v1'

export class ApiError extends Error {
  status: number
  code: string
  details: Record<string, string[] | string>

  constructor(status: number, code: string, message: string, details: Record<string, string[] | string> = {}) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }

  /** Erreurs par champ, prêtes pour React Hook Form. */
  fieldErrors(): Record<string, string> {
    const out: Record<string, string> = {}
    for (const [k, v] of Object.entries(this.details)) out[k] = Array.isArray(v) ? v.join(' ') : String(v)
    return out
  }
}

type Params = Record<string, string | number | boolean | undefined | null>

function getCookie(name: string): string {
  const match = document.cookie.split('; ').find((row) => row.startsWith(`${name}=`))
  return match ? decodeURIComponent(match.split('=')[1]) : ''
}

export function buildUrl(path: string, params?: Params): string {
  const url = `${API_BASE}${path}`
  if (!params) return url
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') qs.set(k, String(v))
  }
  const s = qs.toString()
  return s ? `${url}?${s}` : url
}

async function request<T>(method: string, path: string, body?: unknown, params?: Params): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  let payload: BodyInit | undefined
  if (body instanceof FormData) {
    payload = body
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  if (method !== 'GET') headers['X-CSRFToken'] = getCookie('csrftoken')

  const res = await fetch(buildUrl(path, params), { method, headers, body: payload, credentials: 'same-origin' })
  if (res.status === 204) return undefined as T

  const isJson = res.headers.get('content-type')?.includes('application/json')
  const data: unknown = isJson ? await res.json() : null
  if (!res.ok) {
    const e = (data ?? {}) as { code?: string; message?: string; details?: Record<string, string[] | string> }
    throw new ApiError(
      res.status,
      e.code ?? 'error',
      e.message ?? (res.status >= 500 ? 'Erreur du serveur, réessayez plus tard.' : 'Requête refusée.'),
      e.details ?? {},
    )
  }
  return data as T
}

export const api = {
  get: <T>(path: string, params?: Params) => request<T>('GET', path, undefined, params),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {}),
  patch: <T>(path: string, body: unknown) => request<T>('PATCH', path, body),
  put: <T>(path: string, body: unknown) => request<T>('PUT', path, body),
  delete: (path: string) => request<void>('DELETE', path),
  /** Prépare le cookie CSRF (à appeler une fois au démarrage). */
  ensureCsrf: () => request<unknown>('GET', '/auth/csrf/'),
}

/** Télécharge un fichier (PDF, CSV, XLSX) servi par l'API. */
export async function downloadFile(path: string, params?: Params, fallbackName = 'fichier'): Promise<void> {
  const res = await fetch(buildUrl(path, params), { credentials: 'same-origin' })
  if (!res.ok) throw new ApiError(res.status, 'download_error', 'Téléchargement impossible.')
  const disposition = res.headers.get('content-disposition') ?? ''
  const name = /filename="?([^";]+)"?/.exec(disposition)?.[1] ?? fallbackName
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
