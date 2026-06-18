export class ApiError extends Error {
  readonly status: number;
  readonly statusText: string;

  constructor(message: string, response: Response) {
    super(message);
    this.name = 'ApiError';
    this.status = response.status;
    this.statusText = response.statusText;
  }
}

export async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  await assertOk(response);
  return response.json() as Promise<T>;
}

export async function getBlob(url: string, signal?: AbortSignal): Promise<Blob> {
  const response = await fetch(url, { signal });
  await assertOk(response);
  return response.blob();
}

export async function putJson<TResponse, TBody>(
  url: string,
  body: TBody,
  signal?: AbortSignal,
): Promise<TResponse> {
  const response = await fetch(url, {
    body: JSON.stringify(body),
    headers: { 'content-type': 'application/json' },
    method: 'PUT',
    signal,
  });
  await assertOk(response);
  return response.json() as Promise<TResponse>;
}

export function buildApiUrl(
  path: string,
  params?: Record<string, string | number | null | undefined>,
) {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== null && value !== undefined && value !== '') {
      url.searchParams.set(key, String(value));
    }
  }
  return `${url.pathname}${url.search}`;
}

async function assertOk(response: Response): Promise<void> {
  if (response.ok) {
    return;
  }
  const body = await response.text();
  throw new ApiError(body || `${response.status} ${response.statusText}`, response);
}
