"use client";

import React from 'react';
import {Card, CardContent, CardHeader, CardTitle} from "@/components/ui/card";

const PositionsPage: React.FC = () => {
  return (
    <div className="p-4">
      <Card>
        <CardHeader>
          <CardTitle>Aktif Pozisyonlar</CardTitle>
        </CardHeader>
        <CardContent>
          <p>Mevcut açık işlemlerin detaylı görünümü.</p>
        </CardContent>
      </Card>
    </div>
  );
};

export default PositionsPage;
