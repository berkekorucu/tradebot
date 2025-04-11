"use client";

import { SidebarMenu, SidebarMenuItem, SidebarMenuButton } from "@/components/ui/sidebar";
import { Home, BarChart, Settings, TrendingUp, List, LayoutDashboard, Calendar } from "lucide-react";
import React from "react";

const SidebarMenuComponent: React.FC = () => {
  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <SidebarMenuButton asChild tooltip="Dashboard">
          <a href="/"><LayoutDashboard /><span>Dashboard</span></a>
        </SidebarMenuButton>
      </SidebarMenuItem>
      <SidebarMenuItem>
        <SidebarMenuButton asChild tooltip="Positions">
          <a href="/positions"><List /><span>Positions</span></a>
        </SidebarMenuButton>
      </SidebarMenuItem>
      <SidebarMenuItem>
        <SidebarMenuButton asChild tooltip="Trades">
          <a href="/trades"><TrendingUp /><span>Trades</span></a>
        </SidebarMenuButton>
      </SidebarMenuItem>
      <SidebarMenuItem>
        <SidebarMenuButton asChild tooltip="Scanner">
          <a href="/scanner"><BarChart /><span>Scanner</span></a>
        </SidebarMenuButton>
      </SidebarMenuItem>
      <SidebarMenuItem>
        <SidebarMenuButton asChild tooltip="Settings">
          <a href="/settings"><Settings /><span>Settings</span></a>
        </SidebarMenuButton>
      </SidebarMenuItem>
    </SidebarMenu>
  );
};

export default SidebarMenuComponent;
