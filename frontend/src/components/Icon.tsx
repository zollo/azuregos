// Curated, tech-oriented subset of Lucide (MIT) icons for categories/portals.
import {
  Activity,
  AlertTriangle,
  Bell,
  Bookmark,
  Boxes,
  Bug,
  Building2,
  Cloud,
  Code,
  Cog,
  Container,
  Cpu,
  Database,
  FileText,
  Folder,
  Gauge,
  GitBranch,
  Globe,
  HardDrive,
  Headphones,
  HelpCircle,
  KeyRound,
  Laptop,
  LifeBuoy,
  Lock,
  Mail,
  MessageSquare,
  Monitor,
  Network,
  Package,
  Plug,
  Printer,
  Rocket,
  Server,
  Settings,
  ShieldCheck,
  Smartphone,
  Terminal,
  Ticket,
  Users,
  Wifi,
  Wrench,
  Zap,
  type LucideIcon,
} from "lucide-react";

export const ICONS: Record<string, LucideIcon> = {
  Folder, Ticket, Server, Database, Cloud, Cpu, Terminal, Code, GitBranch, Bug,
  ShieldCheck, Lock, KeyRound, Network, HardDrive, Wifi, Container, Boxes, Package,
  Settings, Wrench, LifeBuoy, Mail, MessageSquare, Bell, Globe, Laptop, Monitor,
  Smartphone, Printer, Zap, Activity, AlertTriangle, FileText, Users, Building2,
  Rocket, HelpCircle, Headphones, Plug, Cog, Bookmark, Gauge,
};

export const ICON_NAMES = Object.keys(ICONS);

// Resolve a stored name (incl. legacy lowercase like "folder") to a known icon.
function resolve(name?: string | null): LucideIcon | null {
  if (!name) return null;
  if (ICONS[name]) return ICONS[name];
  const cap = name.charAt(0).toUpperCase() + name.slice(1);
  return ICONS[cap] ?? null;
}

export default function Icon({
  name,
  size = 18,
  className,
}: {
  name?: string | null;
  size?: number;
  className?: string;
}) {
  const Cmp = resolve(name) ?? Ticket;
  return <Cmp size={size} className={className} aria-hidden />;
}
