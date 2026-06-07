'use client';

import { useState } from 'react';

export interface CampaignFormData {
  name: string;
  template_name: string;
  audience_tags: string[];
  scheduled_at: string | null;
}

interface Props {
  templates: string[];
  onSubmit: (data: CampaignFormData) => void;
  loading?: boolean;
}

export function CampaignForm({ templates, onSubmit, loading = false }: Props) {
  const [name, setName] = useState('');
  const [templateName, setTemplateName] = useState(templates[0] ?? '');
  const [tagsInput, setTagsInput] = useState('');
  const [scheduledAt, setScheduledAt] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError('Campaign name is required');
      return;
    }
    setError('');
    const tags = tagsInput
      .split(',')
      .map(t => t.trim())
      .filter(Boolean);
    onSubmit({
      name: name.trim(),
      template_name: templateName,
      audience_tags: tags,
      scheduled_at: scheduledAt || null,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      {error && (
        <p role="alert" className="rounded-lg bg-red-50 px-4 py-2 text-sm text-red-600">
          {error}
        </p>
      )}

      <div className="flex flex-col gap-1">
        <label htmlFor="campaign-name" className="text-sm font-medium">
          Campaign Name
        </label>
        <input
          id="campaign-name"
          type="text"
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder="e.g. Summer Sale"
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="template" className="text-sm font-medium">
          Template
        </label>
        <select
          id="template"
          value={templateName}
          onChange={e => setTemplateName(e.target.value)}
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
        >
          {templates.map(t => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="tags" className="text-sm font-medium">
          Audience Tags (comma-separated)
        </label>
        <input
          id="tags"
          type="text"
          value={tagsInput}
          onChange={e => setTagsInput(e.target.value)}
          placeholder="purchased, vip"
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="schedule" className="text-sm font-medium">
          Schedule (optional)
        </label>
        <input
          id="schedule"
          type="datetime-local"
          value={scheduledAt}
          onChange={e => setScheduledAt(e.target.value)}
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
        />
      </div>

      <button
        type="submit"
        disabled={loading}
        className="mt-2 rounded-lg bg-green-600 px-4 py-2 font-medium text-white hover:bg-green-700 disabled:opacity-50"
      >
        {loading ? 'Creating...' : 'Create Campaign'}
      </button>
    </form>
  );
}
