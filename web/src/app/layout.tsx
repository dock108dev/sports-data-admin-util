import type { Metadata } from "next";
import type { ReactNode } from "react";

import "@dock108/ui/theme.css";
import "./globals.css";

import { DockFooter, DockHeader } from "@dock108/ui";

export const metadata: Metadata = {
  title: "Sports Admin - dock108",
  description: "Centralized sports data administration for Dock108 apps",
  icons: {
    icon: "/favicon.svg",
  },
};

/**
 * Root layout for the sports-data-admin web app.
 *
 * Provides consistent header/footer via shared DockHeader/DockFooter components
 * and applies global theme styles from @dock108/ui.
 *
 * This app provides sports data administration with integration to the
 * sports-data API backend and sports-data-scraper service for data ingestion.
 */
export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <div className="app-shell">
          <DockHeader />
          <main className="app-main">{children}</main>
          <DockFooter />
        </div>
      </body>
    </html>
  );
}

