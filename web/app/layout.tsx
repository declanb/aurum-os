import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { cn } from "@/lib/utils";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  title: "AURUM OS - AI Gold Trading Copilot",
  description: "AI-native gold trading copilot for disciplined discretionary execution.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className={cn(inter.variable, "min-h-screen bg-background font-sans text-foreground antialiased selection:bg-primary/20")}>
        {/* We will add ClerkProvider and App Shell Nav here later once libraries are added */}
        {children}
      </body>
    </html>
  );
}
