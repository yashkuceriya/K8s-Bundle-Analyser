import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import HealthScore from '../HealthScore';

describe('HealthScore', () => {
  it('shows Healthy label for score > 70', () => {
    render(<HealthScore score={85} />);
    expect(screen.getByText('85%')).toBeInTheDocument();
    expect(screen.getByText('Healthy')).toBeInTheDocument();
  });

  it('shows Degraded label for score 41-70', () => {
    render(<HealthScore score={55} />);
    expect(screen.getByText('55%')).toBeInTheDocument();
    expect(screen.getByText('Degraded')).toBeInTheDocument();
  });

  it('shows Critical label for score <= 40', () => {
    render(<HealthScore score={20} />);
    expect(screen.getByText('20%')).toBeInTheDocument();
    expect(screen.getByText('Critical')).toBeInTheDocument();
  });

  it('renders trend sparkline when provided', () => {
    const { container } = render(<HealthScore score={75} trend={[60, 65, 70, 75]} />);
    // Should render SVG path for sparkline
    const paths = container.querySelectorAll('path');
    expect(paths.length).toBeGreaterThan(0);
    expect(screen.getByText('4 runs')).toBeInTheDocument();
  });

  it('does not render sparkline without trend data', () => {
    render(<HealthScore score={75} />);
    expect(screen.queryByText('runs')).not.toBeInTheDocument();
  });
});
