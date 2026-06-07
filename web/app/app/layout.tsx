import Link from "next/link";
import { LineChart, BookOpen, Settings, ShieldAlert, FileText, LayoutDashboard, Wallet, Bot } from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";
import { BalancePill } from "@/components/BalancePill";
import { PaperModePill } from "@/components/PaperModePill";

const NAV_ITEMS = [
    { href: "/app", icon: LayoutDashboard, label: "Dashboard" },
    { href: "/app/my-trade", icon: Wallet, label: "My Trade" },
    { href: "/app/exchange", icon: LineChart, label: "Exchange" },
    { href: "/app/agents", icon: Bot, label: "Agents" },
    { href: "/app/approvals", icon: ShieldAlert, label: "Approvals" },
    { href: "/app/planner", icon: FileText, label: "Planner" },
    { href: "/app/journal", icon: BookOpen, label: "Journal" },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
    return (
        <div className="flex h-screen bg-background overflow-hidden">
            {/* Icon-only sidebar */}
            <aside className="w-16 border-r border-border bg-card flex flex-col items-center py-3 shrink-0">
                <Link href="/" className="w-10 h-10 mb-4 rounded-lg bg-primary/10 flex items-center justify-center text-primary font-black text-sm border border-primary/20 hover:bg-primary/20 transition">
                    A
                </Link>
                <nav className="flex-1 flex flex-col gap-1 w-full px-2">
                    {NAV_ITEMS.map((item) => (
                        <Link
                            key={item.href}
                            href={item.href}
                            title={item.label}
                            className="group relative h-11 w-full rounded-lg flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                        >
                            <item.icon className="w-5 h-5" />
                            <span className="absolute left-full ml-2 px-2 py-1 bg-popover text-popover-foreground border border-border rounded-md text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-50 shadow-md">
                                {item.label}
                            </span>
                        </Link>
                    ))}
                </nav>
                <Link href="/app/settings" title="Settings" className="h-11 w-11 rounded-lg flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-accent transition-colors">
                    <Settings className="w-5 h-5" />
                </Link>
            </aside>

            {/* Main */}
            <main className="flex-1 flex flex-col min-w-0">
                <header className="h-16 border-b border-border bg-card flex items-center justify-between px-4 shrink-0">
                    <div className="flex items-center gap-3">
                        <h2 className="text-base font-bold text-foreground tracking-tight"><span className="text-primary">Helm</span></h2>
                    </div>
                    <div className="flex items-center gap-4">
                        <PaperModePill />
                        <BalancePill />
                        <div className="flex items-center gap-2 px-2.5 py-1 rounded-md bg-emerald-500/10 border border-emerald-500/20">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                            <span className="text-[10px] font-semibold text-emerald-500 uppercase tracking-wider">Live</span>
                        </div>
                        <ThemeToggle />
                        <div className="w-8 h-8 rounded-full bg-muted border border-border flex items-center justify-center text-xs font-bold text-foreground cursor-pointer hover:bg-accent transition">
                            DB
                        </div>
                    </div>
                </header>

                <div className="p-6 lg:p-8 flex-1 overflow-y-auto">
                    {children}
                </div>
            </main>
        </div>
    );
}
