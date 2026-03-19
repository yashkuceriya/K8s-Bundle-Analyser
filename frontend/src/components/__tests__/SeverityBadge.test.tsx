import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import SeverityBadge from '../SeverityBadge';

describe('SeverityBadge', () => {
  it('renders critical badge', () => {
    render(<SeverityBadge severity="critical" />);
    expect(screen.getByText(/critical/i)).toBeInTheDocument();
  });

  it('renders warning badge', () => {
    render(<SeverityBadge severity="warning" />);
    expect(screen.getByText(/warning/i)).toBeInTheDocument();
  });

  it('renders info badge', () => {
    render(<SeverityBadge severity="info" />);
    expect(screen.getByText(/info/i)).toBeInTheDocument();
  });

  it('renders unknown severity gracefully', () => {
    render(<SeverityBadge severity="unknown" />);
    expect(screen.getByText(/unknown/i)).toBeInTheDocument();
  });
});
