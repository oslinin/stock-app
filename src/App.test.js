import { render, screen } from '@testing-library/react';
import App from './App';

test('renders app title', () => {
  render(<App />);
  const titleElement = screen.getByText(/My Stock App/i);
  expect(titleElement).toBeInTheDocument();
});

test('renders sidebar with Stock app entry', () => {
  render(<App />);
  const sidebarElement = screen.getByText('Stock app');
  expect(sidebarElement).toBeInTheDocument();
  expect(sidebarElement.closest('nav')).toHaveClass('sidebar');
});
