"use client";

import { createContext, useContext } from "react";

export type EvidenceSelection = { id: string; title?: string };
export const EvidenceInspectorContext = createContext<{
  open: boolean;
  openEvidence: (selection?: EvidenceSelection, trigger?: HTMLElement) => void;
  close: () => void;
} | null>(null);

export function useEvidenceInspector() {
  return useContext(EvidenceInspectorContext);
}
