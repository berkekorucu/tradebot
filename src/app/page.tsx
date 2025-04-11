"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "@recharts/react";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import {
  Title,
  Text,
} from "@tremor/react";
import { Search, User, Bell } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import { optimizeTradingStrategy } from "@/ai/flows/strategy-optimizer";
import React from "react";

import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import {
  Sidebar,
  SidebarContent,
  SidebarMenu,
  SidebarProvider,
} from "@/components/ui/sidebar";
import SidebarMenuComponent from "@/components/dashboard/sidebar-menu";

interface TradingData {
  date: string;
  value: number;
}

const historicalTradingData: TradingData[] = [
  { date: "2024-01-01", value: 10000 },
  { date: "2024-01-08", value: 10500 },
  { date: "2024-01-15", value: 11000 },
  { date: "2024-01-22", value: 10800 },
  { date: "2024-01-29", value: 11200 },
  { date: "2024-02-05", value: 11500 },
  { date: "2024-02-12", value: 11800 },
  { date: "2024-02-19", value: 12000 },
  { date: "2024-02-26", value: 12200 },
  { date: "2024-03-04", value: 12500 },
  { date: "2024-03-11", value: 12600 },
  { date: "2024-03-18", value: 12800 },
  { date: "2024-03-25", value: 13000 },
  { date: "2024-04-01", value: 13200 },
  { date: "2024-04-08", value: 13500 },
  { date: "2024-04-15", value: 13400 },
];

interface StrategyOptimizerProps {}

