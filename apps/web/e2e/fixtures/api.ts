import { fileURLToPath } from "node:url";
import type { Page } from "@playwright/test";

/**
 * Synthetic API responses so the snapshots cover populated layouts, not just empty states.
 *
 * SYNTHETIC — NOT MEASUREMENTS. These are hand-written shapes, not pipeline output: they predate
 * the run and were never regenerated from it. Real measured figures live in RESULTS.md and
 * ml/evals/reports/, and they do not match these. Every value that could be mistaken for a result
 * carries `fixture` in the adjacent label, and prime directive 5 applies: none of these numbers
 * may be quoted in the README, the paper, a model card, or anywhere else. Their only job is to
 * give each page enough shape to render.
 *
 * These fixtures are **not** what the README's demo GIF shows. That recording populates the page
 * from here but overrides `/v1/tokenize/fertility` with real measured tokenizer output
 * (`scripts/capture-specimen.spec.ts`), because the Specimen's dash boundaries are a claim about
 * what a tokenizer did to a string — and `fertility.json`'s hand-written offsets are not that.
 * Its `jais-family` entry even inverts the finding, splitting the English words while leaving the
 * Arabic whole. Fine for exercising the layout; a lie if published.
 *
 * Without this, `/chat`, `/evals`, `/edge` and `/registry` only ever snapshot their empty
 * states — so a regression in a populated table, a heatmap or a streamed message would not
 * show up in CI at all.
 */

const FERTILITY = fileURLToPath(new URL("./fertility.json", import.meta.url));

const MODELS = {
  object: "list",
  data: [
    {
      id: "sanad-bank-awq",
      object: "model",
      x_sanad: {
        mode: "dev",
        upstream: "vllm",
        quant: "awq-w4a16",
        healthy: true,
        license: "Apache-2.0",
      },
    },
    {
      id: "sanad-bank-gguf",
      object: "model",
      x_sanad: {
        mode: "dev",
        upstream: "llamacpp",
        quant: "gguf-q4km",
        healthy: true,
        license: "Apache-2.0",
      },
    },
  ],
};

const EVAL_RUNS = [
  {
    id: "run-fixture-01",
    created_at: "2026-07-20T09:00:00Z",
    model_version: "fixture-only-not-a-real-run",
    headline: { domain_eval: 0.71, arabicmmlu: 0.58 },
  },
];

const EVAL_RUN_DETAIL = {
  id: "run-fixture-01",
  provenance_split: { native: 0.62, translated: 0.11, synthetic: 0.27 },
  benchmark_scores: [
    {
      task: "arabicmmlu",
      model: "fixture-base",
      metric: "acc",
      value: 0.55,
      measured_locally: true,
    },
    {
      task: "arabicmmlu",
      model: "fixture-sanad",
      metric: "acc",
      value: 0.58,
      measured_locally: true,
    },
    { task: "aratrust", model: "fixture-base", metric: "acc", value: 0.62, measured_locally: true },
    {
      task: "aratrust",
      model: "fixture-sanad",
      metric: "acc",
      value: 0.66,
      measured_locally: true,
    },
    {
      task: "madinahqa",
      model: "fixture-sanad",
      metric: "acc",
      value: 0.49,
      measured_locally: false,
    },
  ],
  judge: {
    headline_final: 3.9,
    correct_rate: 0.82,
    per_dimension: [
      { dimension: "completeness", score: 4.1 },
      { dimension: "conciseness", score: 3.6 },
      { dimension: "helpfulness", score: 4.0 },
      { dimension: "honesty", score: 4.2 },
      { dimension: "harmlessness", score: 4.7 },
    ],
    judges: ["falcon-h1-7b-fixture", "allam-7b-fixture"],
    human_judge_kappa: 0.68,
  },
  agreement: {
    krippendorff_alpha: { overall: 0.71, completeness: 0.66, conciseness: 0.58, honesty: 0.74 },
    pairwise_cohens_kappa: { "falcon-h1-7b-fixture|allam-7b-fixture": 0.63 },
    heatmap: [
      { judge: "falcon-h1-7b-fixture", dimension: "completeness", mean_abs_dev: 0.4 },
      { judge: "falcon-h1-7b-fixture", dimension: "conciseness", mean_abs_dev: 1.1 },
      { judge: "falcon-h1-7b-fixture", dimension: "helpfulness", mean_abs_dev: 0.6 },
      { judge: "allam-7b-fixture", dimension: "completeness", mean_abs_dev: 0.7 },
      { judge: "allam-7b-fixture", dimension: "conciseness", mean_abs_dev: 1.6 },
      { judge: "allam-7b-fixture", dimension: "helpfulness", mean_abs_dev: 0.5 },
    ],
    human_queue_count: 7,
  },
  efficiency: {
    ttft_ms: 210,
    tokens_per_second: 34.2,
    peak_vram_gb: 6.1,
    watts: 41.5,
    usd_per_1m_output_tokens: 0.0,
  },
};

