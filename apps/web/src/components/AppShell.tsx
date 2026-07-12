import type { ReactNode } from "react";
import GlobalNav, { type GlobalPage } from "./GlobalNav";

interface Props {
  active: GlobalPage;
  waitingCount: number;
  onNavigate: (page: GlobalPage) => void;
  children: ReactNode;
}

export default function AppShell({ active, waitingCount, onNavigate, children }: Props) {
  return (
    <div className="min-h-screen">
      <GlobalNav active={active} waitingCount={waitingCount} onNavigate={onNavigate} />
      {children}
    </div>
  );
}
