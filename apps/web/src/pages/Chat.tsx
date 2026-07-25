import { ChatMessage, type Message } from "@/components/chat/ChatMessage";
import { Button } from "@/components/ui";
import { GraphemeBuffer } from "@/lib/bidi";
import { getJson } from "@/lib/http";
import { streamChat } from "@/lib/sse";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

interface ModelsResponse {
  data: Array<{ id: string; x_sanad?: { healthy?: boolean } }>;
}

export default function Chat() {
  const { t } = useTranslation();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [model, setModel] = useState("sanad-bank-awq");
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const models = useQuery({
    queryKey: ["models"],
    queryFn: () => getJson<ModelsResponse>("/v1/models"),
    staleTime: 30_000,
  });

  // don't leave the picker on a dead upstream when a healthy one exists
  useEffect(() => {
    const list = models.data?.data;
    if (!list?.length) return;
    const healthy = (id: string) => list.find((m) => m.id === id)?.x_sanad?.healthy;
    if (!healthy(model)) {
      const firstHealthy = list.find((m) => m.x_sanad?.healthy);
      if (firstHealthy) setModel(firstHealthy.id);
    }
  }, [models.data, model]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: `messages` is the trigger — scroll to the newest message whenever the list changes
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  const send = async () => {
    const prompt = input.trim();
    if (!prompt || busy) return;
    setInput("");
    setBusy(true);

    const history = [...messages, { role: "user" as const, content: prompt }];
    setMessages([...history, { role: "assistant", content: "", streaming: true }]);

    // grapheme-safe streaming: never tear Arabic ligatures (§8.6)
    const buffer = new GraphemeBuffer();
    const append = (safe: string) => {
      if (!safe) return;
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last?.streaming) next[next.length - 1] = { ...last, content: last.content + safe };
        return next;
      });
    };

    abortRef.current = new AbortController();
    await streamChat(
      "/v1/chat/completions",
      {
        model,
        stream: true,
        messages: history.map(({ role, content }) => ({ role, content })),
      },
      {
        onDelta: (delta) => append(buffer.push(delta)),
        onFinal: (x) => {
          append(buffer.flush());
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last?.streaming) {
              next[next.length - 1] = {
                ...last,
                streaming: false,
                stats: {
                  ttft_ms: x.ttft_ms as number | undefined,
                  tokens_per_second: x.tokens_per_second as number | undefined,
                  detected_lang: x.detected_lang as string | undefined,
                },
              };
            }
            return next;
          });
        },
        onError: () => {
          append(buffer.flush());
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last?.streaming) {
              next[next.length - 1] = {
                ...last,
                streaming: false,
                content: last.content || `⚠ ${t("chat.streamError")}`,
              };
            }
            return next;
          });
        },
        onDone: () => {
          append(buffer.flush());
          setMessages((prev) => prev.map((m) => (m.streaming ? { ...m, streaming: false } : m)));
          setBusy(false);
        },
      },
      abortRef.current.signal,
    );
    setBusy(false);
  };

  const stop = () => {
    abortRef.current?.abort();
    setBusy(false);
  };

  return (
    <div className="mx-auto flex h-[calc(100dvh-8.5rem)] max-w-4xl flex-col gap-3 p-4">
      <div className="flex items-center justify-between gap-3">
        <h1 className="font-display text-2xl">{t("chat.title")}</h1>
        <label className="flex items-center gap-2 text-sm text-sand-400">
          {t("chat.model")}
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="rounded-md border border-ink-700 bg-ink-900 px-2 py-1.5 text-sand-100"
            dir="ltr"
          >
            {(models.data?.data ?? [{ id: "sanad-bank-awq" }]).map((m) => (
              <option key={m.id} value={m.id}>
                {m.id}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div ref={scrollRef} className="panel flex-1 space-y-4 overflow-y-auto p-4">
        {messages.map((m, i) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: append-only list
          <ChatMessage key={i} message={m} />
        ))}
      </div>

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <input
          dir="auto"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t("chat.placeholder")}
          aria-label={t("chat.placeholder")}
          className="flex-1 rounded-md border border-ink-700 bg-ink-900 px-3 py-2.5 text-sm
                     text-sand-100 placeholder:text-sand-400/60"
        />
        {busy ? (
          <Button variant="danger" onClick={stop}>
            {t("chat.stop")}
          </Button>
        ) : (
          <Button type="submit" disabled={!input.trim()}>
            {t("chat.send")}
          </Button>
        )}
      </form>
    </div>
  );
}
