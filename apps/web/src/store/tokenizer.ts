/**
 * DOM ⇄ Canvas bridge for the FertilityField hero (§8.4a): the tokenizer pills and text
 * input live in the DOM; the 3D scene subscribes to this store for regroup targets.
 */
import { create } from "zustand";

export interface TokenSegment {
  id: number;
  start: number;
  end: number;
  text: string;
  script: "ar" | "en" | "mixed";
}

export interface TokenizerResult {
  tokens: number;
  tokens_per_word: number;
  cost_vs_best?: number;
  segments: TokenSegment[];
}

export interface FertilityResponse {
  text_words: number;
  detected_lang: string;
  tokenizers: Record<string, TokenizerResult>;
}

export const DEFAULT_SENTENCE =
  "يخضع حساب التوفير لمعدل فائدة سنوي قدره 2.75% subject to CBUAE regulations";

export const TOKENIZER_ORDER = ["qwen3", "jais-family", "allam", "falcon-h1", "llama-3.2"] as const;
export type TokenizerName = (typeof TOKENIZER_ORDER)[number];

interface TokenizerState {
  text: string;
  selected: TokenizerName;
  result: FertilityResponse | null;
  loading: boolean;
  setText: (text: string) => void;
  select: (name: TokenizerName) => void;
  setResult: (result: FertilityResponse | null) => void;
  setLoading: (loading: boolean) => void;
}

export const useTokenizerStore = create<TokenizerState>((set) => ({
  text: DEFAULT_SENTENCE,
  selected: "qwen3",
  result: null,
  loading: false,
  setText: (text) => set({ text }),
  select: (selected) => set({ selected }),
  setResult: (result) => set({ result, loading: false }),
  setLoading: (loading) => set({ loading }),
}));
