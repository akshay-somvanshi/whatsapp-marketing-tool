'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { Campaign } from '@/lib/api';

const STATUS_STYLE: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700',
  scheduled: 'bg-blue-100 text-blue-700',
  running: 'bg-yellow-100 text-yellow-700',
  completed: 'bg-green-100 text-green-700',
};

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.campaigns.list().then(setCampaigns).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-6">Loading...</div>;

  return (
    <main className="p-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Campaigns</h1>
        <Link
          href="/campaigns/new"
          className="rounded-lg bg-green-600 px-3 py-2 text-sm font-medium text-white hover:bg-green-700"
        >
          New Campaign
        </Link>
      </div>

      {campaigns.length === 0 ? (
        <p className="text-gray-500">
          No campaigns yet.{' '}
          <Link href="/campaigns/new" className="text-green-600 underline">
            Create one
          </Link>
          .
        </p>
      ) : (
        <div className="space-y-3">
          {campaigns.map(c => (
            <div
              key={c.id}
              className="flex items-start justify-between rounded-xl bg-white p-4 shadow"
            >
              <div>
                <h2 className="font-semibold">{c.name}</h2>
                <p className="text-sm text-gray-500">Template: {c.template_name}</p>
                <p className="text-sm text-gray-500">
                  Tags: {c.audience_tags.join(', ') || '—'}
                </p>
              </div>
              <div className="text-right">
                <span
                  className={`rounded-full px-2 py-1 text-xs font-medium ${STATUS_STYLE[c.status] ?? ''}`}
                >
                  {c.status}
                </span>
                <p className="mt-2 text-sm text-gray-600">
                  Sent: {c.sent_count} · Delivered: {c.delivered_count} · Read: {c.read_count}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
