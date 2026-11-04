import { Globe, PhoneIncoming, PhoneOutgoing } from "lucide-react";

import { Badge, Dot } from "@/components/ui/badge";
import type { CallDirection, CallStatus } from "@/lib/types";
import { DIRECTION_LABEL, STATUS_LABEL } from "@/lib/utils";

const TONE: Record<CallStatus, "neutral" | "primary" | "success" | "warning" | "danger"> = {
  queued: "neutral",
  ringing: "primary",
  in_progress: "success",
  completed: "neutral",
  no_answer: "warning",
  failed: "danger",
};

export function StatusBadge({ status }: { status: CallStatus }) {
  const live = status === "ringing" || status === "in_progress";
  return (
    <Badge tone={TONE[status]}>
      {(live || status === "queued") && <Dot pulse={live} />}
      {STATUS_LABEL[status]}
    </Badge>
  );
}

const DIRECTION_ICON = { web: Globe, inbound: PhoneIncoming, outbound: PhoneOutgoing } as const;

export function DirectionLabel({ direction, iconOnly }: { direction: CallDirection; iconOnly?: boolean }) {
  const Icon = DIRECTION_ICON[direction];
  return (
    <span className="inline-flex items-center gap-1.5 text-muted-foreground" title={DIRECTION_LABEL[direction]}>
      <Icon className="size-3.5" />
      {!iconOnly && <span className="text-foreground/80">{DIRECTION_LABEL[direction]}</span>}
    </span>
  );
}
