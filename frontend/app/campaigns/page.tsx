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

const EDITABLE_STATUSES = new Set(['draft', 'scheduled']);

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingCampaign, setEditingCampaign] = useState<Campaign | null>(null);
  const [editForm, setEditForm] = useState({ name: '', audience_tags: '', scheduled_at: '' });
  const [editError, setEditError] = useState('');

  const load = () =>
    api.campaigns.list().then(setCampaigns).finally(() => setLoading(false));

  useEffect(() => {
    load();
  }, []);

  const openEdit = (c: Campaign) => {
    setEditingCampaign(c);
    setEditForm({
      name: c.name,
      audience_tags: c.audience_tags.join(', '),
      scheduled_at: c.scheduled_at ? c.scheduled_at.slice(0, 16) : '',
    });
    setEditError('');
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingCampaign) return;
    setEditError('');
    try {
      await api.campaigns.update(editingCampaign.id, {
        name: editForm.name,
        audience_tags: editForm.audience_tags.split(',').map(t => t.trim()).filter(Boolean),
        scheduled_at: editForm.scheduled_at || null,
      });
      setEditingCampaign(null);
      load();
    } catch {
      setEditError('Failed to update campaign.');
    }
  };

  const handleDelete = async (c: Campaign) => {
    if (!confirm(`Delete campaign "${c.name}"? This cannot be undone.`)) return;
    try {
      await api.campaigns.delete(c.id);
      load();
    } catch {
      alert('Failed to delete campaign.');
    }
  };

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
                <p className="text-sm text-gray-500">
                  Scheduled: {formatDate(c.scheduled_at)}
                </p>
              </div>
              <div className="flex flex-col items-end gap-2">
                <span
                  className={`rounded-full px-2 py-1 text-xs font-medium ${STATUS_STYLE[c.status] ?? ''}`}
                >
                  {c.status}
                </span>
                <p className="text-sm text-gray-600">
                  Sent: {c.sent_count} · Delivered: {c.delivered_count} · Read: {c.read_count}
                </p>
                <div className="flex gap-2">
                  {EDITABLE_STATUSES.has(c.status) && (
                    <button
                      onClick={() => openEdit(c)}
                      className="text-sm text-blue-600 hover:underline"
                    >
                      Edit
                    </button>
                  )}
                  <button
                    onClick={() => handleDelete(c)}
                    className="text-sm text-red-500 hover:underline"
                  >
                    Delete
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {editingCampaign && (
        <div className="fixed inset-0 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
            <h2 className="mb-4 text-lg font-bold">Edit Campaign</h2>
            <form onSubmit={handleEditSubmit} className="flex flex-col gap-3">
              {editError && <p className="text-sm text-red-600">{editError}</p>}
              <div className="flex flex-col gap-1">
                <label className="text-sm font-medium">Campaign Name</label>
                <input
                  required
                  value={editForm.name}
                  onChange={e => setEditForm(f => ({ ...f, name: e.target.value }))}
                  className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-sm font-medium">Audience Tags (comma-separated)</label>
                <input
                  value={editForm.audience_tags}
                  onChange={e => setEditForm(f => ({ ...f, audience_tags: e.target.value }))}
                  placeholder="purchased, vip"
                  className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-sm font-medium">Schedule (optional)</label>
                <input
                  type="datetime-local"
                  value={editForm.scheduled_at}
                  onChange={e => setEditForm(f => ({ ...f, scheduled_at: e.target.value }))}
                  className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
                />
              </div>
              <div className="mt-1 flex gap-2">
                <button
                  type="button"
                  onClick={() => setEditingCampaign(null)}
                  className="flex-1 rounded-lg border border-gray-300 py-2 text-sm hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="flex-1 rounded-lg bg-green-600 py-2 text-sm font-medium text-white hover:bg-green-700"
                >
                  Update
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </main>
  );
}
