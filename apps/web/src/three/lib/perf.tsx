import { useUiStore } from "@/store/ui";
/**
 * Shared scene hygiene (§8.4): every scene renders inside SceneFrame — dpr [1,2],
 * frameloop="demand" (invalidate during animation), AdaptiveDpr + PerformanceMonitor
 * degrade quality before dropping frames, and a static poster fallback for
 * no-WebGL / reduced-motion / low-tier mobile.
 */
import { AdaptiveDpr, PerformanceMonitor } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { type ReactNode, useState } from "react";
import { useTranslation } from "react-i18next";

export function webglAvailable(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") ?? canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

export function Poster({ label, children }: { label: string; children?: ReactNode }) {
  const { t } = useTranslation();
  return (
    <div
      role="img"
      aria-label={label}
      className="panel relative flex h-full min-h-64 w-full items-center justify-center overflow-hidden bg-[radial-gradient(ellipse_at_30%_20%,#1a2438_0%,#0E1420_70%)]"
    >
      <div className="text-center text-sand-400 text-sm p-6">
        {children ?? t("poster.webglMissing")}
      </div>
    </div>
  );
}

export interface SceneFrameProps {
  /** Text alternative for the canvas (§8.7 a11y). */
  label: string;
  children: ReactNode;
  poster?: ReactNode;
  camera?: { position: [number, number, number]; fov?: number };
  /** Scenes with continuous animation set this true; others render on demand. */
  animated?: boolean;
  className?: string;
}

export function SceneFrame({
  label,
  children,
  poster,
  camera,
  animated,
  className,
}: SceneFrameProps) {
  const reducedMotion = useUiStore((s) => s.reducedMotion);
  const [degraded, setDegraded] = useState(false);

  if (reducedMotion || !webglAvailable()) {
    return <Poster label={label}>{poster}</Poster>;
  }

  return (
    <div className={className ?? "h-full w-full"} aria-label={label} role="img">
      <Canvas
        dpr={degraded ? 1 : [1, 2]}
        frameloop={animated ? "always" : "demand"}
        camera={camera ?? { position: [0, 0, 8], fov: 45 }}
        gl={{ antialias: true, powerPreference: "high-performance" }}
      >
        <PerformanceMonitor onDecline={() => setDegraded(true)}>
          <AdaptiveDpr pixelated />
          {children}
        </PerformanceMonitor>
      </Canvas>
    </div>
  );
}
