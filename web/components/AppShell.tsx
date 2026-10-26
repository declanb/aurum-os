"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
    LineChart,
    BookOpen,
    Settings,
    ShieldAlert,
    FileText,
    LayoutDashboard,
    Wallet,
    Bot,
    MessageCircle,
    MoreHorizontal,
    ListChecks,
} from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";
import { BalancePill } from "@/components/BalancePill";
import { PaperModePill } from "@/components/PaperModePill";
import { ProfitBanner, ProfitBell, ProfitNotificationProvider, ProfitSheet } from "@/components/ProfitNotifications";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
    { href: "/app", icon: LayoutDashboard, label: "Dashboard", exact: true },
    { href: "/app/my-trade", icon: Wallet, label: "My Trade" },
    { href: "/app/exchange", icon: LineChart, label: "Exchange" },
    { href: "/app/agents", icon: Bot, label: "Agents" },
    { href: "/app/guru", icon: MessageCircle, label: "Guru" },
    { href: "/app/recommendations", icon: ListChecks, label: "Recommendations" },
    { href: "/app/approvals", icon: ShieldAlert, label: "Approvals" },
    { href: "/app/planner", icon: FileText, label: "Planner" },
    { href: "/app/journal", icon: BookOpen, label: "Journal" },
];

const MOBILE_TABS = [
    { href: "/app", icon: LayoutDashboard, label: "Home", exact: true },
    { href: "/app/my-trade", icon: Wallet, label: "Trades" },
    { href: "/app/approvals", icon: ShieldAlert, label: "Approvals" },
    { href: "/app/exchange", icon: LineChart, label: "Exchange" },
];

const MORE_ITEMS = [
    { href: "/app/recommendations", icon: ListChecks, label: "Recommendations" },
    { href: "/app/planner", icon: FileText, label: "Planner" },
    { href: "/app/journal", icon: BookOpen, label: "Journal" },
    { href: "/app/agents", icon: Bot, label: "Agents" },
    { href: "/app/guru", icon: MessageCircle, label: "Guru" },
    { href: "/app/settings", icon: Settings, label: "Settings" },
];

