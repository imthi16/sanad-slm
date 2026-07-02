import { postJson } from "@/lib/http";
import { type FertilityResponse, type TokenizerName, useTokenizerStore } from "@/store/tokenizer";
/**
 * useTokenClusters (§8.4a): fetches /v1/tokenize/fertility for the current sentence and maps
 * each atlas unit to its token cluster's target position + color. On tokenizer switch the
 * particles regroup — teal clusters for Arabic tokens, sand for English.
 */
import { useMutation } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";
import * as THREE from "three";
import type { AtlasEntry } from "./glyphAtlas";

export const COLOR_AR = new THREE.Color("#1FA79B"); // teal-400: Arabic tokens
export const COLOR_EN = new THREE.Color("#B9AC93"); // sand-400: English tokens

export interface ClusterTargets {
  /** one target position per atlas entry */
  positions: Float32Array;
  /** one rgb per atlas entry (cluster color by script) */
  colors: Float32Array;
  tokens: number;
  tokensPerWord: number;
  costVsBest: number | null;
}

/** Scatter layout: sentence laid out as one line, direction-aware, before clustering. */
export function baselinePositions(entries: AtlasEntry[], sentence: string): Float32Array {
  const positions = new Float32Array(entries.length * 3);
  const total = sentence.length || 1;
  const span = 10;
  const rtl = /[؀-ۿ]/.test(sentence);
  entries.forEach((e, i) => {
    const mid = (e.start + e.end) / 2 / total; // 0..1 along the sentence
    const x = (rtl ? 1 - mid : mid) * span - span / 2;
    positions[i * 3] = x;
    positions[i * 3 + 1] = 0;
    positions[i * 3 + 2] = 0;
  });
  return positions;
}

/** Deterministic cluster centers on a gentle spiral — stable across re-renders. */
function clusterCenter(index: number, count: number): [number, number, number] {
  const golden = 2.399963;
  const r = 1.6 + 2.6 * Math.sqrt((index + 0.5) / Math.max(count, 1));
  const theta = index * golden;
  return [r * Math.cos(theta), 0.9 * Math.sin(theta * 1.7), -0.5 + (index % 3) * 0.5];
}

export function computeTargets(
  entries: AtlasEntry[],
  sentence: string,
  result: FertilityResponse | null,
  tokenizer: TokenizerName,
): ClusterTargets {
  const positions = baselinePositions(entries, sentence);
  const colors = new Float32Array(entries.length * 3);
  entries.forEach((e, i) => {
    const c = e.script === "ar" ? COLOR_AR : COLOR_EN;
    colors[i * 3] = c.r;
    colors[i * 3 + 1] = c.g;
    colors[i * 3 + 2] = c.b;
  });

  const tok = result?.tokenizers[tokenizer];
  if (!tok) {
    return { positions, colors, tokens: 0, tokensPerWord: 0, costVsBest: null };
  }

  const segs = tok.segments;
  entries.forEach((entry, i) => {
    // the token cluster this unit belongs to = segment covering its char midpoint
    const mid = (entry.start + entry.end) / 2;
    const segIndex = segs.findIndex((s) => mid >= s.start && mid < s.end);
    const seg = segIndex >= 0 ? segs[segIndex] : undefined;
    const [cx, cy, cz] = clusterCenter(segIndex >= 0 ? segIndex : 0, segs.length);
    // deterministic jitter inside the cluster so units don't stack
    const j = i * 0.618;
    positions[i * 3] = cx + 0.45 * Math.cos(j * 7);
    positions[i * 3 + 1] = cy + 0.3 * Math.sin(j * 5);
    positions[i * 3 + 2] = cz + 0.25 * Math.sin(j * 3);
    const color = seg?.script === "ar" ? COLOR_AR : seg?.script === "en" ? COLOR_EN : COLOR_EN;
    colors[i * 3] = color.r;
    colors[i * 3 + 1] = color.g;
    colors[i * 3 + 2] = color.b;
  });

  return {
    positions,
    colors,
    tokens: tok.tokens,
    tokensPerWord: tok.tokens_per_word,
    costVsBest: tok.cost_vs_best ?? null,
  };
}

/** Fetch fertility for the store's sentence (debounced by caller), keep store in sync. */
export function useFertility(): { measure: (text: string) => void; loading: boolean } {
  const setResult = useTokenizerStore((s) => s.setResult);
  const setLoading = useTokenizerStore((s) => s.setLoading);
  const text = useTokenizerStore((s) => s.text);

  const mutation = useMutation({
    mutationFn: (t: string) => postJson<FertilityResponse>("/v1/tokenize/fertility", { text: t }),
    onMutate: () => setLoading(true),
    onSuccess: (data) => setResult(data),
    onError: () => setResult(null),
  });

  // biome-ignore lint/correctness/useExhaustiveDependencies: fire once on mount with the initial sentence; later measurements go through `measure`
  useEffect(() => {
    mutation.mutate(text);
  }, []);

  return useMemo(
    () => ({ measure: (t: string) => mutation.mutate(t), loading: mutation.isPending }),
    [mutation],
  );
}
