import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { ApiError } from '../api/client'

interface ToastValue {
  showError: (error: unknown) => void
  showMessage: (text: string) => void
}

const ToastContext = createContext<ToastValue | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<{ id: number; text: string; kind: string }[]>([])

  const push = useCallback((text: string, kind: string) => {
    const id = Date.now() + Math.random()
    setMessages((current) => [...current, { id, text, kind }])
    setTimeout(() => setMessages((current) => current.filter((m) => m.id !== id)), 6000)
  }, [])

  const value = useMemo<ToastValue>(
    () => ({
      showError: (error) =>
        push(error instanceof ApiError ? error.message : 'Something went wrong', 'error'),
      showMessage: (text) => push(text, 'info'),
    }),
    [push],
  )

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {messages.map((m) => (
          <div key={m.id} className={`toast toast--${m.kind}`}>
            {m.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastValue {
  const value = useContext(ToastContext)
  if (!value) throw new Error('useToast must be used inside a ToastProvider')
  return value
}
