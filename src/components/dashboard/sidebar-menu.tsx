"use client";

import { SidebarMenu, SidebarMenuItem, SidebarMenuButton } from "@/components/ui/sidebar";
import { Home, BarChart, Settings, TrendingUp, List, LayoutDashboard, Calendar, User, File, ShoppingCart, PieChart, Mail, Users } from "lucide-react";
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
       <SidebarMenuItem>
        <SidebarMenuButton asChild tooltip="Calendar">
          <a href="/calendar"><Calendar /><span>Calendar</span></a>
        </SidebarMenuButton>
      </SidebarMenuItem>
       <SidebarMenuItem>
        <SidebarMenuButton asChild tooltip="Profile">
          <a href="/profile"><User /><span>Profile</span></a>
        </SidebarMenuButton>
      </SidebarMenuItem>
       <SidebarMenuItem>
        <SidebarMenuButton asChild tooltip="Pages">
          <a href="/pages"><File /><span>Pages</span></a>
        </SidebarMenuButton>
      </SidebarMenuItem>
      <SidebarMenuItem>
         <SidebarMenuButton asChild tooltip="eCommerce">
            <a href="/ecommerce"><ShoppingCart /><span>eCommerce</span></a>
         </SidebarMenuButton>
      </SidebarMenuItem>
      <SidebarMenuItem>
         <SidebarMenuButton asChild tooltip="Analytics">
            <a href="/analytics"><PieChart /><span>Analytics</span></a>
         </SidebarMenuButton>
      </SidebarMenuItem>
       <SidebarMenuItem>
          <SidebarMenuButton asChild tooltip="Messages">
             <a href="/messages"><Mail /><span>Messages</span></a>
          </SidebarMenuButton>
       </SidebarMenuItem>
       <SidebarMenuItem>
          <SidebarMenuButton asChild tooltip="Users">
             <a href="/users"><Users /><span>Users</span></a>
          </SidebarMenuButton>
       </SidebarMenuItem>
    </SidebarMenu>
  );
};

export default SidebarMenuComponent;
