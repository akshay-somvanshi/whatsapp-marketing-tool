'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { api } from '@/lib/api';
import { CampaignForm } from '@/components/CampaignForm';
import type { CampaignFormData } from '@/components/CampaignForm';

const TEMPLATES = ['hello_world', 'review_request'];

export default function NewCampaignPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (data: CampaignFormData) => {
    setLoading(true);
    setError('');
    try {
      await api.campaigns.create({
        name: data.name,
        template_name: data.template_name,
        audience_tags: data.audience_tags,
        scheduled_at: data.scheduled_at
          ? new Date(data.scheduled_at).toISOString()
          : null,
      });
      router.push('/campaigns');
    } catch {
      setError('Failed to create campaign. Please try again.');
      setLoading(false);
    }
  };

  return (
    <main className="mx-auto max-w-lg p-6">
      <h1 className="mb-6 text-2xl font-bold">New Campaign</h1>
      {error && (
        <p className="mb-4 rounded-lg bg-red-50 px-4 py-2 text-sm text-red-600">{error}</p>
      )}
      <div className="rounded-xl bg-white p-6 shadow">
        <CampaignForm templates={TEMPLATES} onSubmit={handleSubmit} loading={loading} />
      </div>
    </main>
  );
}
