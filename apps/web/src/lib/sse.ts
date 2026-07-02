/**
 * SSE helpers (§3.3: SSE > WebSockets for one-way token streams).
 *
 * - streamChat: POST-based SSE over fetch (EventSource can't POST) for /v1/chat/completions.
 * - subscribe: GET EventSource with exponential backoff for /v1/telemetry/stream.
 */

export interface ChatStreamHandlers {
  onDelta: (text: string) => void;
  onFinal?: (xSanad: Record<string, unknown>) => void;
  onError?: (message: string) => void;
  onDone?: () => void;
}

export async function streamChat(
  url: string,
  body: unknown,
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) {
    handlers.onError?.(`upstream ${response.status}`);
    return;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const data = line.slice(6).trim();
        if (data === "[DONE]") {
          handlers.onDone?.();
          return;
        }
        try {
          const parsed = JSON.parse(data);
          if (parsed.object === "sanad.final") {
            handlers.onFinal?.(parsed.x_sanad);
          } else {
            const delta: string | undefined = parsed.choices?.[0]?.delta?.content;
            if (delta) handlers.onDelta(delta);
          }
        } catch {
          // ignore non-JSON keepalives
        }
      }
    }
    handlers.onDone?.();
  } catch (err) {
    if ((err as Error).name !== "AbortError") {
      handlers.onError?.((err as Error).message);
    }
  }
}

export interface Subscription {
  close: () => void;
}

/** EventSource with exponential backoff reconnect (EdgeBoard telemetry, §8.4c). */
export function subscribe(
  url: string,
  onMessage: (data: string) => void,
  onStatus?: (connected: boolean) => void,
): Subscription {
  let source: EventSource | null = null;
  let attempt = 0;
  let closed = false;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const connect = () => {
    if (closed) return;
    source = new EventSource(url);
    source.onopen = () => {
      attempt = 0;
      onStatus?.(true);
    };
    source.onmessage = (e) => onMessage(e.data);
    source.onerror = () => {
      onStatus?.(false);
      source?.close();
      const delay = Math.min(30_000, 1000 * 2 ** attempt++);
      timer = setTimeout(connect, delay);
    };
  };
  connect();

  return {
    close: () => {
      closed = true;
      if (timer) clearTimeout(timer);
      source?.close();
    },
  };
}
