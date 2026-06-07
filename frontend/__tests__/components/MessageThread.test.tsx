import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import { MessageThread } from '@/components/MessageThread';
import type { MessageOut } from '@/lib/api';

const messages: MessageOut[] = [
  {
    id: '1',
    contact_phone: '+919876543210',
    direction: 'inbound',
    body: 'Hello, do you have gold bangles?',
    status: 'sent',
    wa_message_id: 'wamid.001',
    template_name: null,
    created_at: '2024-01-01T10:00:00Z',
  },
  {
    id: '2',
    contact_phone: '+919876543210',
    direction: 'outbound',
    body: 'Yes! We have a beautiful range of gold bangles.',
    status: 'delivered',
    wa_message_id: 'wamid.002',
    template_name: null,
    created_at: '2024-01-01T10:01:00Z',
  },
];

describe('MessageThread', () => {
  it('renders all message bodies', () => {
    render(<MessageThread messages={messages} />);
    expect(screen.getByText('Hello, do you have gold bangles?')).toBeInTheDocument();
    expect(
      screen.getByText('Yes! We have a beautiful range of gold bangles.'),
    ).toBeInTheDocument();
  });

  it('marks inbound messages with data-direction="inbound"', () => {
    render(<MessageThread messages={messages} />);
    const bubble = screen
      .getByText('Hello, do you have gold bangles?')
      .closest('[data-direction]');
    expect(bubble).toHaveAttribute('data-direction', 'inbound');
  });

  it('marks outbound messages with data-direction="outbound"', () => {
    render(<MessageThread messages={messages} />);
    const bubble = screen
      .getByText('Yes! We have a beautiful range of gold bangles.')
      .closest('[data-direction]');
    expect(bubble).toHaveAttribute('data-direction', 'outbound');
  });

  it('shows empty-state text when no messages', () => {
    render(<MessageThread messages={[]} />);
    expect(screen.getByText(/no messages yet/i)).toBeInTheDocument();
  });

  it('renders a single message correctly', () => {
    render(<MessageThread messages={[messages[0]]} />);
    expect(screen.getByText('Hello, do you have gold bangles?')).toBeInTheDocument();
    expect(
      screen.queryByText('Yes! We have a beautiful range of gold bangles.'),
    ).not.toBeInTheDocument();
  });
});
