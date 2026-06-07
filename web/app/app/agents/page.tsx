"use client";

import { useEffect, useState } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Bot, Play, Pause, RefreshCw, AlertTriangle, CheckCircle, XCircle, Activity, TrendingUp } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

type Agent = {
  agent_id: string;
  symbol: string | null;
  status: string;
  last_heartbeat: string;
  pid: number;
  metadata: any;
};

type AgentRegistry = {
  [key: string]: Agent;
};

type AgentStatus = {
  total_agents: number;
  running: number;
  stale: number;
  paused: boolean;
};

export default function AgentsPage() {
  const [agents, setAgents] = useState<AgentRegistry>({});
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [logs, setLogs] = useState<string[]>([]);

  useEffect(() => {
    load();
    const i = setInterval(load, 5_000);
    return () => clearInterval(i);
  }, []);

  const load = async () => {
    try {
      const [agentsRes, statusRes] = await Promise.all([
        fetch(`${API_URL}/agent/`),
        fetch(`${API_URL}/agent/status`),
      ]);

      const agentsData: AgentRegistry = agentsRes.ok ? await agentsRes.json() : {};
      const statusData = statusRes.ok ? await statusRes.json() : null;

      setAgents(agentsData);
      setStatus(statusData);

      // Fetch profit hunter logs if any exist
      const profitHunterAgents = Object.values(agentsData).filter((a: Agent) =>
        a.agent_id.startsWith("profit_hunter")
      );
      if (profitHunterAgents.length > 0) {
        const logsRes = await fetch(`${API_URL}/agent/profit-hunter/logs`);
        if (logsRes.ok) {
          const logsData = await logsRes.json();
          setLogs(logsData.logs || []);
        }
      }
    } catch (e) {
      console.error("Failed to load agents:", e);
    } finally {
      setLoading(false);
    }
  };

  const handlePause = async () => {
    await fetch(`${API_URL}/agent/pause`, { method: "POST" });
    load();
  };

  const handleResume = async () => {
    await fetch(`${API_URL}/agent/resume`, { method: "POST" });
    load();
  };

  const handleClean = async () => {
    await fetch(`${API_URL}/agent/clean`, { method: "POST" });
    load();
  };

  const scoutAgents = Object.values(agents).filter((a) => a.agent_id === "scout");
  const profitHunters = Object.values(agents).filter((a) => a.agent_id.startsWith("profit_hunter"));

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[50vh]">
        <p className="text-muted-foreground animate-pulse">Loading agent status…</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-7xl">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground mb-1">
            <Bot className="w-8 h-8 inline mr-2 text-primary" />
            Agent Fleet
          </h1>
          <p className="text-muted-foreground">
            Scout finds trades · Profit hunters exit positions · All registered agents heartbeat every 60s
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button size="sm" variant="outline" onClick={handleClean}>
            <RefreshCw className="w-4 h-4 mr-2" />
            Clean Stale
          </Button>
          {status?.paused ? (
            <Button size="sm" onClick={handleResume} className="bg-emerald-600 hover:bg-emerald-700">
              <Play className="w-4 h-4 mr-2" />
              Resume All
            </Button>
          ) : (
            <Button size="sm" variant="destructive" onClick={handlePause}>
              <Pause className="w-4 h-4 mr-2" />
              Pause All
            </Button>
          )}
        </div>
      </div>

      {/* Status Overview */}
      {status && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground uppercase">Total Agents</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{status.total_agents}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground uppercase">Running</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-emerald-500">{status.running}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground uppercase">Stale</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-yellow-500">{status.stale}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground uppercase">Status</CardTitle>
            </CardHeader>
            <CardContent>
              <Badge variant={status.paused ? "destructive" : "default"} className="text-sm">
                {status.paused ? "⏸ PAUSED" : "▶ ACTIVE"}
              </Badge>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Scout Agent */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg font-semibold flex items-center gap-2">
              <Activity className="w-5 h-5 text-primary" />
              Scout Agent
            </CardTitle>
            {scoutAgents.length > 0 && (
              <Badge variant="default" className="bg-emerald-600">
                <CheckCircle className="w-3 h-3 mr-1" />
                Running
              </Badge>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {scoutAgents.length === 0 ? (
            <div className="text-center py-8">
              <AlertTriangle className="w-12 h-12 text-yellow-500 mx-auto mb-3" />
              <p className="text-sm text-muted-foreground mb-1">Scout agent not running</p>
              <p className="text-xs text-muted-foreground">
                Start with: <code className="bg-muted px-2 py-0.5 rounded text-xs">./scripts/start_scout.sh wyckoff</code>
              </p>
            </div>
          ) : (
            scoutAgents.map((agent) => (
              <div key={agent.agent_id} className="space-y-3">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="text-muted-foreground text-xs uppercase tracking-wider mb-1">Playbook</p>
                    <p className="font-mono text-foreground font-semibold">
                      {agent.metadata?.playbook || "Unknown"}
                    </p>
                  </div>
                  <div>
                    <p className="text-muted-foreground text-xs uppercase tracking-wider mb-1">Poll Interval</p>
                    <p className="font-mono text-foreground">{agent.metadata?.poll_minutes || "?"} minutes</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground text-xs uppercase tracking-wider mb-1">PID</p>
                    <p className="font-mono text-foreground">{agent.pid}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground text-xs uppercase tracking-wider mb-1">Last Heartbeat</p>
                    <p className="font-mono text-foreground text-xs">
                      {new Date(agent.last_heartbeat).toLocaleTimeString()}
                    </p>
                  </div>
                </div>
                {agent.metadata?.symbols && (
                  <div>
                    <p className="text-muted-foreground text-xs uppercase tracking-wider mb-2">Monitoring</p>
                    <div className="flex flex-wrap gap-2">
                      {agent.metadata.symbols.map((sym: string) => (
                        <Badge key={sym} variant="outline" className="font-mono text-xs">
                          {sym}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))
          )}
        </CardContent>
      </Card>

      {/* Profit Hunters */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg font-semibold flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-emerald-500" />
              Profit Hunters
            </CardTitle>
            <Badge variant="outline">{profitHunters.length} active</Badge>
          </div>
        </CardHeader>
        <CardContent>
          {profitHunters.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-sm text-muted-foreground mb-1">No profit hunters monitoring positions</p>
              <p className="text-xs text-muted-foreground">
                Start with: <code className="bg-muted px-2 py-0.5 rounded text-xs">python -m api.services.profit_hunter --symbol BTC-EUR --qty 0.0001 --cost-eur 2.00</code>
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {profitHunters.map((agent) => (
                <div
                  key={agent.agent_id}
                  className="border border-border rounded-lg p-4 bg-muted/30 hover:bg-muted/50 transition"
                >
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <p className="font-bold text-foreground text-lg">{agent.symbol}</p>
                      <Badge variant="default" className="mt-1 text-xs bg-emerald-600">
                        Hunting
                      </Badge>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-muted-foreground">PID {agent.pid}</p>
                      <p className="text-xs text-muted-foreground font-mono">
                        {new Date(agent.last_heartbeat).toLocaleTimeString()}
                      </p>
                    </div>
                  </div>
                  <div className="grid grid-cols-3 gap-4 text-sm">
                    <div>
                      <p className="text-muted-foreground text-xs uppercase tracking-wider mb-1">Qty</p>
                      <p className="font-mono text-foreground">{agent.metadata?.qty || "?"}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground text-xs uppercase tracking-wider mb-1">Cost</p>
                      <p className="font-mono text-foreground">€{agent.metadata?.cost_eur?.toFixed(2) || "?"}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground text-xs uppercase tracking-wider mb-1">Target Profit</p>
                      <p className="font-mono text-emerald-500 font-semibold">
                        €{agent.metadata?.min_profit_eur?.toFixed(2) || "?"}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Logs */}
      {logs.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg font-semibold">Recent Logs</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="bg-black/90 rounded-lg p-4 font-mono text-xs text-green-400 h-64 overflow-y-auto">
              {logs.map((line, i) => (
                <div key={i}>{line}</div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
