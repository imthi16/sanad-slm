/**
 * Bootstrap fetch helpers used until `just api-types` generates the typed client into
 * src/lib/api/ (which then owns all request/response types — never hand-written, §8.5).
 */

export class ApiError extends Error {
  constructor(
    public status: number,
    public title: string,
  ) {
    super(`${status}: ${title}`);
  }
}

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(path, { signal });
  if (!r.ok) {
    const problem = await r.json().catch(() => ({ title: r.statusText }));
    throw new ApiError(r.status, problem.title ?? r.statusText);
  }
  return r.json() as Promise<T>;
}

export async function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!r.ok) {
    const problem = await r.json().catch(() => ({ title: r.statusText }));
    throw new ApiError(r.status, problem.title ?? r.statusText);
  }
  return r.json() as Promise<T>;
}
