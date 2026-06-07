import '@testing-library/jest-dom';
import { render, screen, fireEvent } from '@testing-library/react';
import { ContactsTable } from '@/components/ContactsTable';
import type { Contact } from '@/lib/api';

const contacts: Contact[] = [
  {
    id: '1',
    name: 'Priya Sharma',
    phone: '+919876543210',
    opted_in: true,
    tags: ['purchased'],
    created_at: '2024-01-01T00:00:00Z',
  },
  {
    id: '2',
    name: 'Rahul Verma',
    phone: '+919876543211',
    opted_in: false,
    tags: [],
    created_at: '2024-01-02T00:00:00Z',
  },
];

describe('ContactsTable', () => {
  it('renders all contact rows', () => {
    render(<ContactsTable contacts={contacts} />);
    expect(screen.getByText('Priya Sharma')).toBeInTheDocument();
    expect(screen.getByText('Rahul Verma')).toBeInTheDocument();
    expect(screen.getByText('+919876543210')).toBeInTheDocument();
  });

  it('filters by name when search input changes', () => {
    render(<ContactsTable contacts={contacts} />);
    fireEvent.change(screen.getByPlaceholderText(/search contacts/i), {
      target: { value: 'Priya' },
    });
    expect(screen.getByText('Priya Sharma')).toBeInTheDocument();
    expect(screen.queryByText('Rahul Verma')).not.toBeInTheDocument();
  });

  it('filters by phone number', () => {
    render(<ContactsTable contacts={contacts} />);
    fireEvent.change(screen.getByPlaceholderText(/search contacts/i), {
      target: { value: '543211' },
    });
    expect(screen.queryByText('Priya Sharma')).not.toBeInTheDocument();
    expect(screen.getByText('Rahul Verma')).toBeInTheDocument();
  });

  it('shows no-results message when search has no matches', () => {
    render(<ContactsTable contacts={contacts} />);
    fireEvent.change(screen.getByPlaceholderText(/search contacts/i), {
      target: { value: 'zzznomatch' },
    });
    expect(screen.getByText(/no contacts found/i)).toBeInTheDocument();
  });

  it('displays opted-in status correctly', () => {
    render(<ContactsTable contacts={contacts} />);
    const rows = screen.getAllByRole('row');
    expect(rows[1]).toHaveTextContent('Yes');
    expect(rows[2]).toHaveTextContent('No');
  });

  it('renders empty table when contacts array is empty', () => {
    render(<ContactsTable contacts={[]} />);
    expect(screen.getByText(/no contacts found/i)).toBeInTheDocument();
  });
});
