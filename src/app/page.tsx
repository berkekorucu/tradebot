"use client";

import { SidebarProvider, Sidebar, SidebarContent } from "@/components/ui/sidebar";
import DashboardContent from "@/components/dashboard/dashboard-content";
import SidebarMenu from "@/components/dashboard/sidebar-menu";
import React from "react";
import {Card, CardContent, CardHeader, CardTitle} from "@/components/ui/card";
import {Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis} from "recharts";
import {cn} from "@/lib/utils";
import {Button} from "@/components/ui/button";
import {Textarea} from "@/components/ui/textarea";
import {Label} from "@/components/ui/label";
import {useToast} from "@/hooks/use-toast";
import {optimizeTradingStrategy} from "@/ai/flows/strategy-optimizer";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card"

interface TradingData {
  date: string;
  value: number;
}

const historicalTradingData: TradingData[] = [
  { date: '2024-01-01', value: 10000 },
  { date: '2024-01-08', value: 10500 },
  { date: '2024-01-15', value: 11000 },
  { date: '2024-01-22', value: 10800 },
  { date: '2024-01-29', value: 11200 },
  { date: '2024-02-05', value: 11500 },
  { date: '2024-02-12', value: 11800 },
  { date: '2024-02-19', value: 12000 },
  { date: '2024-02-26', value: 12200 },
  { date: '2024-03-04', value: 12500 },
  { date: '2024-03-11', value: 12600 },
  { date: '2024-03-18', value: 12800 },
  { date: '2024-03-25', value: 13000 },
  { date: '2024-04-01', value: 13200 },
  { date: '2024-04-08', value: 13500 },
  { date: '2024-04-15', value: 13400 },
];

interface StrategyOptimizerProps {
}

const StrategyOptimizer: React.FC<StrategyOptimizerProps> = () => {
  const [historicalData, setHistoricalData] = React.useState<string>('');
  const [currentStrategy, setCurrentStrategy] = React.useState<string>('');
  const [optimizationGoals, setOptimizationGoals] = React.useState<string>('');
  const [suggestedStrategy, setSuggestedStrategy] = React.useState<string>('');
  const [rationale, setRationale] = React.useState<string>('');
  const [riskAssessment, setRiskAssessment] = React.useState<string>('');
  const {toast} = useToast();

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();

    try {
      const result = await optimizeTradingStrategy({
        historicalData,
        currentStrategy,
        optimizationGoals,
      });
      setSuggestedStrategy(result.suggestedStrategy);
      setRationale(result.rationale);
      setRiskAssessment(result.riskAssessment);
    } catch (error: any) {
      console.error('Error optimizing strategy:', error);
      toast({
        title: 'Error',
        description: error.message || 'Failed to optimize trading strategy.',
        variant: 'destructive',
      });
    }
  };

  return (
    <Card className="col-span-2 smooth-transition">
      <CardHeader>
        <CardTitle>AI Strategy Optimizer</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        <form onSubmit={handleSubmit} className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="historicalData">Historical Data (CSV)</Label>
            <Textarea
              id="historicalData"
              placeholder="Date,Open,High,Low,Close,Volume"
              value={historicalData}
              onChange={(e) => setHistoricalData(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="currentStrategy">Current Strategy (Optional)</Label>
            <Textarea
              id="currentStrategy"
              placeholder="Describe your current strategy"
              value={currentStrategy}
              onChange={(e) => setCurrentStrategy(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="optimizationGoals">Optimization Goals</Label>
            <Textarea
              id="optimizationGoals"
              placeholder="Maximize profit, minimize risk, etc."
              value={optimizationGoals}
              onChange={(e) => setOptimizationGoals(e.target.value)}
            />
          </div>
          <Button type="submit">Optimize Strategy</Button>
        </form>

        {suggestedStrategy && (
          <div className="mt-4 grid gap-4">
            <h3>Suggested Strategy</h3>
            <p>{suggestedStrategy}</p>
            <h3>Rationale</h3>
            <p>{rationale}</p>
            <h3>Risk Assessment</h3>
            <p>{riskAssessment}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default function Home() {
  const accountBalance = 50000;
  const openPositions = 5;
  const totalTrades = 120;
  const profitableTrades = 90;
  const profitFactor = 1.8;

  return (
    <SidebarProvider>
      <Sidebar collapsible="icon" variant="inset">
        <SidebarMenu />
      </Sidebar>
      <SidebarContent>
        <div className="md:flex md:flex-col gap-4 p-4">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <Card className="smooth-transition">
              <CardHeader>
                <CardTitle>Account Balance</CardTitle>
              </CardHeader>
              <CardContent className="animated-gradient">
                <div className="text-2xl font-bold">${accountBalance.toLocaleString()}</div>
              </CardContent>
            </Card>

            <Card className="smooth-transition">
              <CardHeader>
                <CardTitle>Open Positions</CardTitle>
              </CardHeader>
              <CardContent className="animated-gradient">
                <div className="text-2xl font-bold">{openPositions}</div>
              </CardContent>
            </Card>

            <Card className="smooth-transition">
              <CardHeader>
                <CardTitle>Total Trades</CardTitle>
              </CardHeader>
              <CardContent className="animated-gradient">
                <div className="text-2xl font-bold">{totalTrades}</div>
              </CardContent>
            </Card>

            <Card className="smooth-transition">
              <CardHeader>
                <CardTitle>Profit Factor</CardTitle>
              </CardHeader>
              <CardContent className="animated-gradient">
                <div className="text-2xl font-bold">{profitFactor}</div>
              </CardContent>
            </Card>
          </div>

          <Card className="col-span-2 smooth-transition">
            <CardHeader>
              <CardTitle>Performance Chart</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <AreaChart data={historicalTradingData}
                           margin={{top: 10, right: 30, left: 0, bottom: 0}}>
                  <CartesianGrid strokeDasharray="3 3"/>
                  <XAxis dataKey="date"/>
                  <YAxis/>
                  <Tooltip/>
                  <Area type="monotone" dataKey="value" stroke="#8884d8" fill="#8884d8"/>
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <StrategyOptimizer/>
        </div>
      </SidebarContent>
    </SidebarProvider>
  );
}

