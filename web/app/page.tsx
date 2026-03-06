import { GlassCard } from "@/components/GlassCard";
import { Button } from "@/components/ui/button";
import Link from "next/link";

export default function LandingPage() {
  return (
    <div className="relative min-h-screen overflow-hidden bg-background flex flex-col items-center justify-center p-6 text-center">
      {/* Subtle ambient lighting */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-primary/5 rounded-full blur-[100px] pointer-events-none" />

      <div className="z-10 max-w-3xl space-y-8">
        <div className="inline-flex h-9 items-center justify-center rounded-full border border-border bg-muted px-4 text-xs font-semibold uppercase tracking-widest text-primary">
          Discretionary Execution Model
        </div>

        <h1 className="text-5xl md:text-7xl font-bold tracking-tight text-foreground">
          AURUM <span className="text-primary">OS</span>
        </h1>

        <p className="text-lg text-muted-foreground max-w-xl mx-auto leading-relaxed">
          AI-native gold trading copilot. Designed for disciplined, high-conviction discretionary execution with immutable audit trails.
        </p>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-4">
          <Link href="/app">
            <Button size="lg" className="w-full sm:w-auto h-12 px-8 font-bold rounded-xl">
              Enter Workspace
            </Button>
          </Link>
          <Button size="lg" variant="outline" className="w-full sm:w-auto h-12 px-8 font-medium rounded-xl">
            View Architecture
          </Button>
        </div>
      </div>

      <div className="absolute bottom-12 w-full max-w-5xl px-6 grid grid-cols-1 md:grid-cols-3 gap-6 z-10 text-left">
        <GlassCard className="p-6">
          <div className="text-primary mb-2">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
          </div>
          <h3 className="text-foreground font-bold mb-2">Agentic Scrutiny</h3>
          <p className="text-muted-foreground text-sm">Validate risk and challenge confirmation bias before staging any ticket.</p>
        </GlassCard>
        <GlassCard className="p-6">
          <div className="text-primary mb-2">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" /></svg>
          </div>
          <h3 className="text-foreground font-bold mb-2">Immutable Validation</h3>
          <p className="text-muted-foreground text-sm">Trades require explicit human authorization to be released.</p>
        </GlassCard>
        <GlassCard className="p-6">
          <div className="text-primary mb-2">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 10h16M4 14h16M4 18h16" /></svg>
          </div>
          <h3 className="text-foreground font-bold mb-2">Systematic Journaling</h3>
          <p className="text-muted-foreground text-sm">Process-focused analytics prioritizing execution quality over PnL.</p>
        </GlassCard>
      </div>
    </div>
  );
}
