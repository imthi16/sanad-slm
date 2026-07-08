import { textDirection } from "@/lib/bidi";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";

export interface Message {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  stats?: { ttft_ms?: number; tokens_per_second?: number; detected_lang?: string };
}

export function ChatMessage({ message }: { message: Message }) {
  const { t } = useTranslation();
  const dir = textDirection(message.content); // dir per message (§8.6)
  const isUser = message.role === "user";
  return (
    <div className={clsx("flex flex-col gap-1", isUser ? "items-end" : "items-start")}>
      <span className="text-xs text-sand-400">{isUser ? t("chat.you") : t("chat.assistant")}</span>
      <div
        dir={dir}
        lang={dir === "rtl" ? "ar" : "en"}
        aria-live={message.streaming ? "polite" : undefined}
        className={clsx(
          "panel max-w-[75%] whitespace-pre-wrap px-4 py-3 text-sm leading-relaxed",
          isUser ? "border-brass-400/30" : "border-dune-700",
        )}
      >
        {/* mixed-script inline content stays isolated (§8.6) */}
        <span className="bidi-isolate">{message.content}</span>
        {message.streaming && <span className="animate-pulse text-brass-400">▍</span>}
      </div>
      {message.stats && !message.streaming && (
        <span className="text-xs text-sand-400" dir="ltr">
          {t("chat.ttft")} <span className="metric">{message.stats.ttft_ms ?? "—"}ms</span>
          {" · "}
          <span className="metric">{message.stats.tokens_per_second ?? "—"}</span>{" "}
          {t("chat.tokensPerSec")}
        </span>
      )}
    </div>
  );
}