const ARTIFACT = "sanad-qwen3-4b-bank-fixture";
const AWQ_VERSION = "v0.0.0-fixture";
const GGUF_VERSION = "v0.0.0-fixture-gguf";

const REGISTRY = {
  artifacts: [
    {
      model_name: ARTIFACT,
      version: AWQ_VERSION,
      sha256: "fixture00112233445566778899aabbccddeeff00112233445566778899aabbcc",
      cosign_signed: true,
      licenses: ["Apache-2.0", "CC-BY-4.0"],
      base_model: "Qwen/Qwen3-4B-Instruct-2507",
      created_at: "2026-07-20T09:30:00Z",
    },
    {
      model_name: ARTIFACT,
      version: GGUF_VERSION,
      sha256: null,
      cosign_signed: false,
      licenses: ["Apache-2.0"],
      base_model: "Qwen/Qwen3-4B-Instruct-2507",
      created_at: null,
    },
  ],
  lineage: {
    // LineageChain matches edges against `${model_name}@${version}`, so at least one edge must
    // terminate at that exact key or the lineage row renders nothing and the snapshot proves
    // only its absence. Both artifacts are wired in: the AWQ version receives base/data/config
    // and emits the GGUF one.
    nodes: [
      { id: "Qwen/Qwen3-4B-Instruct-2507", kind: "base" },
      { id: "data-manifest-fixture", kind: "dataset" },
      { id: "train-config-fixture", kind: "config" },
      { id: `${ARTIFACT}@${AWQ_VERSION}`, kind: "model", cosign_signed: true },
      { id: `${ARTIFACT}@${GGUF_VERSION}`, kind: "quant", cosign_signed: false },
    ],
    edges: [
      {
        from: "Qwen/Qwen3-4B-Instruct-2507",
        to: `${ARTIFACT}@${AWQ_VERSION}`,
        label: "qlora+dora",
      },
      { from: "data-manifest-fixture", to: `${ARTIFACT}@${AWQ_VERSION}`, label: "sft" },
      { from: "train-config-fixture", to: `${ARTIFACT}@${AWQ_VERSION}`, label: "config" },
      {
        from: `${ARTIFACT}@${AWQ_VERSION}`,
        to: `${ARTIFACT}@${GGUF_VERSION}`,
        label: "imatrix + Q4_K_M",
      },
    ],
  },
};

/** One telemetry frame, shaped like the API's snapshot payload. */
const TELEMETRY_FRAMES = [
  JSON.stringify({
    source: "fixture-edge",
    ts: "2026-07-20T09:31:00Z",
    watts: 38.4,
    temp_c: 54.2,
    gpu_util_pct: null,
    tokens_per_second: 12.6,
    mem_used_gb: 3.1,
  }),
  JSON.stringify({
    source: "fixture-edge",
    ts: "2026-07-20T09:31:05Z",
    watts: 41.9,
    temp_c: 56.8,
    gpu_util_pct: null,
    tokens_per_second: 13.1,
    mem_used_gb: 3.2,
  }),
];

/**
 * A bilingual assistant reply, chunked the way a real tokenizer stream chunks it.
 *
 * Delta 3 ends on the base letter ا and delta 4 opens with the combining fathatan (U+064B) that
 * belongs to it, so the stream splits a grapheme *mid-cluster*. That is the case GraphemeBuffer
 * exists for: without it the DOM briefly shows a bare combining mark hanging off the previous
 * word. Deltas that all break on spaces cannot exercise it — concatenation yields the same final
 * string either way, so a final-text assertion alone can never fail.
 */
export const CHAT_DELTAS = [
  "يخضع حساب التوفير ",
  "لمعدل فائدة سنوي ",
  "قدره 2.75% وفقا",
  "\u064B لتعليمات المصرف المركزي. ",
  "In short: 2.75% APR, ",
  "subject to CBUAE rules.",
] as const;

/** What the thread must read once the stream drains — byte-exact. */
export const CHAT_REPLY = CHAT_DELTAS.join("");

