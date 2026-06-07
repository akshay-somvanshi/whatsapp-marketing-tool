import type { MessageOut } from '@/lib/api';

export function MessageThread({ messages }: { messages: MessageOut[] }) {
  if (messages.length === 0) {
    return <p className="py-8 text-center text-gray-400">No messages yet.</p>;
  }

  return (
    <div className="flex flex-col gap-3 p-4">
      {messages.map(msg => (
        <div
          key={msg.id}
          data-direction={msg.direction}
          className={`max-w-[70%] rounded-2xl px-4 py-2 text-sm ${
            msg.direction === 'inbound'
              ? 'self-start bg-gray-100 text-gray-900'
              : 'self-end bg-green-500 text-white'
          }`}
        >
          <p>{msg.body}</p>
          <span className="mt-1 block text-xs opacity-60">
            {new Date(msg.created_at).toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        </div>
      ))}
    </div>
  );
}
