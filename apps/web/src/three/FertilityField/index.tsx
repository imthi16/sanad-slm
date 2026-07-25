import { useTokenizerStore } from "@/store/tokenizer";
/**
 * FertilityField — hero + working demo (§8.4a, the signature element).
 *
 * A real bilingual sentence renders as glyph-particles (instanced quads over a DOM-shaped
 * canvas atlas — ligatures stay correct). On tokenizer switch the particles lerp into token
 * clusters: paper-cream = Arabic tokens, pewter = Latin. One draw call per script; ≤1200 instances;
 * custom shader does the position lerp + cluster color. Drag to orbit (damped), scroll passes
 * through. The DOM HUD/pills live in the page (zustand bridges DOM ⇄ Canvas).
 */
import { useFrame, useThree } from "@react-three/fiber";
import { Bloom, Vignette } from "@react-three/postprocessing";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { type GlyphAtlas, buildAtlas } from "../lib/glyphAtlas";
import { PostFX, SceneFrame, useFontsReady } from "../lib/perf";
import { baselinePositions, computeTargets } from "../lib/useTokenClusters";

const VERT = /* glsl */ `
attribute vec3 startPosition;
attribute vec3 targetPosition;
attribute vec3 clusterColor;
attribute vec4 uvRect;    // u0 v0 u1 v1
attribute vec2 unitSize;
uniform float uProgress;  // 0 = sentence line, 1 = clustered
uniform float uTime;
varying vec2 vUv;
varying vec3 vColor;

float easeOut(float t) { return 1.0 - pow(1.0 - t, 3.0); }

void main() {
  float t = easeOut(uProgress);
  vec3 base = mix(startPosition, targetPosition, t);
  // gentle idle drift so the field feels alive (collapses via uTime freeze on reduced motion)
  base.y += 0.05 * sin(uTime * 0.8 + startPosition.x * 2.0);
  vec3 local = position * vec3(unitSize, 1.0);
  vec4 world = modelMatrix * vec4(base, 1.0);
  // billboard: face the camera
  vec3 camRight = vec3(viewMatrix[0][0], viewMatrix[1][0], viewMatrix[2][0]);
  vec3 camUp    = vec3(viewMatrix[0][1], viewMatrix[1][1], viewMatrix[2][1]);
  world.xyz += camRight * local.x + camUp * local.y;
  gl_Position = projectionMatrix * viewMatrix * world;
  vUv = vec2(mix(uvRect.x, uvRect.z, uv.x), mix(uvRect.y, uvRect.w, uv.y));
  vColor = clusterColor;
}
`;

const FRAG = /* glsl */ `
uniform sampler2D uAtlas;
varying vec2 vUv;
varying vec3 vColor;
void main() {
  float a = texture2D(uAtlas, vUv).a;
  if (a < 0.05) discard;
  gl_FragColor = vec4(vColor, a);
}
`;

