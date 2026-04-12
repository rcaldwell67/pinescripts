
import React from 'react';
import { render, screen } from '@testing-library/react';
import App from './App';

describe('App', () => {
  it('renders dashboard heading and message', () => {
    render(<App />);
    expect(screen.getByText('Dashboard App')).toBeInTheDocument();
    expect(screen.getByText(/restored to a minimal, valid state/i)).toBeInTheDocument();
  });
});
