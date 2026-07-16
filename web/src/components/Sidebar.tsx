import { FileText, MessageSquareText, Settings, UploadCloud } from "lucide-react";

export type Tab = "upload" | "ask" | "settings";

const NAV_ITEMS: { tab: Tab; label: string; icon: typeof UploadCloud }[] = [
  { tab: "upload", label: "Upload", icon: UploadCloud },
  { tab: "ask", label: "Ask", icon: MessageSquareText },
  { tab: "settings", label: "Settings", icon: Settings },
];

interface SidebarProps {
  activeTab: Tab;
  onNavigate: (tab: Tab) => void;
}

export function Sidebar({ activeTab, onNavigate }: SidebarProps) {
  return (
    <aside className="flex h-full w-64 flex-shrink-0 flex-col bg-slate-900 text-slate-200">
      <div className="flex items-center gap-2 px-6 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600">
          <FileText className="h-4 w-4 text-white" />
        </div>
        <div>
          <p className="text-sm font-semibold text-white">findocai</p>
          <p className="text-xs text-slate-400">Document Intelligence</p>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-2">
        {NAV_ITEMS.map(({ tab, label, icon: Icon }) => {
          const active = tab === activeTab;
          return (
            <button
              key={tab}
              onClick={() => onNavigate(tab)}
              className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                active
                  ? "bg-slate-800 text-white"
                  : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
              }`}
            >
              <Icon className="h-4 w-4" />
              {label}
            </button>
          );
        })}
      </nav>

      <div className="border-t border-slate-800 px-6 py-4 text-xs text-slate-500">
        Bank document RAG &amp; extraction demo
      </div>
    </aside>
  );
}
