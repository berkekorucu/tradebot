"use client";

import React from 'react';
import {Card, CardContent, CardHeader, CardTitle} from "@/components/ui/card";

const ScannerPage: React.FC = () => {
  return (
    <div className="p-4">
      <Card>
        <CardHeader>
          <CardTitle>Fırsat Tarayıcı</CardTitle>
        </CardHeader>
        <CardContent>
          <p>En yüksek potansiyel taşıyan kripto paraların listesi.</p>
        </CardContent>
      </Card>
    </div>
  );
};

export default ScannerPage;
