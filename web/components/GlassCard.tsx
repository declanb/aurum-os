import { cn } from "@/lib/utils";
import React from "react";

interface GlassCardProps extends React.HTMLAttributes<HTMLDivElement> {
    children: React.ReactNode;
}

export function GlassCard({ children, className, ...props }: GlassCardProps) {
    return (
        <div
            className={cn(
                "backdrop-blur-xl bg-slate-900/40 border border-slate-800 shadow-xl rounded-2xl",
                "transition-colors duration-300",
                className
            )}
            {...props}
        >
            {children}
        </div>
    );
}
