/**
 * Drag-and-drop ship-assembly state.
 *
 * Tiny zustand store: a flat list of placed parts (id, x, y) plus
 * a small set of mutators. Connection rules and material choices are
 * layered on top of this in later phases (Track 2 P2, P3).
 */

import { create } from 'zustand';

export interface PlacedPart {
  /** Stable instance id (uuid-ish) — multiple instances of one part def OK. */
  uid: string;
  /** Part-def id from /api/ship/parts. */
  partId: string;
  /** Pixel coords on the canvas. */
  x: number;
  y: number;
  /** Optional material override; null = use part-def default. */
  material: string | null;
}

interface AssemblyState {
  placed: PlacedPart[];
  selectedUid: string | null;
  addPart: (partId: string, x: number, y: number) => string;
  movePart: (uid: string, x: number, y: number) => void;
  removePart: (uid: string) => void;
  selectPart: (uid: string | null) => void;
  setMaterial: (uid: string, material: string | null) => void;
  clear: () => void;
  loadFromRecord: (parts: PlacedPart[]) => void;
}

const _uid = (): string =>
  `p_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;

export const useAssembly = create<AssemblyState>((set) => ({
  placed: [],
  selectedUid: null,
  addPart: (partId, x, y) => {
    const uid = _uid();
    set((s) => ({
      placed: [...s.placed, { uid, partId, x, y, material: null }],
      selectedUid: uid,
    }));
    return uid;
  },
  movePart: (uid, x, y) =>
    set((s) => ({
      placed: s.placed.map((p) => (p.uid === uid ? { ...p, x, y } : p)),
    })),
  removePart: (uid) =>
    set((s) => ({
      placed: s.placed.filter((p) => p.uid !== uid),
      selectedUid: s.selectedUid === uid ? null : s.selectedUid,
    })),
  selectPart: (uid) => set({ selectedUid: uid }),
  setMaterial: (uid, material) =>
    set((s) => ({
      placed: s.placed.map((p) => (p.uid === uid ? { ...p, material } : p)),
    })),
  clear: () => set({ placed: [], selectedUid: null }),
  loadFromRecord: (parts) => set({ placed: [...parts], selectedUid: null }),
}));
