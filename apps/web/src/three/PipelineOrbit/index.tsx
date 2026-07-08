/**
 * PipelineOrbit — architecture as space (§8.4b, Home section 2).
 * Five translucent panels (Data → QLoRA → Quantize → Eval → Edge) orbit a slowly rotating
 * core; ScrollControls scrubs the camera along the arc; clicking a panel routes to its page.
 * Labels via drei <Text> (troika) in both scripts.
 */
import arabicFontUrl from "@fontsource/ibm-plex-sans-arabic/files/ibm-plex-sans-arabic-arabic-400-normal.woff?url";
import latinFontUrl from "@fontsource/space-grotesk/files/space-grotesk-latin-400-normal.woff?url";
import { ScrollControls, Text, useScroll } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import * as THREE from "three";
import { SceneFrame } from "../lib/perf";

// Self-hosted woffs for troika <Text> — without an explicit `font`, troika resolves fallback
// glyph data from cdn.jsdelivr.net at runtime, which breaks the air gap (prime directive 1).

interface Station {
  key: string;
  route: string;
}

const STATIONS: Station[] = [
  { key: "pipeline.data", route: "/registry" },
  { key: "pipeline.qlora", route: "/evals" },
  { key: "pipeline.quantize", route: "/registry" },
  { key: "pipeline.eval", route: "/evals" },
  { key: "pipeline.edge", route: "/edge" },
];

function Core() {
  const ref = useRef<THREE.Mesh>(null);
  useFrame((_, delta) => {
    if (ref.current) ref.current.rotation.y += delta * 0.15;
  });
  return (
    <mesh ref={ref}>
      <icosahedronGeometry args={[0.9, 1]} />
      <meshStandardMaterial color="#26324A" emissive="#C9A227" emissiveIntensity={0.12} wireframe />
    </mesh>
  );
}

function PanelStation({ station, index }: { station: Station; index: number }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const group = useRef<THREE.Group>(null);
  const angle = (index / STATIONS.length) * Math.PI * 2;
  const radius = 3.4;

  const position = useMemo<[number, number, number]>(
    () => [Math.sin(angle) * radius, Math.sin(index * 1.3) * 0.4, Math.cos(angle) * radius],
    [angle, index],
  );

  useFrame(({ camera }) => {
    group.current?.lookAt(camera.position);
  });

  const isArabic = i18n.language === "ar";
  return (
    <group ref={group} position={position}>
      {/* biome-ignore lint/a11y/useKeyWithClickEvents: R3F <mesh> is a WebGL object, not DOM;
          keyboard users reach every route via the header nav — the 3D panel is supplementary */}
      <mesh
        onClick={() => navigate(station.route)}
        onPointerOver={(e) => {
          e.stopPropagation();
          document.body.style.cursor = "pointer";
        }}
        onPointerOut={() => {
          document.body.style.cursor = "auto";
        }}
      >
        <planeGeometry args={[1.9, 1.1]} />
        {/* translucent standard material — MeshTransmission is over the GPU budget here (§8.4b) */}
        <meshStandardMaterial
          color="#141C2B"
          transparent
          opacity={0.72}
          roughness={0.35}
          metalness={0.15}
          side={THREE.DoubleSide}
        />
      </mesh>
      <Text
        position={[0, 0.12, 0.01]}
        fontSize={0.26}
        color="#EDE4D3"
        anchorX="center"
        anchorY="middle"
        direction={isArabic ? "rtl" : "ltr"}
        font={isArabic ? arabicFontUrl : latinFontUrl}
      >
        {t(station.key)}
      </Text>
      <Text
        position={[0, -0.24, 0.01]}
        fontSize={0.13}
        color="#C9A227"
        anchorX="center"
        anchorY="middle"
        font={latinFontUrl}
      >
        {`0${index + 1}`}
      </Text>
    </group>
  );
}

function OrbitRig() {
  const scroll = useScroll();
  useFrame(({ camera }) => {
    // scrub the camera along the arc with scroll (§8.4b)
    const t = scroll.offset * Math.PI * 1.6;
    const r = 7.5;
    camera.position.set(Math.sin(t) * r, 1.4 - scroll.offset, Math.cos(t) * r);
    camera.lookAt(0, 0, 0);
  });
  return null;
}

function OrbitContents() {
  return (
    <ScrollControls pages={2} damping={0.2}>
      <ambientLight intensity={0.5} />
      <pointLight position={[4, 4, 4]} intensity={40} color="#EDE4D3" />
      <Core />
      {STATIONS.map((s, i) => (
        <PanelStation key={s.key} station={s} index={i} />
      ))}
      <OrbitRig />
    </ScrollControls>
  );
}

export function PipelineOrbit({ label }: { label: string }) {
  return (
    <SceneFrame label={label} animated camera={{ position: [0, 1.4, 7.5], fov: 45 }}>
      <OrbitContents />
    </SceneFrame>
  );
}
