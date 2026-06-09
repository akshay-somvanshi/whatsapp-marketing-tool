'use client';

import { useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import type { Contact } from '@/lib/api';
import { ContactsTable } from '@/components/ContactsTable';

type ModalMode = 'add' | 'edit';

export default function ContactsPage() {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalMode, setModalMode] = useState<ModalMode>('add');
  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState({ name: '', phone: '', opted_in: false, tags: '' });
  const [formError, setFormError] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  const load = () =>
    api.contacts.list().then(setContacts).finally(() => setLoading(false));

  useEffect(() => {
    load();
  }, []);

  const openAdd = () => {
    setModalMode('add');
    setEditingId(null);
    setForm({ name: '', phone: '', opted_in: false, tags: '' });
    setFormError('');
    setShowModal(true);
  };

  const openEdit = (contact: Contact) => {
    setModalMode('edit');
    setEditingId(contact.id);
    setForm({ name: contact.name, phone: contact.phone, opted_in: contact.opted_in, tags: contact.tags.join(', ') });
    setFormError('');
    setShowModal(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');
    const tags = form.tags.split(',').map(t => t.trim()).filter(Boolean);
    try {
      if (modalMode === 'add') {
        await api.contacts.create({ name: form.name, phone: form.phone, opted_in: form.opted_in, tags });
      } else if (editingId) {
        await api.contacts.update(editingId, { name: form.name, opted_in: form.opted_in, tags });
      }
      setShowModal(false);
      load();
    } catch {
      setFormError(modalMode === 'add'
        ? 'Failed to create contact. Check phone number format (+E.164).'
        : 'Failed to update contact.');
    }
  };

  const handleDelete = async (contact: Contact) => {
    if (!confirm(`Delete ${contact.name}? This cannot be undone.`)) return;
    try {
      await api.contacts.delete(contact.id);
      load();
    } catch {
      alert('Failed to delete contact.');
    }
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const res = await api.contacts.import(file);
      alert(`Imported ${res.imported}, skipped ${res.skipped}`);
      load();
    } catch {
      alert('Import failed. Make sure the CSV has a "phone" column.');
    } finally {
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  if (loading) return <div className="p-6">Loading...</div>;

  return (
    <main className="p-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Contacts ({contacts.length})</h1>
        <div className="flex gap-2">
          <button
            onClick={() => fileRef.current?.click()}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm hover:bg-gray-50"
          >
            Import CSV
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={handleImport}
          />
          <button
            onClick={openAdd}
            className="rounded-lg bg-green-600 px-3 py-2 text-sm font-medium text-white hover:bg-green-700"
          >
            Add Contact
          </button>
        </div>
      </div>

      <ContactsTable contacts={contacts} onEdit={openEdit} onDelete={handleDelete} />

      {showModal && (
        <div className="fixed inset-0 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
            <h2 className="mb-4 text-lg font-bold">
              {modalMode === 'add' ? 'Add Contact' : 'Edit Contact'}
            </h2>
            <form onSubmit={handleSubmit} className="flex flex-col gap-3">
              {formError && <p className="text-sm text-red-600">{formError}</p>}
              <input
                required
                placeholder="Name"
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
              />
              {modalMode === 'add' && (
                <input
                  required
                  placeholder="+919876543210"
                  value={form.phone}
                  onChange={e => setForm(f => ({ ...f, phone: e.target.value }))}
                  className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
                />
              )}
              <input
                placeholder="Tags (comma-separated)"
                value={form.tags}
                onChange={e => setForm(f => ({ ...f, tags: e.target.value }))}
                className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
              />
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={form.opted_in}
                  onChange={e => setForm(f => ({ ...f, opted_in: e.target.checked }))}
                />
                Opted in to WhatsApp marketing
              </label>
              <div className="mt-1 flex gap-2">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="flex-1 rounded-lg border border-gray-300 py-2 text-sm hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="flex-1 rounded-lg bg-green-600 py-2 text-sm font-medium text-white hover:bg-green-700"
                >
                  {modalMode === 'add' ? 'Save' : 'Update'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </main>
  );
}
