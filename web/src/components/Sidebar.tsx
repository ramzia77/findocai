import { FileStack, LayoutDashboard, MessageSquareText, ScrollText, Settings } from "lucide-react";

export type Tab = "overview" | "documents" | "ask" | "audit" | "settings";

const NAV_ITEMS: { tab: Tab; label: string; icon: typeof LayoutDashboard }[] = [
  { tab: "overview", label: "Overview", icon: LayoutDashboard },
  { tab: "documents", label: "Documents", icon: FileStack },
  { tab: "ask", label: "Ask", icon: MessageSquareText },
  { tab: "audit", label: "Audit Trail", icon: ScrollText },
  { tab: "settings", label: "Settings", icon: Settings },
];

interface SidebarProps {
  activeTab: Tab;
  onNavigate: (tab: Tab) => void;
}

export function Sidebar({ activeTab, onNavigate }: SidebarProps) {
  return (
    <aside className="flex h-full w-60 flex-shrink-0 flex-col border-r border-zinc-200 bg-white">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-zinc-900">
          <span className="text-xs font-bold text-white">FD</span>
        </div>
        <div>
          <p className="text-sm font-semibold leading-tight text-zinc-900">findocai</p>
          <p className="text-[11px] leading-tight text-zinc-400">Document Intelligence</p>
        </div>
      </div>

      <nav className="flex-1 space-y-0.5 px-3 py-2">
        {NAV_ITEMS.map(({ tab, label, icon: Icon }) => {
          const active = tab === activeTab;
          return (
            <button
              key={tab}
              onClick={() => onNavigate(tab)}
              className={`relative flex w-full items-center gap-3 rounded-md py-2 pl-3.5 pr-3 text-sm transition-colors ${
                active ? "bg-zinc-50 font-medium text-zinc-900" : "text-zinc-500 hover:bg-zinc-50 hover:text-zinc-900"
              }`}
            >
              {active && <span className="absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-accent-500" />}
              <Icon className="h-4 w-4" strokeWidth={1.75} />
              {label}
            </button>
          );
        })}
      </nav>

      <div className="border-t border-zinc-100 px-5 py-4 text-[11px] leading-snug text-zinc-400">
        Bank document RAG &amp; extraction demo
      </div>
    </aside>
  );
}
