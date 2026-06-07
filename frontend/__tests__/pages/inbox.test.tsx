import '@testing-library/jest-dom';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import InboxPage from '@/app/inbox/page';
import { api } from '@/lib/api';

// Factory must NOT reference outer variables (jest.mock is hoisted before const declarations).
jest.mock('@/lib/api', () => ({
  api: {
    conversations: {
      list: jest.fn(),
      get: jest.fn(),
      patch: jest.fn(),
    },
  },
}));

const listMock = api.conversations.list as jest.Mock;
const getMock = api.conversations.get as jest.Mock;
const patchMock = api.conversations.patch as jest.Mock;

const MOCK_CONV = {
  id: 'c1',
  contact_phone: '+919876543210',
  status: 'active',
  session_status: 'active',
  ai_enabled: true,
  session_expires_at: '',
  updated_at: '',
};

const MOCK_DETAIL = {
  ...MOCK_CONV,
  messages: [
    {
      id: 'm1',
      contact_phone: '+919876543210',
      direction: 'inbound' as const,
      body: 'Hello from customer',
      status: 'sent',
      wa_message_id: null,
      template_name: null,
      created_at: '2024-01-01T10:00:00Z',
    },
    {
      id: 'm2',
      contact_phone: '+919876543210',
      direction: 'outbound' as const,
      body: 'Thanks for reaching out!',
      status: 'delivered',
      wa_message_id: 'wamid.001',
      template_name: null,
      created_at: '2024-01-01T10:01:00Z',
    },
  ],
};

beforeEach(() => {
  listMock.mockResolvedValue([MOCK_CONV]);
  getMock.mockResolvedValue(MOCK_DETAIL);
  patchMock.mockResolvedValue({ ...MOCK_CONV, ai_enabled: false });
  jest.clearAllMocks();
  // Re-apply after clearAllMocks wipes return values
  listMock.mockResolvedValue([MOCK_CONV]);
  getMock.mockResolvedValue(MOCK_DETAIL);
  patchMock.mockResolvedValue({ ...MOCK_CONV, ai_enabled: false });
});

describe('InboxPage', () => {
  it('shows loading state initially', () => {
    render(<InboxPage />);
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('shows conversation list after loading', async () => {
    render(<InboxPage />);
    await waitFor(() =>
      expect(screen.getByText('+919876543210')).toBeInTheDocument(),
    );
  });

  it('shows empty-state prompt before a conversation is selected', async () => {
    render(<InboxPage />);
    await waitFor(() => screen.getByText('+919876543210'));
    expect(screen.getByText(/select a conversation/i)).toBeInTheDocument();
  });

  it('loads message thread when a conversation is clicked', async () => {
    render(<InboxPage />);
    await waitFor(() => screen.getByText('+919876543210'));
    fireEvent.click(screen.getByText('+919876543210'));
    await waitFor(() =>
      expect(screen.getByText('Hello from customer')).toBeInTheDocument(),
    );
    expect(screen.getByText('Thanks for reaching out!')).toBeInTheDocument();
  });

  it('hides empty-state after conversation is selected', async () => {
    render(<InboxPage />);
    await waitFor(() => screen.getByText('+919876543210'));
    fireEvent.click(screen.getByText('+919876543210'));
    await waitFor(() => screen.getByText('Hello from customer'));
    expect(screen.queryByText(/select a conversation/i)).not.toBeInTheDocument();
  });

  it('shows AI toggle button after conversation is selected', async () => {
    render(<InboxPage />);
    await waitFor(() => screen.getByText('+919876543210'));
    fireEvent.click(screen.getByText('+919876543210'));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /disable ai/i })).toBeInTheDocument(),
    );
  });
});
