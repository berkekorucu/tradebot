
import type {Metadata} from 'next/font';
import {Geist, Geist_Mono} from 'next/font/google';
import './globals.css';
import {Toaster} from "@/components/ui/toaster";
import localFont from 'next/font/local'

const sfPro = localFont({
  src: [
    {
      path: './assets/fonts/SF-Pro-Display-Regular.woff2',
      weight: '400',
      style: 'normal',
    },
    {
      path: './assets/fonts/SF-Pro-Display-Medium.woff2',
      weight: '500',
      style: 'normal',
    },
    {
      path: './assets/fonts/SF-Pro-Display-Bold.woff2',
      weight: '700',
      style: 'normal',
    },
  ],
  variable: '--font-sf-pro-display',
})

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export const metadata: Metadata = {
  title: 'TradeWise',
  description: 'AI Powered Trading Bot Dashboard',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${sfPro.variable} ${geistSans.variable} ${geistMono.variable} antialiased`}>
        {children}
        <Toaster />
      </body>
    </html>
  );
}
