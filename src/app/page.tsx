"use client";

import { useEffect, useState } from 'react';
import { collection, onSnapshot, query, orderBy, limit } from 'firebase/firestore';
import { ref, onValue } from 'firebase/database';
import { db, rdb } from '@/lib/firebase';
import { formatCurrency } from '@/lib/utils';
import {
  Card, Grid, Text, Metric, Title, 
  AreaChart, Flex, Icon, Badge
} from '@tremor/react';
import { useAuth } from '@/hooks/useAuth';
import { 
  HomeIcon, WalletIcon, CogIcon, 
  PlusCircleIcon, ChartBarIcon
} from '@heroicons/react/outline';
import { Search, User, Bell, List, TrendingUp, BarChart, Settings, Calendar } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Sidebar,
  SidebarContent,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarProvider,
} from "@/components/ui/sidebar";
import SidebarMenuComponent from "@/components/dashboard/sidebar-menu";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";

// Ana dashboard sayfası
export default function Home() {
  const { user } = useAuth();
  const [portfolio, setPortfolio] = useState<any>(null);
  const [positions, setPositions] = useState<any[]>([]);
  const [transactions, setTransactions] = useState<any[]>([]);
  const [liveData, setLiveData] = useState<any>({});
  const [systemStatus, setSystemStatus] = useState<any>(null);
  const [favorites, setFavorites] = useState<any[]>([]);
  
  // Buraya Firebase'den veya backend'den verileri çekecek olan useEffect hook'ları eklenecek

  useEffect(() => {
    // Dummy portfolio verisi
    setPortfolio({
      balance: 5432.12,
      daily_change: 0.35,
      history: [
        { date: "2024-05-01", balance: 5000 },
        { date: "2024-05-08", balance: 5100 },
        { date: "2024-05-15", balance: 5300 },
        { date: "2024-05-22", balance: 5432.12 },
      ],
      id: "portfolio123",
      created_at: new Date().toISOString(),
      margin_limit: 10000,
    });

    // Dummy transactions verisi
    setTransactions([
      { id: "tx1", symbol: "BTC", type: "Long", fee: 0.01, amount: 0.002, timestamp: new Date().getTime() },
      { id: "tx2", symbol: "ETH", type: "Short", fee: 0.005, amount: -0.008, timestamp: new Date().getTime() },
    ]);

    // Dummy favorites verisi
    setFavorites([
      { id: "fav1", symbol: "BTC", name: "Bitcoin" },
      { id: "fav2", symbol: "ETH", name: "Ethereum" },
      { id: "fav3", symbol: "LTC", name: "Litecoin" },
    ]);
  }, []);

  // Toplam portföy değeri hesaplama
  const totalBalance = portfolio?.balance || 0;
  const dailyChange = portfolio?.daily_change || 0;
  const isPositive = dailyChange >= 0;

  return (
    <SidebarProvider>
      <Sidebar collapsible="icon" variant="inset">
        <SidebarMenuComponent />
      </Sidebar>
      <SidebarContent>
        <div className="md:flex md:flex-row h-screen bg-gray-50 dark:bg-gray-900">
          {/* Ana İçerik */}
          <div className="flex-1 overflow-auto p-6">
            <h1 className="text-3xl font-semibold mb-2 text-foreground">
              Welcome back, {user?.displayName?.split(' ')[0] || 'User'}
            </h1>
            
            <div className="mb-6">
              <p className="text-gray-500 mb-1 text-muted-foreground">My Balance</p>
              <h2 className="text-3xl font-bold text-foreground">{formatCurrency(totalBalance)}</h2>
            </div>
            
            {/* Performans Grafiği */}
            {portfolio?.history && (
              <Card className="mb-6 rise-card">
                <AreaChart
                  className="h-72"
                  data={portfolio.history}
                  index="date"
                  categories={["balance"]}
                  colors={["purple"]}
                  valueFormatter={(number) => formatCurrency(number)}
                  showAnimation={true}
                  showLegend={false}
                  showYAxis={false}
                  showGradient={true}
                />
              </Card>
            )}
            
            {/* İşlemler */}
            <div className="mb-6">
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-2xl font-bold text-foreground">Transactions</h3>
                <Button variant="ghost" size="icon">
                 <Calendar className="h-5 w-5" />
                </Button>
              </div>
              
              <table className="w-full border-collapse">
                <thead>
                  <tr className="text-gray-500 text-left">
                    <th className="pb-3">NAME OF TRANSACTION</th>
                    <th className="pb-3">CATEGORY</th>
                    <th className="pb-3">CASHBACK</th>
                    <th className="pb-3 text-right">AMOUNT</th>
                  </tr>
                </thead>
                <tbody>
                  {transactions.map((tx) => (
                    <tr key={tx.id} className="border-b border-gray-100 dark:border-gray-800">
                      <td className="py-4">
                        <div className="flex items-center">
                          <div className="w-10 h-10 bg-gray-100 dark:bg-gray-800 rounded-full flex items-center justify-center mr-3">
                           <Avatar className="w-10 h-10">
                              <AvatarImage src="https://github.com/shadcn.png" />
                              <AvatarFallback>CN</AvatarFallback>
                            </Avatar>
                          </div>
                          <div>
                            <div className="font-medium text-foreground">{tx.symbol}</div>
                            <div className="text-sm text-gray-500 text-muted-foreground">
                              {new Date(tx.timestamp).toLocaleString()}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="py-4 text-foreground">{tx.type}</td>
                      <td className="py-4 text-green-500">+${tx.fee}</td>
                      <td className="py-4 text-right font-medium" 
                          style={{ color: tx.amount > 0 ? '#22c55e' : '#ef4444' }}>
                        {tx.amount > 0 ? '+' : ''}{formatCurrency(tx.amount)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          
          {/* Sağ Panel */}
          <div className="w-full md:w-80 p-6 border-l border-gray-200 dark:border-gray-800">
            <h3 className="text-2xl font-bold mb-6 text-foreground">My Cards</h3>
            
            {/* Portföy Kartı */}
            <div className="w-full h-48 rounded-lg gradient-purple text-white p-5 mb-6 relative overflow-hidden">
              <div className="flex justify-between">
                <div>
                  <p className="text-purple-200 mb-1">Current Balance</p>
                  <h4 className="text-2xl font-bold">{formatCurrency(totalBalance)}</h4>
                </div>
                <div>
                  {/*  <img src="/logo-white.png" alt="Logo" className="h-6" /> */}
                </div>
              </div>
              
              <div className="mt-8">
                <p className="text-purple-200 text-sm mb-1">PORTFOLIO ID</p>
                <div className="flex justify-between items-center">
                  <p>•••• •••• •••• {portfolio?.id?.slice(-4) || '1234'}</p>
                </div>
              </div>
              
              <div className="absolute bottom-5 right-5">
                <p className="text-sm">
                  <span className="text-purple-200 mr-2">STARTED</span>
                  {portfolio?.created_at ? new Date(portfolio.created_at).toLocaleDateString('en-US', { month: '2-digit', year: '2-digit' }) : '01/23'}
                </p>
              </div>
            </div>
            
            {/* Bakiye ve Limit Bilgileri */}
            <div className="flex justify-between mb-6">
              <div>
                <p className="text-gray-500 mb-1 text-muted-foreground">Balance</p>
                <p className="font-bold text-foreground">{formatCurrency(totalBalance)}</p>
              </div>
              <div>
                <p className="text-gray-500 mb-1 text-muted-foreground">Credit Limit</p>
                <p className="font-bold text-foreground">{formatCurrency(portfolio?.margin_limit || 0)}</p>
              </div>
            </div>
            
            {/* Para Gönder */}
            <div className="mb-6">
              <h4 className="text-lg font-bold mb-4 text-foreground">Send money to</h4>
              
              <div className="flex space-x-3 mb-4">
                {favorites.slice(0, 3).map((fav) => (
                  <div key={fav.id} className="flex flex-col items-center">
                    <div className="w-12 h-12 rounded-full bg-gray-200 dark:bg-gray-700 mb-1 overflow-hidden">
                      <img src={`/coins/${fav.symbol.toLowerCase()}.png`} alt={fav.symbol} className="w-full h-full object-cover" />
                    </div>
                    <p className="text-xs text-muted-foreground">{fav.name}</p>
                  </div>
                ))}
                
                <div className="flex flex-col items-center">
                  <div className="w-12 h-12 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center mb-1">
                    <PlusCircleIcon className="w-6 h-6 text-gray-400" />
                  </div>
                  <p className="text-xs text-muted-foreground">More</p>
                </div>
              </div>
              
              {/* Para Gönderme Formu */}
              <div className="mb-4">
                <p className="text-gray-500 mb-2 text-muted-foreground">Card number</p>
                <div className="border border-gray-200 dark:border-gray-700 rounded p-3 flex items-center">
                  <span className="mr-2">💳</span>
                  <input type="text" placeholder="xxxx xxxx xxxx xxxx" className="bg-transparent flex-1 outline-none text-foreground" />
                </div>
              </div>
              
              <div className="mb-6">
                <p className="text-gray-500 mb-2 text-muted-foreground">Sum</p>
                <div className="border border-gray-200 dark:border-gray-700 rounded p-3 flex items-center">
                  <span className="mr-2">$</span>
                  <input type="text" placeholder="130.00" className="bg-transparent flex-1 outline-none text-foreground" />
                </div>
              </div>
              
              <Button className="w-full bg-black text-white py-3 rounded-lg font-medium">
                Send money
              </Button>
            </div>
          </div>
        </div>
      </SidebarContent>
    </SidebarProvider>
  );
}
