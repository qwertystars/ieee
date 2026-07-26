import { Link } from 'react-router-dom'

export default function NotFoundPage() {
  return (
    <div
      className="flex min-h-screen flex-col items-center justify-center gap-4 bg-gray-950 p-8 text-center"
      role="alert"
      aria-live="polite"
    >
      <h1 className="text-2xl font-bold text-gray-100">404</h1>
      <p className="text-sm text-gray-500">The page you are looking for does not exist.</p>
      <Link
        to="/dashboard"
        className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
        aria-label="Go to dashboard"
      >
        Go to Dashboard
      </Link>
    </div>
  )
}
