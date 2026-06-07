import type { Metadata } from 'next';
import Link from 'next/link';
import './globals.css';

export const metadata: Metadata = {
  title: 'WhatsApp Marketing Platform',
  description: 'Customer re-engagement via WhatsApp',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50">
        <nav className="flex h-16 items-center gap-6 bg-white px-6 shadow">
          <span className="text-lg font-bold text-green-600">WA Marketing</span>
          <Link href="/" className="text-gray-600 hover:text-green-600">
            Dashboard
          </Link>
          <Link href="/contacts" className="text-gray-600 hover:text-green-600">
            Contacts
          </Link>
          <Link href="/campaigns" className="text-gray-600 hover:text-green-600">
            Campaigns
          </Link>
          <Link href="/inbox" className="text-gray-600 hover:text-green-600">
            Inbox
          </Link>
        </nav>
        {children}
      </body>
    </html>
  );
}
