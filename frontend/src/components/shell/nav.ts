import { Bot, LayoutGrid, Phone, PhoneCall, Settings, type LucideIcon } from "lucide-react";

export const NAV: { href: string; label: string; icon: LucideIcon; shortcut: string }[] = [
  { href: "/", label: "Overview", icon: LayoutGrid, shortcut: "G O" },
  { href: "/agents", label: "Agents", icon: Bot, shortcut: "G A" },
  { href: "/calls", label: "Calls", icon: PhoneCall, shortcut: "G C" },
  { href: "/phone-numbers", label: "Phone numbers", icon: Phone, shortcut: "G P" },
  { href: "/settings", label: "Settings", icon: Settings, shortcut: "G S" },
];

export function isCurrent(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}
