import '@testing-library/jest-dom';
import { render, screen, waitFor } from '@testing-library/react';
import DashboardPage from '@/app/page';

jest.mock('@/lib/api', () => ({
  api: {
    contacts: {
      list: jest.fn().mockResolvedValue([
        {
          id: '1',
          name: 'Priya',
          phone: '+919876543210',
          opted_in: true,
          tags: [],
          created_at: '',
        },
        {
          id: '2',
          name: 'Rahul',
          phone: '+919876543211',
          opted_in: false,
          tags: [],
          created_at: '',
        },
      ]),
    },
    conversations: {
      list: jest.fn().mockResolvedValue([
        {
          id: 'c1',
          contact_phone: '+919876543210',
          status: 'active',
          session_status: 'active',
          ai_enabled: true,
          session_expires_at: '',
          updated_at: '',
        },
        {
          id: 'c2',
          contact_phone: '+919876543211',
          status: 'expired',
          session_status: 'expired',
          ai_enabled: false,
          session_expires_at: '',
          updated_at: '',
        },
      ]),
    },
    campaigns: {
      list: jest.fn().mockResolvedValue([
        {
          id: 'ca1',
          name: 'Test Campaign',
          template_name: 'review_request',
          template_params: {},
          audience_tags: [],
          scheduled_at: null,
          status: 'completed',
          sent_count: 10,
          delivered_count: 8,
          read_count: 5,
          created_at: new Date().toISOString(),
        },
      ]),
    },
  },
}));

describe('DashboardPage', () => {
  it('shows loading state initially', () => {
    render(<DashboardPage />);
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('renders all three stat card labels after data loads', async () => {
    render(<DashboardPage />);
    await waitFor(() =>
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument(),
    );
    expect(screen.getByText('Total Contacts')).toBeInTheDocument();
    expect(screen.getByText('Active Conversations')).toBeInTheDocument();
    expect(screen.getByText('Campaigns This Month')).toBeInTheDocument();
  });

  it('displays correct total contacts count', async () => {
    render(<DashboardPage />);
    await waitFor(() =>
      expect(screen.getByTestId('stat-total-contacts')).toHaveTextContent('2'),
    );
  });

  it('displays only active conversations in the count', async () => {
    render(<DashboardPage />);
    await waitFor(() =>
      expect(screen.getByTestId('stat-active-conversations')).toHaveTextContent('1'),
    );
  });

  it('displays campaigns created this month', async () => {
    render(<DashboardPage />);
    await waitFor(() =>
      expect(screen.getByTestId('stat-campaigns-this-month')).toHaveTextContent('1'),
    );
  });
});
