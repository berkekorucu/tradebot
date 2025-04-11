"use client";

import React from 'react';
import {Card, CardContent, CardHeader, CardTitle} from "@/components/ui/card";

const TradesPage: React.FC = () => {
  return (
    <div className="p-4">
      <Card>
        <CardHeader>
          <CardTitle>İşlem Geçmişi</CardTitle>
        </CardHeader>
        <CardContent>
          <p>Kapatılan işlemlerin analizi.</p>
        </CardContent>
      </Card>
    </div>
  );
};

export default TradesPage;
