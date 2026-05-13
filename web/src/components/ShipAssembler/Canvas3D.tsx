/**
 * 3D preview of the assembled ship.
 *
 * Each placed part renders as a solid primitive shaped by its category
 * (hull=cylinder, habitat=torus, reactor=cylinder, radiator=plane,
 * shield=cone, propulsion=cone), positioned by the (x, y) in the
 * assembly store, scaled into a view-friendly world. Click selects;
 * double-click removes (matches Canvas2D behaviour).
 *
 * Solid opaque MeshStandardMaterial — no transparent / wireframe /
 * additive primitives by default per the ARIA solid-3D rule.
 *
 * Roadmap Track 2 Phase 4 — capstone of the assembler track.
 */

import { Canvas } from '@react-three/fiber';
import { OrbitControls, Grid } from '@react-three/drei';
import { useMemo } from 'react';
import * as THREE from 'three';
import type { ShipPartDef } from '../../api/aria';
import { useAssembly } from './AssemblyStore';

interface Props {
  partDefs: Record<string, ShipPartDef>;
}

interface PartMeshProps {
  uid: string;
  partId: string;
  x: number;
  y: number;
  selected: boolean;
  defs: Record<string, ShipPartDef>;
  onSelect: () => void;
  onRemove: () => void;
}

function PartMesh({ uid, partId, x, y, selected, defs, onSelect, onRemove }: PartMeshProps) {
  const def = defs[partId];
  if (!def) return null;
  // Map 2D pixel coords (typically 0..600) to world units (~ -5..+5).
  // Store the geometry+arguments choice per category, all opaque.
  const px = (x - 300) / 60;
  const py = -(y - 200) / 60;
  const baseColor = new THREE.Color(def.color || '#475569');
  const onPointer = (
    e: { stopPropagation: () => void; nativeEvent?: { detail?: number } },
  ) => {
    e.stopPropagation();
    const detail = e.nativeEvent?.detail ?? 1;
    if (detail >= 2) onRemove();
    else onSelect();
  };

  const mat = (
    <meshStandardMaterial
      color={baseColor}
      roughness={0.55}
      metalness={0.25}
      emissive={selected ? new THREE.Color('#22d3ee') : new THREE.Color('#000')}
      emissiveIntensity={selected ? 0.18 : 0}
    />
  );

  // Common props for selection ring highlight on selected parts.
  const SelectionRing = selected ? (
    <mesh rotation={[Math.PI / 2, 0, 0]}>
      <torusGeometry args={[0.85, 0.04, 8, 32]} />
      <meshStandardMaterial color="#22d3ee" emissive="#22d3ee" emissiveIntensity={0.7} />
    </mesh>
  ) : null;

  switch (def.category) {
    case 'hull':
      return (
        <group position={[px, py, 0]} onClick={onPointer} userData={{ uid }}>
          <mesh rotation={[0, 0, Math.PI / 2]}>
            <cylinderGeometry args={[0.55, 0.55, 1.6, 32]} />
            {mat}
          </mesh>
          {SelectionRing}
        </group>
      );
    case 'habitat':
      return (
        <group position={[px, py, 0]} onClick={onPointer} userData={{ uid }}>
          <mesh rotation={[Math.PI / 2, 0, 0]}>
            <torusGeometry args={[0.85, 0.13, 16, 48]} />
            {mat}
          </mesh>
          {SelectionRing}
        </group>
      );
    case 'reactor':
      return (
        <group position={[px, py, 0]} onClick={onPointer} userData={{ uid }}>
          <mesh rotation={[0, 0, Math.PI / 2]}>
            <cylinderGeometry args={[0.42, 0.42, 1.0, 24]} />
            {mat}
          </mesh>
          {SelectionRing}
        </group>
      );
    case 'radiator':
      return (
        <group position={[px, py, 0]} onClick={onPointer} userData={{ uid }}>
          <mesh>
            <boxGeometry args={[1.5, 0.04, 0.6]} />
            {mat}
          </mesh>
          {SelectionRing}
        </group>
      );
    case 'shield':
      return (
        <group position={[px, py, 0]} onClick={onPointer} userData={{ uid }}>
          <mesh rotation={[0, 0, -Math.PI / 2]}>
            <coneGeometry args={[0.7, 1.1, 32]} />
            {mat}
          </mesh>
          {SelectionRing}
        </group>
      );
    case 'propulsion':
      return (
        <group position={[px, py, 0]} onClick={onPointer} userData={{ uid }}>
          <mesh rotation={[0, 0, Math.PI / 2]}>
            <coneGeometry args={[0.45, 0.9, 28]} />
            {mat}
          </mesh>
          {SelectionRing}
        </group>
      );
    default:
      return (
        <group position={[px, py, 0]} onClick={onPointer} userData={{ uid }}>
          <mesh>
            <sphereGeometry args={[0.55, 16, 16]} />
            {mat}
          </mesh>
          {SelectionRing}
        </group>
      );
  }
}

export function Canvas3D({ partDefs }: Props) {
  const placed = useAssembly((s) => s.placed);
  const selectedUid = useAssembly((s) => s.selectedUid);
  const selectPart = useAssembly((s) => s.selectPart);
  const removePart = useAssembly((s) => s.removePart);

  const meshes = useMemo(
    () =>
      placed.map((p) => (
        <PartMesh
          key={p.uid}
          uid={p.uid}
          partId={p.partId}
          x={p.x}
          y={p.y}
          selected={p.uid === selectedUid}
          defs={partDefs}
          onSelect={() => selectPart(p.uid)}
          onRemove={() => removePart(p.uid)}
        />
      )),
    [placed, selectedUid, partDefs, selectPart, removePart],
  );

  return (
    <div className="h-full w-full bg-ui-bg-0">
      <Canvas
        camera={{ position: [4, 3, 6], fov: 45 }}
        dpr={[1, 1.5]}
        gl={{ antialias: true }}
      >
        <color attach="background" args={['#020617']} />
        <ambientLight intensity={0.35} />
        <directionalLight position={[5, 8, 4]} intensity={0.9} />
        <directionalLight position={[-4, -3, -2]} intensity={0.25} color="#a5b4fc" />
        <Grid
          position={[0, -1.5, 0]}
          args={[20, 20]}
          cellColor="#334155"
          sectionColor="#475569"
          sectionThickness={1.0}
          fadeDistance={18}
          fadeStrength={1.6}
          followCamera={false}
        />
        {meshes}
        <OrbitControls makeDefault enableDamping dampingFactor={0.08} />
      </Canvas>
      {placed.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center text-xs text-ui-text-faint pointer-events-none">
          (3D preview empty — drag a part on the 2D tab first)
        </div>
      )}
    </div>
  );
}

export default Canvas3D;
