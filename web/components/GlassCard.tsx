import { cn } from "@/lib/utils";
import React from "react";

interface GlassCardProps extends React.HTMLAttributes<HTMLDivElement> {
    children: React.ReactNode;
}

export function GlassCard({ children, className, ...props }: GlassCardProps) {
    return (
        <div
            className={cn(
                "rounded-2xl border border-border bg-card shadow-sm",
                "transition-colors duration-300",
                className
            )}
            {...props}
        >
            {children}
        </div>
    );
}
