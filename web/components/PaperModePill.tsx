"use client";

import { useEffect, useState } from "react";
import { FlaskConical } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export function PaperModePill() {
  const [paper, setPaper] = useState<boolean | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch(`${API_URL}/agent/status`);
        if (!res.ok) return;
        const data = await res.json();
        setPaper(Boolean(data.paper_trading));
      } catch {
        // silent — pill just stays hidden
      }
    };
    load();
    const i = setInterval(load, 30_000);
    return () => clearInterval(i);
  }, []);

  if (!paper) return null;

  return (
    <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-md bg-amber-500/10 border border-amber-500/40">
      <FlaskConical className="w-3.5 h-3.5 text-amber-500" />
      <span className="text-xs font-bold text-amber-600 dark:text-amber-400">
        PAPER
      </span>
    </div>
  );
}
