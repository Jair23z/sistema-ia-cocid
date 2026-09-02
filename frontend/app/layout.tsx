import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Image from "next/image";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Análisis científico COCID",
  description: "Consulta de publicaciones científicas mediante OpenAlex.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="es"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <header className="border-b border-cocid-navy/10 bg-cocid-white">
          <div className="px-4 sm:px-6 lg:px-8">
            <div className="mx-auto flex w-full max-w-4xl items-center gap-4 py-4 sm:gap-6 sm:py-5">
              <Image
                alt=""
                className="h-20 w-auto shrink-0 object-contain sm:h-24"
                height={2440}
                priority
                sizes="(min-width: 640px) 78px, 65px"
                src="/branding/cocid-logo-standard.png"
                unoptimized
                width={1967}
              />
              <div className="min-w-0">
                <p className="text-xl font-bold leading-none tracking-[0.08em] text-cocid-navy sm:text-2xl">
                  COCID
                </p>
                <p className="mt-1 max-w-lg text-sm leading-5 text-cocid-graphite/80 sm:text-base sm:leading-6">
                  Colegio Universitario Científico de Datos
                </p>
                <div className="mt-2 flex items-center gap-2">
                  <span
                    aria-hidden="true"
                    className="h-0.5 w-6 shrink-0 bg-cocid-gold"
                  />
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-cocid-navy sm:text-sm">
                    Análisis científico
                  </p>
                </div>
              </div>
            </div>
          </div>
        </header>
        {children}
      </body>
    </html>
  );
}
