"use client";

import React from 'react';
import {Card, CardContent, CardHeader} from "@/components/ui/card";

const SettingsPage: React.FC = () => {
  return (
    <div className="p-4">
      <Card>
        <CardHeader>
          Ayarlar
        </CardHeader>
        <CardContent>
          <p>Bot ayarlarının düzenlenebilmesi.</p>
        </CardContent>
      </Card>
    </div>
  );
};

export default SettingsPage;
