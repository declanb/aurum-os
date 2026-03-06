import Link from "next/link";
import { BarChart3, BookOpen, CheckSquare, Settings, ShieldAlert, FileText } from "lucide-react";

export default function AppLayout({ children }: { children: React.ReactNode }) {
    return (
        <div className="flex min-h-screen bg-[#0A0A0B]">
            {/* Sidebar */}
            <aside className="w-64 border-r border-slate-800 bg-slate-950/80 backdrop-blur-xl flex flex-col hidden md:flex">
                <div className="h-16 flex items-center px-6 border-b border-slate-800">
                    <Link href="/" className="font-bold text-xl text-white tracking-tight">
                        AURUM <span className="text-amber-500">OS</span>
                    </Link>
                </div>

                <nav className="flex-1 overflow-y-auto px-4 py-6 space-y-1">
                    <Link href="/app" className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-slate-900 text-amber-500 font-medium">
                        <BarChart3 className="w-5 h-5" /> Dashboard
                    </Link>
                    <Link href="/app/analysis" className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-900/50 transition-colors">
                        <CheckSquare className="w-5 h-5" /> Market Analysis
                    </Link>
                    <Link href="/app/planner" className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-900/50 transition-colors">
                        <FileText className="w-5 h-5" /> Trade Planner
                    </Link>
                    <Link href="/app/approvals" className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-900/50 transition-colors">
                        <ShieldAlert className="w-5 h-5" /> Approvals
                    </Link>
                    <Link href="/app/journal" className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-900/50 transition-colors">
                        <BookOpen className="w-5 h-5" /> Journal
                    </Link>
                </nav>

                <div className="p-4 border-t border-slate-800">
                    <Link href="/app/settings" className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-900/50 transition-colors">
                        <Settings className="w-5 h-5" /> Settings
                    </Link>
                </div>
            </aside>

            {/* Main Content */}
            <main className="flex-1 flex flex-col">
                <header className="h-16 border-b border-slate-800 bg-slate-950/50 backdrop-blur-md flex items-center justify-between px-6 lg:px-8 sticky top-0 z-10">
                    <h2 className="text-sm font-medium text-slate-400">Workspace / <span className="text-white">Overview</span></h2>
                    <div className="flex items-center gap-4">
                        <div className="flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider hidden sm:inline-block">Agents Ready</span>
                        </div>
                        <div className="w-8 h-8 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-xs text-white cursor-pointer hover:bg-slate-700 transition">
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
