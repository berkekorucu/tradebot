"use client";

import React from 'react';
import {Card, CardContent, CardHeader} from "@/components/ui/card";

const PositionsPage: React.FC = () => {
  return (
    <div className="p-4">
      <Card>
        <CardHeader>
          Aktif Pozisyonlar
        </CardHeader>
        <CardContent>
          <p>Mevcut açık işlemlerin detaylı görünümü.</p>
        </CardContent>
      </Card>
    </div>
  );
};

export default PositionsPage;
