import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Suspense } from "react";
import { AppShell } from "@/components/app-shell";
import { Providers } from "@/components/providers";
import { Spinner } from "@/components/ui";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin", "latin-ext"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin", "latin-ext"] });

export const metadata: Metadata = {
  title: "Cyfrowy Asystent Ocen Okresowych",
  description: "Ocena okresowa w służbie cywilnej wspierana przez AI - AI sugeruje, człowiek decyduje.",
};

// Cała aplikacja jest za logowaniem, a sesja żyje w localStorage, więc powłoka (AppShell) renderuje się
// celowo tylko w przeglądarce (`use(browser())`). Wyłączamy walidację „instant UI” dla całego drzewa,
// zamiast udawać statyczny serwerowy shell dla danych, które istnieją tylko po zalogowaniu.
export const instant = false;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="pl" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full">
        <Providers>
          <Suspense fallback={<Spinner />}>
            <AppShell>{children}</AppShell>
          </Suspense>
        </Providers>
      </body>
    </html>
  );
}
