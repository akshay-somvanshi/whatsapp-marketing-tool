'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { Campaign, Contact, ConversationOut } from '@/lib/api';

function StatCard({ label, value }: { label: string; value: number }) {
  const testId = `stat-${label.toLowerCase().replace(/ /g, '-')}`;
  return (
    <div className="rounded-xl bg-white p-6 shadow">
      <dt className="text-sm text-gray-500">{label}</dt>
      <dd className="mt-1 text-3xl font-bold text-gray-900" data-testid={testId}>
        {value}
      </dd>
    </div>
  );
}

export default function DashboardPage() {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [conversations, setConversations] = useState<ConversationOut[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.contacts.list(), api.conversations.list(), api.campaigns.list()])
      .then(([c, cv, ca]) => {
        setContacts(c);
        setConversations(cv);
        setCampaigns(ca);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-6">Loading...</div>;

  const activeConvs = conversations.filter(c => c.session_status === 'active').length;
  const now = new Date();
  const thisMonthCampaigns = campaigns.filter(c => {
    const d = new Date(c.created_at);
    return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
  }).length;

  return (
    <main className="p-6">
      <h1 className="mb-6 text-2xl font-bold">Dashboard</h1>
      <dl className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard label="Total Contacts" value={contacts.length} />
        <StatCard label="Active Conversations" value={activeConvs} />
        <StatCard label="Campaigns This Month" value={thisMonthCampaigns} />
      </dl>
    </main>
  );
}