function ScriptField({ atlas, sentence }: { atlas: GlyphAtlas; sentence: string }) {
  const meshRef = useRef<THREE.Mesh>(null);
  const progress = useRef(0);
  const selected = useTokenizerStore((s) => s.selected);
  const result = useTokenizerStore((s) => s.result);

  const { geometry, material, uniforms } = useMemo(() => {
    const entries = atlas.entries;
    const plane = new THREE.PlaneGeometry(1, 1);
    const geo = new THREE.InstancedBufferGeometry();
    geo.index = plane.index;
    geo.setAttribute("position", plane.getAttribute("position"));
    geo.setAttribute("uv", plane.getAttribute("uv"));
    geo.instanceCount = entries.length;

    const starts = baselinePositions(entries, sentence);
    geo.setAttribute("startPosition", new THREE.InstancedBufferAttribute(starts, 3));
    geo.setAttribute("targetPosition", new THREE.InstancedBufferAttribute(starts.slice(), 3));
    const colors = new Float32Array(entries.length * 3).fill(0.8);
    geo.setAttribute("clusterColor", new THREE.InstancedBufferAttribute(colors, 3));
    const rects = new Float32Array(entries.length * 4);
    const sizes = new Float32Array(entries.length * 2);
    entries.forEach((e, i) => {
      rects.set([e.u0, e.v0, e.u1, e.v1], i * 4);
      sizes.set([e.width, e.height], i * 2);
    });
    geo.setAttribute("uvRect", new THREE.InstancedBufferAttribute(rects, 4));
    geo.setAttribute("unitSize", new THREE.InstancedBufferAttribute(sizes, 2));

    // typed handle onto the shader uniforms — avoids indexing three's IUniform map
    const sceneUniforms = {
      uAtlas: { value: atlas.texture },
      uProgress: { value: 0 },
      uTime: { value: 0 },
    };
    const mat = new THREE.ShaderMaterial({
      vertexShader: VERT,
      fragmentShader: FRAG,
      uniforms: sceneUniforms,
      transparent: true,
      depthWrite: false,
    });
    return { geometry: geo, material: mat, uniforms: sceneUniforms };
  }, [atlas, sentence]);

  useEffect(
    () => () => {
      geometry.dispose();
      material.dispose();
    },
    [geometry, material],
  );

  // regroup on tokenizer switch / new measurement
  useEffect(() => {
    const targets = computeTargets(atlas.entries, sentence, result, selected);
    const tp = geometry.getAttribute("targetPosition") as THREE.InstancedBufferAttribute;
    const cc = geometry.getAttribute("clusterColor") as THREE.InstancedBufferAttribute;
    (tp.array as Float32Array).set(targets.positions);
    (cc.array as Float32Array).set(targets.colors);
    tp.needsUpdate = true;
    cc.needsUpdate = true;
    progress.current = 0; // restart the lerp
  }, [atlas, sentence, result, selected, geometry]);

  useFrame((state, delta) => {
    uniforms.uTime.value = state.clock.elapsedTime;
    if (result) {
      progress.current = Math.min(1, progress.current + delta / 0.6); // 600ms regroup (§8.2)
    }
    uniforms.uProgress.value = progress.current;
  });

  return <mesh ref={meshRef} geometry={geometry} material={material} frustumCulled={false} />;
}

function DampedOrbit() {
  const target = useRef({ x: 0, y: 0 });
  const { gl } = useThree();

  useEffect(() => {
    const el = gl.domElement;
    let dragging = false;
    let last = { x: 0, y: 0 };
    const down = (e: PointerEvent) => {
      dragging = true;
      last = { x: e.clientX, y: e.clientY };
    };
    const move = (e: PointerEvent) => {
      if (!dragging) return;
      target.current.x += (e.clientX - last.x) * 0.004;
      target.current.y = THREE.MathUtils.clamp(
        target.current.y + (e.clientY - last.y) * 0.003,
        -0.5,
        0.5,
      );
      last = { x: e.clientX, y: e.clientY };
    };
    const up = () => {
      dragging = false;
    };
    el.addEventListener("pointerdown", down);
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => {
      el.removeEventListener("pointerdown", down);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
  }, [gl]);

  useFrame(({ camera }) => {
    // damped follow — scroll is untouched (passes through, §8.4a)
    const r = 9;
    const tx = Math.sin(target.current.x) * r;
    const tz = Math.cos(target.current.x) * r;
    const ty = target.current.y * 4;
    camera.position.x += (tx - camera.position.x) * 0.06;
    camera.position.z += (tz - camera.position.z) * 0.06;
    camera.position.y += (ty - camera.position.y) * 0.06;
    camera.lookAt(0, 0, 0);
  });
  return null;
}

function FieldContents() {
  const text = useTokenizerStore((s) => s.text);
  // canvas fillText draws nothing for still-loading webfonts and never re-renders,
  // so an atlas built before document.fonts.ready is silently blank — wait for it
  const fontsReady = useFontsReady();
  const atlases = useMemo(
    () =>
      fontsReady
        ? { ar: buildAtlas(text, "ar"), en: buildAtlas(text, "en") }
        : { ar: null, en: null },
    [text, fontsReady],
  );

  return (
    <>
      <color attach="background" args={["#171310"]} />
      {atlases.ar && <ScriptField atlas={atlases.ar} sentence={text} />}
      {atlases.en && <ScriptField atlas={atlases.en} sentence={text} />}
      <DampedOrbit />
      <PostFX>
        {/* subtle only: bloom on the brightest glyphs + a quiet vignette (§8.4) */}
        <Bloom luminanceThreshold={0.85} intensity={0.35} mipmapBlur />
        <Vignette darkness={0.55} offset={0.3} />
      </PostFX>
    </>
  );
}

export function FertilityField({ label }: { label: string }) {
  return (
    <SceneFrame
      label={label}
      animated
      camera={{ position: [0, 0, 9], fov: 40 }}
      className="h-full w-full"
    >
      <FieldContents />
    </SceneFrame>
  );
}
