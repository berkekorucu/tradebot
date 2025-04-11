"use client";

import React from 'react';
import {Card, CardContent, CardHeader, CardTitle} from "@/components/ui/card";

const SettingsPage: React.FC = () => {
  return (
    <div className="p-4">
      <Card>
        <CardHeader>
          <CardTitle>Ayarlar</CardTitle>
        </CardHeader>
        <CardContent>
          <p>Bot ayarlarının düzenlenebilmesi.</p>
        </CardContent>
      </Card>
    </div>
  );
};

export default SettingsPage;
