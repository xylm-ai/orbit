"use client";

import { useEffect, useState } from "react";
import { createPriceFeed } from "@/lib/api";

interface PriceUpdate {
  type: string;
  updated_isins: string[];
  timestamp: string;
}

export function PriceTicker() {
  const [lastUpdate, setLastUpdate] = useState<string | null>(null);
  const [updatedCount, setUpdatedCount] = useState(0);

  useEffect(() => {
    const token = localStorage.getItem("orbit_token");
    if (!token) return;

    const ws = createPriceFeed(token);

    ws.onmessage = (event) => {
      try {
        const data: PriceUpdate = JSON.parse(event.data);
        if (data.type === "price_update") {
          setLastUpdate(new Date(data.timestamp).toLocaleTimeString());
          setUpdatedCount(data.updated_isins.length);
        }
      } catch {
        // ignore malformed messages
      }
    };

    return () => ws.close();
  }, []);

  if (!lastUpdate) return null;

  return (
    <span className="text-xs text-muted-foreground">
      {updatedCount} prices updated at {lastUpdate}
    </span>
  );
}
