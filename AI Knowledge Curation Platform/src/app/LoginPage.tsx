import { useState } from 'react'

type Props = {
  onSignIn: (email: string, password: string) => Promise<{ error: Error | null }>
  onSignUp: (email: string, password: string) => Promise<{ error: Error | null }>
}

export function LoginPage({ onSignIn, onSignUp }: Props) {
  const [mode, setMode] = useState<'signin' | 'signup'>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [signedUp, setSignedUp] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      if (mode === 'signin') {
        const { error } = await onSignIn(email, password)
        if (error) setError(error.message)
      } else {
        const { error } = await onSignUp(email, password)
        if (error) setError(error.message)
        else setSignedUp(true)
      }
    } finally {
      setLoading(false)
    }
  }

  function switchMode(next: 'signin' | 'signup') {
    setMode(next)
    setError(null)
    setSignedUp(false)
  }

  return (
    <div className="flex items-center justify-center h-screen bg-slate-100" style={{ fontFamily: "'Inter', system-ui, sans-serif" }}>
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm w-full max-w-sm p-8">
        {/* Logo */}
        <div className="flex items-center gap-2.5 mb-8">
          <div className="size-8 rounded-xl bg-blue-500 flex items-center justify-center shrink-0 shadow-sm">
            <svg className="size-4 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
            </svg>
          </div>
          <div>
            <p className="text-sm font-bold text-slate-900 leading-tight">Synker</p>
            <p className="text-xs text-slate-500 leading-tight">Knowledge Platform</p>
          </div>
        </div>

        <h1 className="text-lg font-semibold text-slate-900 mb-1">
          {mode === 'signin' ? 'Sign in to your account' : 'Create an account'}
        </h1>
        <p className="text-sm text-slate-500 mb-6">
          {mode === 'signin' ? 'Welcome back.' : 'Get started with Synker.'}
        </p>

        {signedUp ? (
          <div className="rounded-xl bg-emerald-50 border border-emerald-200 px-4 py-4 text-sm text-emerald-800">
            Check your email to confirm your account, then{' '}
            <button onClick={() => switchMode('signin')} className="font-medium underline underline-offset-2">
              sign in
            </button>
            .
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1.5">Email</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 transition-all"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1.5">Password</label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 transition-all"
              />
            </div>

            {error && (
              <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-blue-600 text-white text-sm font-medium rounded-xl px-4 py-2.5 hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
            >
              {loading
                ? mode === 'signin' ? 'Signing in…' : 'Creating account…'
                : mode === 'signin' ? 'Sign in' : 'Create account'}
            </button>
          </form>
        )}

        {!signedUp && (
          <p className="text-xs text-slate-500 text-center mt-6">
            {mode === 'signin' ? (
              <>Don't have an account?{' '}
                <button onClick={() => switchMode('signup')} className="text-blue-600 font-medium hover:underline">
                  Sign up
                </button>
              </>
            ) : (
              <>Already have an account?{' '}
                <button onClick={() => switchMode('signin')} className="text-blue-600 font-medium hover:underline">
                  Sign in
                </button>
              </>
            )}
          </p>
        )}
      </div>
    </div>
  )
}
