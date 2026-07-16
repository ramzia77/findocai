import { createContext, ReactNode, useContext, useEffect, useState } from "react";

const STORAGE_KEY_BASE_URL = "findocai.apiBaseUrl";
const STORAGE_KEY_API_KEY = "findocai.apiKey";
const DEFAULT_BASE_URL = "http://localhost:8000";

interface SettingsContextValue {
  apiBaseUrl: string;
  apiKey: string;
  setApiBaseUrl: (value: string) => void;
  setApiKey: (value: string) => void;
}

const SettingsContext = createContext<SettingsContextValue | null>(null);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [apiBaseUrl, setApiBaseUrlState] = useState(
    () => localStorage.getItem(STORAGE_KEY_BASE_URL) ?? DEFAULT_BASE_URL,
  );
  const [apiKey, setApiKeyState] = useState(
    () => localStorage.getItem(STORAGE_KEY_API_KEY) ?? "",
  );

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY_BASE_URL, apiBaseUrl);
  }, [apiBaseUrl]);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY_API_KEY, apiKey);
  }, [apiKey]);

  return (
    <SettingsContext.Provider
      value={{
        apiBaseUrl,
        apiKey,
        setApiBaseUrl: setApiBaseUrlState,
        setApiKey: setApiKeyState,
      }}
    >
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings(): SettingsContextValue {
  const ctx = useContext(SettingsContext);
  if (!ctx) throw new Error("useSettings must be used within a SettingsProvider");
  return ctx;
}
