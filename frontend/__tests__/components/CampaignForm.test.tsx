import '@testing-library/jest-dom';
import { render, screen, fireEvent } from '@testing-library/react';
import { CampaignForm } from '@/components/CampaignForm';

const TEMPLATES = ['review_request', 'welcome_back'];

describe('CampaignForm', () => {
  it('shows validation error when name is empty and form is submitted', () => {
    render(<CampaignForm templates={TEMPLATES} onSubmit={jest.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /create campaign/i }));
    expect(screen.getByRole('alert')).toHaveTextContent(/name is required/i);
  });

  it('does not call onSubmit when name is empty', () => {
    const onSubmit = jest.fn();
    render(<CampaignForm templates={TEMPLATES} onSubmit={onSubmit} />);
    fireEvent.click(screen.getByRole('button', { name: /create campaign/i }));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('calls onSubmit with correct data on valid submission', () => {
    const onSubmit = jest.fn();
    render(<CampaignForm templates={TEMPLATES} onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText(/campaign name/i), {
      target: { value: 'Summer Sale' },
    });
    fireEvent.change(screen.getByLabelText(/audience tags/i), {
      target: { value: 'purchased, vip' },
    });
    fireEvent.click(screen.getByRole('button', { name: /create campaign/i }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'Summer Sale',
        audience_tags: ['purchased', 'vip'],
      }),
    );
  });

  it('renders all template options in the dropdown', () => {
    render(<CampaignForm templates={TEMPLATES} onSubmit={jest.fn()} />);
    expect(screen.getByRole('option', { name: 'review_request' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'welcome_back' })).toBeInTheDocument();
  });

  it('shows loading state and disables button when loading prop is true', () => {
    render(<CampaignForm templates={TEMPLATES} onSubmit={jest.fn()} loading={true} />);
    const btn = screen.getByRole('button', { name: /creating/i });
    expect(btn).toBeDisabled();
  });

  it('clears validation error after valid name is entered and re-submitted', () => {
    const onSubmit = jest.fn();
    render(<CampaignForm templates={TEMPLATES} onSubmit={onSubmit} />);

    // Trigger error
    fireEvent.click(screen.getByRole('button', { name: /create campaign/i }));
    expect(screen.getByRole('alert')).toBeInTheDocument();

    // Enter valid name and submit
    fireEvent.change(screen.getByLabelText(/campaign name/i), {
      target: { value: 'Diwali Special' },
    });
    fireEvent.click(screen.getByRole('button', { name: /create campaign/i }));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(onSubmit).toHaveBeenCalled();
  });
});
