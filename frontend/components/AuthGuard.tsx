'use client';

import { useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import Link from 'next/link';
import { clearTokens, isAuthenticated } from '@/lib/auth';

const PUBLIC_PATHS = ['/login'];

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [ready, setReady] = useState(false);

  const isPublic = PUBLIC_PATHS.includes(pathname);

  useEffect(() => {
    if (!isPublic && !isAuthenticated()) {
      router.replace('/login');
      return;
    }
    setReady(true);
  }, [isPublic, pathname, router]);

  // Login page renders without the app chrome.
  if (isPublic) return <>{children}</>;

  // Avoid flashing protected content before the auth check resolves.
  if (!ready) return null;

  function logout() {
    clearTokens();
    router.replace('/login');
  }

  return (
    <>
      <nav className="flex h-16 items-center gap-6 bg-white px-6 shadow">
        <span className="text-lg font-bold text-green-600">WA Marketing</span>
        <Link href="/" className="text-gray-600 hover:text-green-600">Dashboard</Link>
        <Link href="/contacts" className="text-gray-600 hover:text-green-600">Contacts</Link>
        <Link href="/campaigns" className="text-gray-600 hover:text-green-600">Campaigns</Link>
        <Link href="/inbox" className="text-gray-600 hover:text-green-600">Inbox</Link>
        <button
          onClick={logout}
          className="ml-auto text-sm text-gray-500 hover:text-red-600"
        >
          Log out
        </button>
      </nav>
      {children}
    </>
  );
}
