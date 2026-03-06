import Link from "next/link";
import { BarChart3, BookOpen, CheckSquare, Settings, ShieldAlert, FileText } from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";

export default function AppLayout({ children }: { children: React.ReactNode }) {
    return (
        <div className="flex min-h-screen bg-background">
            {/* Sidebar */}
            <aside className="w-64 border-r border-border bg-sidebar flex flex-col hidden md:flex">
                <div className="h-16 flex items-center px-6 border-b border-border">
                    <Link href="/" className="font-bold text-xl text-foreground tracking-tight">
                        AURUM <span className="text-primary">OS</span>
                    </Link>
                </div>

                <nav className="flex-1 overflow-y-auto px-4 py-6 space-y-1">
                    <Link href="/app" className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-accent text-accent-foreground font-medium">
                        <BarChart3 className="w-5 h-5" /> Dashboard
                    </Link>
                    <Link href="/app/analysis" className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent transition-colors">
                        <CheckSquare className="w-5 h-5" /> Market Analysis
                    </Link>
                    <Link href="/app/planner" className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent transition-colors">
                        <FileText className="w-5 h-5" /> Trade Planner
                    </Link>
                    <Link href="/app/approvals" className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent transition-colors">
                        <ShieldAlert className="w-5 h-5" /> Approvals
                    </Link>
                    <Link href="/app/journal" className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent transition-colors">
                        <BookOpen className="w-5 h-5" /> Journal
                    </Link>
                </nav>

                <div className="p-4 border-t border-border">
                    <Link href="/app/settings" className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent transition-colors">
                        <Settings className="w-5 h-5" /> Settings
                    </Link>
                </div>
            </aside>

            {/* Main Content */}
            <main className="flex-1 flex flex-col">
                <header className="h-16 border-b border-border bg-background/80 backdrop-blur-md flex items-center justify-between px-6 lg:px-8 sticky top-0 z-10">
                    <h2 className="text-sm font-medium text-muted-foreground">Workspace / <span className="text-foreground">Overview</span></h2>
                    <div className="flex items-center gap-4">
                        <div className="flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider hidden sm:inline-block">Agents Ready</span>
                        </div>
                        <ThemeToggle />
                        <div className="w-8 h-8 rounded-full bg-muted border border-border flex items-center justify-center text-xs text-foreground cursor-pointer hover:bg-accent transition">
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
