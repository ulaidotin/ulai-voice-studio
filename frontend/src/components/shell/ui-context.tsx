"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";

import { PlaceCallDialog } from "@/components/calls/place-call-dialog";
import { CommandPalette } from "./command-palette";

interface UI {
  placeCall: (agentId?: string) => void;
  openCommand: () => void;
}

const Ctx = createContext<UI | null>(null);

export function useUI(): UI {
  const ui = useContext(Ctx);
  if (!ui) throw new Error("useUI outside UIProvider");
  return ui;
}

/** Global dialogs reachable from anywhere: the command palette and "Place call". */
export function UIProvider({ children }: { children: React.ReactNode }) {
  const [callFor, setCallFor] = useState<{ agentId?: string } | null>(null);
  const [commandOpen, setCommandOpen] = useState(false);

  const placeCall = useCallback((agentId?: string) => setCallFor({ agentId }), []);
  const openCommand = useCallback(() => setCommandOpen(true), []);
  const value = useMemo(() => ({ placeCall, openCommand }), [placeCall, openCommand]);

  return (
    <Ctx.Provider value={value}>
      {children}
      <CommandPalette open={commandOpen} onOpenChange={setCommandOpen} />
      <PlaceCallDialog
        open={callFor !== null}
        agentId={callFor?.agentId}
        onOpenChange={(o) => !o && setCallFor(null)}
      />
    </Ctx.Provider>
  );
}
