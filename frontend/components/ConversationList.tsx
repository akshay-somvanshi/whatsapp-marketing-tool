import type { ConversationOut } from '@/lib/api';

interface Props {
  conversations: ConversationOut[];
  selectedPhone: string | null;
  onSelect: (conv: ConversationOut) => void;
}

export function ConversationList({ conversations, selectedPhone, onSelect }: Props) {
  if (conversations.length === 0) {
    return <p className="p-4 text-center text-gray-400">No conversations yet.</p>;
  }

  return (
    <ul className="divide-y">
      {conversations.map(conv => (
        <li
          key={conv.id}
          role="button"
          tabIndex={0}
          onClick={() => onSelect(conv)}
          onKeyDown={e => e.key === 'Enter' && onSelect(conv)}
          className={`cursor-pointer p-4 hover:bg-gray-50 ${
            selectedPhone === conv.contact_phone
              ? 'border-l-4 border-green-500 bg-green-50'
              : ''
          }`}
        >
          <p className="font-medium">{conv.contact_phone}</p>
          <p className="mt-0.5 text-xs text-gray-500">
            {conv.session_status === 'active' ? '● Active' : '○ Expired'}
          </p>
        </li>
      ))}
    </ul>
  );
}
