import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import { Geist_Mono } from "next/font/google";
import Sidebar from "@/components/Sidebar";
import ServiceWorkerRegister from "@/components/ServiceWorkerRegister";
import "katex/dist/katex.min.css";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Viewport export: Next.js 14+ dedicated configuration for viewport meta tags.
// - width: "device-width" adapts the layout to mobile phone screen dimensions.
// - initialScale / maximumScale: locks initial viewport zoom to prevent awkward double-tap zooms in PWA mode.
// - themeColor: sets the browser address bar / mobile status bar background color to match the dark theme.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  themeColor: "#0a0a0f",
};

// Application-wide document metadata
// - appleWebApp: enables iOS Safari PWA standalone capability with translucent status bar styling.
export const metadata: Metadata = {
  title: "Nexus",
  description:
    "Personal Knowledge Workspace and Engine Control Panel for the Nexus Agentic Engine.",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "Nexus",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex bg-bg-primary text-text-primary">
        <ServiceWorkerRegister />
        <Sidebar />
        {/* pb-16 md:pb-0 reserves 4rem (64px) bottom clearance on mobile viewports (< 768px) so page content is never obscured behind the fixed h-16 mobile bottom navigation bar */}
        <main className="flex-1 overflow-y-auto pb-16 md:pb-0 min-w-0">{children}</main>
      </body>
    </html>
  );
}
