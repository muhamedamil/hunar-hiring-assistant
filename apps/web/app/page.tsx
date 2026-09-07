import { DashboardOverview } from "@/components/dashboard/dashboard-overview";
import { AppShell } from "@/components/layout/app-shell";

export default function HomePage() {
  return <AppShell><div className="mx-auto w-full max-w-6xl py-10"><DashboardOverview /></div></AppShell>;
}
