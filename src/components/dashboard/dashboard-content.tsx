
import React from 'react';
import {Card, CardContent, CardHeader, CardTitle} from "@/components/ui/card";

const DashboardContent: React.FC = () => {
  return (
    <div className="p-4">
      <Card>
        <CardHeader>
          <CardTitle>Welcome to TradeWise</CardTitle>
        </CardHeader>
        <CardContent>
          <p>Your AI-Powered Trading Bot Dashboard.</p>
        </CardContent>
      </Card>
    </div>
  );
};

export default DashboardContent;

