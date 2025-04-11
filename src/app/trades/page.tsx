"use client";

import React from 'react';
import {Card, CardContent, CardHeader} from "@/components/ui/card";

const TradesPage: React.FC = () => {
  return (
    <div className="p-4">
      <Card>
        <CardHeader>
          İşlem Geçmişi
        </CardHeader>
        <CardContent>
          <p>Kapatılan işlemlerin analizi.</p>
        </CardContent>
      </Card>
    </div>
  );
};

export default TradesPage;
