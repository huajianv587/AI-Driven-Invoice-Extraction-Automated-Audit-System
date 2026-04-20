import type { Metadata } from "next";
import type { ReactNode } from "react";
import { IBM_Plex_Mono, Manrope, Orbitron } from "next/font/google";

import { Providers } from "@/components/providers";
import "@/app/globals.css";

const orbitron = Orbitron({
  subsets: ["latin"],
  weight: ["500", "600", "700", "800"],
  variable: "--font-display"
});

const manrope = Manrope({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-ui"
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["500", "600"],
  variable: "--font-mono"
});

export const metadata: Metadata = {
  title: "Invoice Operations Suite",
  description: "World-class invoice operations workspace for audit, routing, and recovery."
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html className={`${orbitron.variable} ${manrope.variable} ${plexMono.variable}`} lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
