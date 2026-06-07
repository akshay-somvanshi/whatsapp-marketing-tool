'use client';

import { useState } from 'react';
import type { Contact } from '@/lib/api';

export function ContactsTable({ contacts }: { contacts: Contact[] }) {
  const [search, setSearch] = useState('');

  const filtered = contacts.filter(
    c =>
      c.name.toLowerCase().includes(search.toLowerCase()) ||
      c.phone.includes(search),
  );

  return (
    <div>
      <input
        type="text"
        placeholder="Search contacts..."
        value={search}
        onChange={e => setSearch(e.target.value)}
        className="mb-4 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
      />
      <div className="overflow-x-auto rounded-xl shadow">
        <table className="min-w-full bg-white text-sm">
          <thead className="bg-gray-50 text-gray-600 uppercase text-xs">
            <tr>
              <th className="px-4 py-3 text-left">Name</th>
              <th className="px-4 py-3 text-left">Phone</th>
              <th className="px-4 py-3 text-left">Opted In</th>
              <th className="px-4 py-3 text-left">Tags</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {filtered.map(c => (
              <tr key={c.id} className="hover:bg-gray-50">
                <td className="px-4 py-3">{c.name}</td>
                <td className="px-4 py-3">{c.phone}</td>
                <td className="px-4 py-3">{c.opted_in ? 'Yes' : 'No'}</td>
                <td className="px-4 py-3">{c.tags.join(', ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {filtered.length === 0 && (
        <p className="mt-6 text-center text-gray-400">No contacts found.</p>
      )}
    </div>
  );
}