const StrategyOptimizer: React.FC<StrategyOptimizerProps> = () => {
  const [historicalData, setHistoricalData] = React.useState<string>("");
  const [currentStrategy, setCurrentStrategy] = React.useState<string>("");
  const [optimizationGoals, setOptimizationGoals] = React.useState<string>("");
  const [suggestedStrategy, setSuggestedStrategy] =
    React.useState<string>("");
  const [rationale, setRationale] = React.useState<string>("");
  const [riskAssessment, setRiskAssessment] = React.useState<string>("");
  const { toast } = useToast();

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
      console.error("Error optimizing strategy:", error);
      toast({
        title: "Error",
        description: error.message || "Failed to optimize trading strategy.",
        variant: "destructive",
      });
    }
  };

  return (
    <Card className="mt-6">
      <CardHeader>
        <Title>AI Strategy Optimizer</Title>
        <Text>Optimize your trading strategy with AI-powered analysis.</Text>
      </CardHeader>
      <CardBody>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="historicalData">Historical Data (CSV)</Label>
            <Textarea
              id="historicalData"
              placeholder="Date,Open,High,Low,Close,Volume"
              value={historicalData}
              onChange={(e) => setHistoricalData(e.target.value)}
              className="shadow-sm focus-visible:ring-accent focus-visible:ring-offset-2"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="currentStrategy">Current Strategy (Optional)</Label>
            <Textarea
              id="currentStrategy"
              placeholder="Describe your current strategy"
              value={currentStrategy}
              onChange={(e) => setCurrentStrategy(e.target.value)}
              className="shadow-sm focus-visible:ring-accent focus-visible:ring-offset-2"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="optimizationGoals">Optimization Goals</Label>
            <Textarea
              id="optimizationGoals"
              placeholder="Maximize profit, minimize risk, etc."
              value={optimizationGoals}
              onChange={(e) => setOptimizationGoals(e.target.value)}
              className="shadow-sm focus-visible:ring-accent focus-visible:ring-offset-2"
            />
          </div>
          <Button
            type="submit"
            className="bg-accent text-accent-foreground rounded-md shadow-md hover:bg-accent/80"
          >
            Optimize Strategy
          </Button>
        </form>

        {suggestedStrategy && (
          <div className="mt-4 space-y-4">
            <div>
              <Title>Suggested Strategy</Title>
              <Text>{suggestedStrategy}</Text>
            </div>
            <div>
              <Title>Rationale</Title>
              <Text>{rationale}</Text>
            </div>
            <div>
              <Title>Risk Assessment</Title>
              <Text>{riskAssessment}</Text>
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  );
};

export default function Home() {
  const accountBalance = 3456000;
  const totalProfit = 45200;
  const totalProduct = 2450;
  const totalUsers = 3456;

  const historicalTradingData = [
    { date: "Sep", value: 20 },
    { date: "Oct", value: 30 },
    { date: "Nov", value: 20 },
    { date: "Dec", value: 40 },
    { date: "Jan", value: 30 },
    { date: "Feb", value: 50 },
    { date: "Mar", value: 40 },
    { date: "Apr", value: 60 },
    { date: "May", value: 50 },
    { date: "Jun", value: 70 },
    { date: "Jul", value: 60 },
    { date: "Aug", value: 80 },
  ];

  const profitThisWeekData = [
    { day: "M", sales: 40, revenue: 60 },
    { day: "T", sales: 50, revenue: 70 },
    { day: "W", sales: 60, revenue: 80 },
    { day: "T", sales: 70, revenue: 50 },
    { day: "F", sales: 30, revenue: 40 },
    { day: "S", sales: 80, revenue: 90 },
    { day: "S", sales: 90, revenue: 70 },
  ];


  return (
    <SidebarProvider>
      <Sidebar collapsible="icon" variant="inset">
        <SidebarMenuComponent />
      </Sidebar>
      <SidebarContent>
        <div className="md:flex md:flex-col gap-4 p-4">
          {/* Top Bar */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Search className="h-5 w-5 text-muted-foreground" />
              <input
                type="text"
                placeholder="Type to search..."
                className="bg-transparent border-none outline-none placeholder:text-muted-foreground"
              />
            </div>
            <div className="flex items-center gap-4">
              <Button variant="ghost" size="icon">
                <Bell className="h-5 w-5" />
              </Button>
              <HoverCard>
                <HoverCardTrigger>
                  <Button variant="ghost" size="icon">
                    <User className="h-5 w-5" />
                  </Button>
                </HoverCardTrigger>
                <HoverCardContent>
                  <div className="flex flex-col space-y-1">
                    <p className="text-sm font-medium">Thomas Anree</p>
                    <p className="text-xs text-muted-foreground">
                      UX Designer
                    </p>
                  </div>
                </HoverCardContent>
              </HoverCard>
            </div>
          </div>

          {/* Header Metrics */}
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mt-4">
            <Card className="bg-secondary text-secondary-foreground shadow-md rounded-xl smooth-transition hover:scale-105">
              <CardHeader>
                <Title className="text-lg font-semibold">Total views</Title>
                <Text className="text-sm text-muted-foreground">
                  Current balance of your trading account
                </Text>
              </CardHeader>
              <CardBody className="text-2xl font-bold">
                ${accountBalance.toLocaleString()}
              </CardBody>
            </Card>

            <Card className="bg-secondary text-secondary-foreground shadow-md rounded-xl smooth-transition hover:scale-105">
              <CardHeader>
                <Title className="text-lg font-semibold">Total Profit</Title>
                <Text className="text-sm text-muted-foreground">
                  Number of currently open trading positions
                </Text>
              </CardHeader>
              <CardBody className="text-2xl font-bold">{totalProfit}</CardBody>
            </Card>

            <Card className="bg-secondary text-secondary-foreground shadow-md rounded-xl smooth-transition hover:scale-105">
              <CardHeader>
                <Title className="text-lg font-semibold">Total Product</Title>
                <Text className="text-sm text-muted-foreground">
                  Total number of trades executed
                </Text>
              </CardHeader>
              <CardBody className="text-2xl font-bold">{totalProduct}</CardBody>
            </Card>

            <Card className="bg-secondary text-secondary-foreground shadow-md rounded-xl smooth-transition hover:scale-105">
              <CardHeader>
                <Title className="text-lg font-semibold">Total Users</Title>
                <Text className="text-sm text-muted-foreground">
                  Ratio of gross profit to gross loss
                </Text>
              </CardHeader>
              <CardBody className="text-2xl font-bold">{totalUsers}</CardBody>
            </Card>
          </div>

          {/* Performance Chart */}
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-2 mt-4">
            <Card className="shadow-md rounded-xl smooth-transition hover:scale-105">
              <CardHeader>
                <Title>Total Revenue</Title>
                <Text>12.04.2022 - 12.05.2022</Text>
              </CardHeader>
              <CardBody>
                <ResponsiveContainer width="100%" height={300}>
                  <AreaChart data={historicalTradingData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis />
                    <Tooltip />
                    <Area type="monotone" dataKey="value" stroke="#8884d8" fill="#8884d8" />
                  </AreaChart>
                </ResponsiveContainer>
              </CardBody>
            </Card>

            <Card className="shadow-md rounded-xl smooth-transition hover:scale-105">
              <CardHeader>
                <Title>Profit this week</Title>
                <Text>This Week</Text>
              </CardHeader>
              <CardBody>
                <ResponsiveContainer width="100%" height={300}>
                  <AreaChart data={profitThisWeekData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="day" />
                    <YAxis />
                    <Tooltip />
                    <Area type="monotone" dataKey="sales" stroke="#8884d8" fill="#8884d8" />
                  </AreaChart>
                </ResponsiveContainer>
              </CardBody>
            </Card>
          </div>

          {/* Strategy Optimizer */}
          <StrategyOptimizer />
        </div>
      </SidebarContent>
    </SidebarProvider>
  );
}
