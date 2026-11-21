import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Source_Serif_4 } from "next/font/google";
import { Suspense } from "react";
import { AppShell } from "@/components/app-shell";
import { Providers } from "@/components/providers";
import { Spinner } from "@/components/ui";
import "./globals.css";

// Typografia urzędowego dokumentu: szeryfowe nagłówki (jak w arkuszu i poradniku KPRM) + czytelny krój do pracy
const plexSans = IBM_Plex_Sans({ variable: "--font-plex-sans", subsets: ["latin", "latin-ext"] });
const serif = Source_Serif_4({ variable: "--font-serif-doc", subsets: ["latin", "latin-ext"] });
const plexMono = IBM_Plex_Mono({ variable: "--font-plex-mono", subsets: ["latin", "latin-ext"], weight: ["400", "500"] });

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
    <html lang="pl" className={`${plexSans.variable} ${serif.variable} ${plexMono.variable} h-full antialiased`}>
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
