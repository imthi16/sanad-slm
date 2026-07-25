import { formatMetric } from "@/lib/format";
import { useUiStore } from "@/store/ui";
/**
 * EdgeBoard — live telemetry (§8.4c). A low-poly edge board whose emissive heat
 * follows live watts from /v1/telemetry/stream. Gauges are drei <Html> overlays so numbers
 * stay crisp and accessible. (A draco glTF ≤300 KB can replace the procedural board later —
 * same props.)
 */
import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import { useTranslation } from "react-i18next";
import type * as THREE from "three";
import { SceneFrame } from "../lib/perf";

export interface EdgeMetrics {
  watts: number | null;
  temp_c: number | null;
  gpu_util_pct: number | null;
  tokens_per_second: number | null;
}

const IDLE_W = 5;
const MAX_W = 25; // small-edge-box envelope; heat glow normalizes into this range

function Board({ metrics }: { metrics: EdgeMetrics }) {
  const heatRef = useRef<THREE.MeshStandardMaterial>(null);
  const fanRef = useRef<THREE.Mesh>(null);

  useFrame((_, delta) => {
    const watts = metrics.watts ?? IDLE_W;
    const heat = Math.min(1, Math.max(0, (watts - IDLE_W) / (MAX_W - IDLE_W)));
    if (heatRef.current) {
      // lerp emissive toward the live heat level — verdigris→cinnabar as it warms
      heatRef.current.emissiveIntensity +=
        (0.2 + heat * 1.6 - heatRef.current.emissiveIntensity) * 0.08;
      heatRef.current.emissive.setRGB(0.79, 0.64 - heat * 0.35, 0.15 - heat * 0.05);
    }
    if (fanRef.current) {
      fanRef.current.rotation.z += delta * (2 + ((metrics.gpu_util_pct ?? 0) / 100) * 18);
    }
  });

  return (
    <group rotation={[-0.5, 0.5, 0]}>
      {/* PCB */}
      <mesh position={[0, 0, 0]}>
        <boxGeometry args={[3.4, 0.08, 2.2]} />
        <meshStandardMaterial color="#0E3B2E" roughness={0.8} />
      </mesh>
      {/* SoC + heat spreader — the glow element */}
      <mesh position={[0, 0.22, 0]}>
        <boxGeometry args={[1.4, 0.35, 1.4]} />
        <meshStandardMaterial
          ref={heatRef}
          color="#3A3229"
          emissive="#3FBFA4"
          emissiveIntensity={0.2}
          roughness={0.4}
          metalness={0.6}
        />
      </mesh>
      {/* fan */}
      <mesh ref={fanRef} position={[0, 0.42, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[0.55, 5]} />
        <meshStandardMaterial color="#1F1A15" roughness={0.5} side={2} />
      </mesh>
      {/* port block + module edge */}
      <mesh position={[-1.45, 0.18, 0.6]}>
        <boxGeometry args={[0.5, 0.28, 0.9]} />
        <meshStandardMaterial color="#8A8F98" metalness={0.7} roughness={0.3} />
      </mesh>
      <mesh position={[0.9, 0.14, -0.7]}>
        <boxGeometry args={[1.4, 0.2, 0.5]} />
        <meshStandardMaterial color="#1A1510" roughness={0.6} />
      </mesh>
    </group>
  );
}

function Gauge({
  label,
  value,
  unit,
  max,
}: { label: string; value: number | null; unit: string; max: number }) {
  const lang = useUiStore((s) => s.lang);
  const numerals = useUiStore((s) => s.numerals);
  const angle = -120 + Math.min(1, Math.max(0, (value ?? 0) / max)) * 240;
  return (
    <div className="panel flex w-28 flex-col items-center gap-1 p-2 text-center">
      {/* decorative needle — the live value is announced by the aria-live span below */}
      <svg viewBox="0 0 100 60" className="w-20" aria-hidden="true" role="presentation">
        <title>{label}</title>
        <path d="M10 55 A45 45 0 0 1 90 55" fill="none" stroke="#3A3229" strokeWidth="6" />
        <line
          x1="50"
          y1="55"
          x2={50 + 38 * Math.cos(((angle - 90) * Math.PI) / 180)}
          y2={55 + 38 * Math.sin(((angle - 90) * Math.PI) / 180)}
          stroke="#3FBFA4"
          strokeWidth="3"
          strokeLinecap="round"
        />
      </svg>
      <span className="metric text-sm" aria-live="polite">
        {formatMetric(value, lang, numerals)}
        <span className="text-xs text-sand-400 ms-1">{unit}</span>
      </span>
      <span className="text-xs text-sand-400">{label}</span>
    </div>
  );
}

function BoardScene({ metrics }: { metrics: EdgeMetrics }) {
  const { t } = useTranslation();
  return (
    <>
      <ambientLight intensity={0.45} />
      <directionalLight position={[3, 5, 2]} intensity={2.2} color="#F4ECDD" />
      <Board metrics={metrics} />
      <Html position={[0, -1.7, 0]} center transform={false} wrapperClass="pointer-events-none">
        <div className="pointer-events-auto flex gap-3" dir="ltr">
          <Gauge
            label={t("edge.tokensPerSec")}
            value={metrics.tokens_per_second}
            unit=""
            max={40}
          />
          <Gauge label={t("edge.temp")} value={metrics.temp_c} unit="°C" max={90} />
          <Gauge label={t("edge.watts")} value={metrics.watts} unit="W" max={MAX_W} />
        </div>
      </Html>
    </>
  );
}

export function EdgeBoard({ label, metrics }: { label: string; metrics: EdgeMetrics }) {
  return (
    <SceneFrame label={label} animated camera={{ position: [0, 1.2, 5.2], fov: 42 }}>
      <BoardScene metrics={metrics} />
    </SceneFrame>
  );
}
