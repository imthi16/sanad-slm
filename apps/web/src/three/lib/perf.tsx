import { useUiStore } from "@/store/ui";
/**
 * Shared scene hygiene (§8.4): every scene renders inside SceneFrame — dpr [1,2],
 * frameloop="demand" (invalidate during animation), AdaptiveDpr + PerformanceMonitor
 * degrade quality before dropping frames, and a static poster fallback for
 * no-WebGL / reduced-motion / low-tier mobile.
 */
import { AdaptiveDpr, PerformanceMonitor } from "@react-three/drei";
import { Canvas, useThree } from "@react-three/fiber";
import { EffectComposer } from "@react-three/postprocessing";
import { Component, type ReactNode, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

// Probe once per page load and release the probe context immediately: browsers cap live
// WebGL contexts (~16/page) and evict the OLDEST — probing on every render floods the pool
// and silently kills the real scene contexts (blank canvas, later null getContextAttributes).
let webglProbe: boolean | null = null;

export function webglAvailable(): boolean {
  if (webglProbe !== null) return webglProbe;
  try {
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("webgl2") ?? canvas.getContext("webgl");
    // A context can exist yet be lost/software-dead — it then reports null attributes.
    webglProbe = Boolean(ctx?.getContextAttributes());
    ctx?.getExtension("WEBGL_lose_context")?.loseContext();
  } catch {
    webglProbe = false;
  }
  return webglProbe;
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

/**
 * Postprocessing wrapper: EffectComposer reads the context attributes during init and
 * crashes on lost/software/mid-remount contexts (null attributes). Mount it one commit
 * late, once the live context verifiably has attributes; skip effects otherwise — the
 * raw scene still renders.
 */
export function PostFX({ children }: { children: ReactNode }) {
  const gl = useThree((s) => s.gl);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let ok = false;
    try {
      ok = Boolean(gl.getContext()?.getContextAttributes());
    } catch {
      ok = false;
    }
    setReady(ok);
  }, [gl]);
  if (!ready) return null;
  return <EffectComposer>{children as React.JSX.Element}</EffectComposer>;
}

/** True once document.fonts.ready resolves — gate canvas-rasterized text on this. */
export function useFontsReady(): boolean {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let alive = true;
    document.fonts.ready.then(() => {
      if (alive) setReady(true);
    });
    return () => {
      alive = false;
    };
  }, []);
  return ready;
}

interface BoundaryProps {
  fallback: ReactNode;
  children: ReactNode;
}

/** Any scene crash (context loss mid-flight, shader failure) degrades to the poster. */
class SceneErrorBoundary extends Component<BoundaryProps, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }

  override render(): ReactNode {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
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
    <SceneErrorBoundary fallback={<Poster label={label}>{poster}</Poster>}>
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
    </SceneErrorBoundary>
  );
}
