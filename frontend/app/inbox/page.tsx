'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { ConversationDetail, ConversationOut } from '@/lib/api';
import { ConversationList } from '@/components/ConversationList';
import { MessageThread } from '@/components/MessageThread';

export default function InboxPage() {
  const [conversations, setConversations] = useState<ConversationOut[]>([]);
  const [selected, setSelected] = useState<ConversationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [threadLoading, setThreadLoading] = useState(false);
  const [replyText, setReplyText] = useState('');
  const [sending, setSending] = useState(false);

  useEffect(() => {
    api.conversations.list().then(setConversations).finally(() => setLoading(false));
  }, []);

  const handleSelect = async (conv: ConversationOut) => {
    setThreadLoading(true);
    try {
      const detail = await api.conversations.get(conv.contact_phone);
      setSelected(detail);
    } finally {
      setThreadLoading(false);
    }
  };

  const toggleAI = async () => {
    if (!selected) return;
    const updated = await api.conversations.patch(selected.contact_phone, {
      ai_enabled: !selected.ai_enabled,
    });
    setSelected(s => (s ? { ...s, ai_enabled: updated.ai_enabled } : s));
  };

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selected || !replyText.trim()) return;
    setSending(true);
    try {
      const msg = await api.conversations.sendMessage(selected.contact_phone, replyText.trim());
      setSelected(s => s ? { ...s, messages: [...s.messages, msg] } : s);
      setReplyText('');
    } finally {
      setSending(false);
    }
  };

  if (loading) return <div className="p-6">Loading...</div>;

  return (
    <main className="flex" style={{ height: 'calc(100vh - 64px)' }}>
      <aside className="w-80 overflow-y-auto border-r bg-white">
        <h2 className="border-b p-4 text-lg font-bold">Inbox</h2>
        <ConversationList
          conversations={conversations}
          selectedPhone={selected?.contact_phone ?? null}
          onSelect={handleSelect}
        />
      </aside>

      <section className="flex flex-1 flex-col">
        {selected ? (
          <>
            <div className="flex items-center justify-between border-b p-4">
              <div>
                <p className="font-semibold">{selected.contact_phone}</p>
                <p className="text-xs text-gray-500">
                  Session: {selected.session_status} · AI:{' '}
                  {selected.ai_enabled ? 'on' : 'off'}
                </p>
              </div>
              <button
                onClick={toggleAI}
                className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50"
              >
                {selected.ai_enabled ? 'Disable AI' : 'Enable AI'}
              </button>
            </div>
            <div className="flex-1 overflow-y-auto">
              {threadLoading ? (
                <p className="py-8 text-center text-gray-400">Loading messages...</p>
              ) : (
                <MessageThread messages={selected.messages} />
              )}
            </div>
            <form onSubmit={handleSend} className="flex gap-2 border-t p-3">
              <input
                type="text"
                value={replyText}
                onChange={e => setReplyText(e.target.value)}
                placeholder={selected.ai_enabled ? 'AI is handling this conversation…' : 'Reply as human…'}
                className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
              />
              <button
                type="submit"
                disabled={sending || !replyText.trim()}
                className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
              >
                Send
              </button>
            </form>
          </>
        ) : (
          <div className="flex flex-1 items-center justify-center text-gray-400">
            Select a conversation to view messages
          </div>
        )}
      </section>
    </main>
  );
}
