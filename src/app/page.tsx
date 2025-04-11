
import { SidebarProvider, Sidebar, SidebarContent } from "@/components/ui/sidebar";
import DashboardContent from "@/components/dashboard/dashboard-content";
import SidebarMenu from "@/components/dashboard/sidebar-menu";

export default function Home() {
  return (
    <SidebarProvider>
      <Sidebar collapsible="icon" variant="inset">
        <SidebarMenu />
      </Sidebar>
      <SidebarContent>
        <DashboardContent />
      </SidebarContent>
    </SidebarProvider>
  );
}

