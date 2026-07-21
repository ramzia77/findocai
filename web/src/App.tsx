import { useState } from "react";
import { Sidebar, Tab } from "./components/Sidebar";
import { TopBar } from "./components/TopBar";
import { SettingsProvider } from "./context/SettingsContext";
import { ToastProvider } from "./context/ToastContext";
import { AskPage } from "./pages/AskPage";
import { AuditPage } from "./pages/AuditPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { OverviewPage } from "./pages/OverviewPage";
import { SettingsPage } from "./pages/SettingsPage";

const PAGE_META: Record<Tab, { title: string; subtitle: string }> = {
  overview: { title: "Overview", subtitle: "Pipeline activity at a glance" },
  documents: { title: "Documents", subtitle: "Ingest documents into the vector index" },
  ask: { title: "Ask", subtitle: "Query ingested documents with cited answers" },
  audit: { title: "Audit Trail", subtitle: "Every query and extraction, for compliance review" },
  settings: { title: "Settings", subtitle: "Configure the API connection" },
};

function AppShell() {
  const [tab, setTab] = useState<Tab>("overview");
  const meta = PAGE_META[tab];

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <Sidebar activeTab={tab} onNavigate={setTab} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar title={meta.title} subtitle={meta.subtitle} />
        <main className="flex-1 overflow-y-auto px-8 py-8">
          {tab === "overview" && <OverviewPage />}
          {tab === "documents" && <DocumentsPage />}
          {tab === "ask" && <AskPage onNavigateToAudit={() => setTab("audit")} />}
          {tab === "audit" && <AuditPage />}
          {tab === "settings" && <SettingsPage />}
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <SettingsProvider>
      <ToastProvider>
        <AppShell />
      </ToastProvider>
    </SettingsProvider>
  );
}