function sseFrames(): string[] {
  const chunks = CHAT_DELTAS.map((content) =>
    JSON.stringify({
      id: "chatcmpl-fixture",
      object: "chat.completion.chunk",
      choices: [{ index: 0, delta: { content }, finish_reason: null }],
    }),
  );
  const final = JSON.stringify({
    object: "sanad.final",
    x_sanad: {
      ttft_ms: 180,
      tokens_per_second: 33.4,
      detected_lang: "mixed",
      sovereign: false,
      upstream: "vllm",
    },
  });
  return [...chunks, final, "[DONE]"].map((c) => `data: ${c}\n\n`);
}

function chatStreamBody(): string {
  return sseFrames().join("");
}

/**
 * Deliver the chat stream frame by frame, with a gap between frames.
 *
 * `route.fulfill` can only send a *complete* response, so the reader drains every delta in one
 * pass and the UI never renders a partial reply — there is no intermediate state to inspect.
 * Stubbing fetch with a paced ReadableStream reproduces real streaming, which is what makes the
 * grapheme-boundary invariant observable. Also records every rendered state of the streaming
 * bubble (it carries aria-live while in flight) for the test to assert over.
 */
export async function installPacedChatStream(page: Page, frameGapMs = 70): Promise<void> {
  await page.addInitScript(
    ({ frames, gap }: { frames: string[]; gap: number }) => {
      const states: string[] = [];
      (window as unknown as { __streamStates: string[] }).__streamStates = states;

      // Install the stub before anything that could throw: init scripts run at document-start,
      // and an exception here would abort the rest of the script silently — leaving the fetch
      // stub uninstalled, the stream delivered in one shot, and no intermediate state to record.
      const original = window.fetch;
      window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === "string" ? input : input.toString();
        if (!url.includes("/v1/chat/completions")) return original(input, init);
        const encoder = new TextEncoder();
        const body = new ReadableStream({
          start(controller) {
            let i = 0;
            const push = () => {
              if (i >= frames.length) {
                controller.close();
                return;
              }
              controller.enqueue(encoder.encode(frames[i++]));
              setTimeout(push, gap);
            };
            setTimeout(push, gap);
          },
        });
        return Promise.resolve(
          new Response(body, {
            status: 200,
            headers: { "Content-Type": "text/event-stream" },
          }),
        );
      };

      // `document.documentElement` does not exist yet at document-start, so observe `document`
      // itself — always present, and subtree:true reaches the whole tree either way.
      const record = () => {
        const bubble = document.querySelector('[aria-live="polite"]');
        const text = bubble?.textContent ?? "";
        if (text && states[states.length - 1] !== text) states.push(text);
      };
      new MutationObserver(record).observe(document, {
        subtree: true,
        childList: true,
        characterData: true,
      });
    },
    { frames: sseFrames(), gap: frameGapMs },
  );
}

/**
 * Route every endpoint the dashboard reads.
 *
 * `/v1/telemetry/stream` is served by stubbing EventSource rather than by fulfilling the route:
 * a fulfilled response is a *complete* one, so the stream would close immediately, flip the page's
 * connected badge to false and trigger backoff reconnects — turning the snapshot into a race. The
 * stub stays open, which is what a real telemetry stream does. `subscribe()`'s own reconnect logic
 * is covered by unit tests, not here.
 */
export async function installApiFixtures(page: Page): Promise<void> {
  await page.route("**/v1/models", (route) => route.fulfill({ json: MODELS }));
  await page.route("**/v1/tokenize/fertility", (route) =>
    route.fulfill({ path: FERTILITY, contentType: "application/json" }),
  );
  await page.route("**/v1/eval/runs", (route) => route.fulfill({ json: EVAL_RUNS }));
  await page.route("**/v1/eval/runs/*", (route) => route.fulfill({ json: EVAL_RUN_DETAIL }));
  await page.route("**/v1/registry/artifacts", (route) => route.fulfill({ json: REGISTRY }));
  await page.route("**/v1/chat/completions", (route) =>
    route.fulfill({ contentType: "text/event-stream", body: chatStreamBody() }),
  );

  await page.addInitScript((frames: string[]) => {
    class StubEventSource {
      onopen: ((e: Event) => void) | null = null;
      onmessage: ((e: MessageEvent) => void) | null = null;
      onerror: ((e: Event) => void) | null = null;
      readyState = 1;
      constructor(public url: string) {
        setTimeout(() => {
          this.onopen?.(new Event("open"));
          for (const data of frames) {
            this.onmessage?.(new MessageEvent("message", { data }));
          }
        }, 0);
      }
      close(): void {
        this.readyState = 2;
      }
      addEventListener(): void {}
      removeEventListener(): void {}
    }
    (window as unknown as { EventSource: unknown }).EventSource = StubEventSource;
  }, TELEMETRY_FRAMES);
}