function isActive(pathname: string, href: string, exact?: boolean) {
    if (exact) return pathname === href;
    return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppShell({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const [moreOpen, setMoreOpen] = useState(false);
    const [morePath, setMorePath] = useState(pathname);
    const moreActive = MORE_ITEMS.some((item) => isActive(pathname, item.href));

    if (pathname !== morePath) {
        setMorePath(pathname);
        setMoreOpen(false);
    }

    return (
        <ProfitNotificationProvider>
        <div className="flex h-dvh bg-background overflow-hidden">
            <aside className="hidden md:flex w-16 border-r border-border bg-card flex-col items-center py-3 shrink-0">
                <Link
                    href="/"
                    aria-label="Helm home"
                    className="w-11 h-11 mb-4 rounded-lg bg-primary/10 flex items-center justify-center text-primary font-black text-sm border border-primary/20 hover:bg-primary/20 transition"
                >
                    A
                </Link>
                <nav className="flex-1 flex flex-col gap-1 w-full px-2" aria-label="Workspace">
                    {NAV_ITEMS.map((item) => {
                        const active = isActive(pathname, item.href, item.exact);
                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                aria-label={item.label}
                                aria-current={active ? "page" : undefined}
                                title={item.label}
                                className={cn(
                                    "group relative h-11 w-full rounded-lg flex items-center justify-center transition-colors",
                                    active
                                        ? "bg-accent text-foreground"
                                        : "text-muted-foreground hover:text-foreground hover:bg-accent"
                                )}
                            >
                                <item.icon className="w-5 h-5" />
                                <span className="absolute left-full ml-2 px-2 py-1 bg-popover text-popover-foreground border border-border rounded-md text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-50 shadow-md">
                                    {item.label}
                                </span>
                            </Link>
                        );
                    })}
                </nav>
                <Link
                    href="/app/settings"
                    aria-label="Settings"
                    title="Settings"
                    className="h-11 w-11 rounded-lg flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                >
                    <Settings className="w-5 h-5" />
                </Link>
            </aside>

            <main className="flex-1 flex flex-col min-w-0 min-h-0">
                <header className="h-14 md:h-16 border-b border-border bg-card flex items-center justify-between px-3 md:px-4 shrink-0 gap-3">
                    <h2 className="text-base font-bold text-foreground tracking-tight">
                        <span className="text-primary">Helm</span>
                    </h2>
                    <div className="flex items-center gap-2 md:gap-3 min-w-0">
                        <PaperModePill />
                        <BalancePill />
                        <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-emerald-500/10 border border-emerald-500/20 shrink-0">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                            <span className="hidden sm:inline text-[10px] font-semibold text-emerald-500 uppercase tracking-wider">
                                Live
                            </span>
                        </div>
                        <ThemeToggle />
                        <ProfitBell />
                        <div className="hidden sm:flex w-9 h-9 rounded-full bg-muted border border-border items-center justify-center text-xs font-bold text-foreground">
                            DB
                        </div>
                    </div>
                </header>

                <div className="flex min-h-0 flex-1 flex-col overflow-y-auto overflow-x-hidden px-4 pt-4 md:px-6 md:pt-6 lg:px-8 lg:pt-8 pb-[calc(4.75rem+env(safe-area-inset-bottom))] md:pb-6 lg:pb-8">
                    <ProfitBanner />
                    <div className="flex min-h-0 flex-1 flex-col">
                        {children}
                    </div>
                </div>
            </main>

            {moreOpen && (
                <button
                    type="button"
                    aria-label="Close menu"
                    className="md:hidden fixed inset-0 z-30 bg-black/40"
                    onClick={() => setMoreOpen(false)}
                />
            )}

            <nav
                className="md:hidden fixed bottom-0 inset-x-0 z-40 border-t border-border bg-card/95 backdrop-blur-md pb-[env(safe-area-inset-bottom)]"
                aria-label="Primary"
            >
                {moreOpen && (
                    <div id="app-more-menu" className="border-b border-border bg-card p-3 grid grid-cols-2 gap-2">
                        {MORE_ITEMS.map((item) => {
                            const active = isActive(pathname, item.href);
                            return (
                                <Link
                                    key={item.href}
                                    href={item.href}
                                    aria-current={active ? "page" : undefined}
                                    className={cn(
                                        "flex items-center gap-3 min-h-14 px-3 rounded-xl border text-sm font-medium",
                                        active
                                            ? "border-primary bg-accent text-foreground"
                                            : "border-border bg-background text-foreground"
                                    )}
                                >
                                    <item.icon className="w-5 h-5 shrink-0" />
                                    {item.label}
                                </Link>
                            );
                        })}
                    </div>
                )}
                <div className="grid grid-cols-5">
                    {MOBILE_TABS.map((tab) => {
                        const active = isActive(pathname, tab.href, tab.exact);
                        return (
                            <Link
                                key={tab.href}
                                href={tab.href}
                                aria-current={active ? "page" : undefined}
                                className={cn(
                                    "flex flex-col items-center justify-center gap-1 min-h-14 px-1 text-[11px] font-medium leading-none",
                                    active ? "text-foreground" : "text-muted-foreground"
                                )}
                            >
                                <tab.icon className={cn("w-5 h-5", active && "text-primary")} />
                                {tab.label}
                            </Link>
                        );
                    })}
                    <button
                        type="button"
                        aria-expanded={moreOpen}
                        aria-controls="app-more-menu"
                        onClick={() => setMoreOpen((open) => !open)}
                        className={cn(
                            "flex flex-col items-center justify-center gap-1 min-h-14 px-1 text-[11px] font-medium leading-none",
                            moreOpen || moreActive ? "text-foreground" : "text-muted-foreground"
                        )}
                    >
                        <MoreHorizontal className={cn("w-5 h-5", (moreOpen || moreActive) && "text-primary")} />
                        More
                    </button>
                </div>
            </nav>
            <ProfitSheet />
        </div>
        </ProfitNotificationProvider>
    );
}
