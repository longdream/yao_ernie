import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'
import { t } from '../utils/i18n'

type ToastKind = 'info' | 'success' | 'warning' | 'error'

type ToastItem = {
  id: string
  kind: ToastKind
  message: string
}

type AlertOptions = {
  title?: string
  message: string
  okText?: string
}

type ConfirmOptions = {
  title?: string
  message: string
  okText?: string
  cancelText?: string
}

type PromptOptions = {
  title?: string
  message: string
  defaultValue?: string
  placeholder?: string
  okText?: string
  cancelText?: string
}

type ModalState =
  | { type: 'alert'; opts: AlertOptions; resolve: () => void }
  | { type: 'confirm'; opts: ConfirmOptions; resolve: (v: boolean) => void }
  | { type: 'prompt'; opts: PromptOptions; resolve: (v: string | null) => void }

export type UIOverlayApi = {
  toast: (kind: ToastKind, message: string) => void
  alert: (opts: AlertOptions) => Promise<void>
  confirm: (opts: ConfirmOptions) => Promise<boolean>
  prompt: (opts: PromptOptions) => Promise<string | null>
}

const UIOverlayContext = createContext<UIOverlayApi | null>(null)

export const useUIOverlay = (): UIOverlayApi => {
  const ctx = useContext(UIOverlayContext)
  if (!ctx) throw new Error('useUIOverlay must be used within UIOverlayProvider')
  return ctx
}

const toastStyle: Record<ToastKind, { bg: string; border: string; text: string }> = {
  info: { bg: 'bg-white', border: 'border-gray-200', text: 'text-gray-800' },
  success: { bg: 'bg-emerald-50', border: 'border-emerald-200', text: 'text-emerald-900' },
  warning: { bg: 'bg-amber-50', border: 'border-amber-200', text: 'text-amber-900' },
  error: { bg: 'bg-red-50', border: 'border-red-200', text: 'text-red-900' }
}

export const UIOverlayProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const [modal, setModal] = useState<ModalState | null>(null)
  const [promptValue, setPromptValue] = useState<string>('')
  const modalActiveRef = useRef(false)

  const toast = useCallback((kind: ToastKind, message: string) => {
    const id = `${Date.now()}_${Math.random().toString(36).slice(2)}`
    const item: ToastItem = { id, kind, message }
    setToasts(prev => [...prev, item])
    window.setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id))
    }, 2600)
  }, [])

  const alert = useCallback(async (opts: AlertOptions) => {
    if (modalActiveRef.current) return
    modalActiveRef.current = true
    return await new Promise<void>((resolve) => {
      setModal({
        type: 'alert',
        opts,
        resolve: () => {
          modalActiveRef.current = false
          setModal(null)
          resolve()
        }
      })
    })
  }, [])

  const confirm = useCallback(async (opts: ConfirmOptions) => {
    if (modalActiveRef.current) return false
    modalActiveRef.current = true
    return await new Promise<boolean>((resolve) => {
      setModal({
        type: 'confirm',
        opts,
        resolve: (v: boolean) => {
          modalActiveRef.current = false
          setModal(null)
          resolve(v)
        }
      })
    })
  }, [])

  const prompt = useCallback(async (opts: PromptOptions) => {
    if (modalActiveRef.current) return null
    modalActiveRef.current = true
    setPromptValue(opts.defaultValue ?? '')
    return await new Promise<string | null>((resolve) => {
      setModal({
        type: 'prompt',
        opts,
        resolve: (v: string | null) => {
          modalActiveRef.current = false
          setModal(null)
          resolve(v)
        }
      })
    })
  }, [])

  const api = useMemo<UIOverlayApi>(() => ({ toast, alert, confirm, prompt }), [toast, alert, confirm, prompt])

  return (
    <UIOverlayContext.Provider value={api}>
      {children}

      {/* Toasts */}
      <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[80] flex flex-col gap-2 w-[min(680px,calc(100vw-24px))] pointer-events-none">
        {toasts.map(item => {
          const s = toastStyle[item.kind]
          return (
            <div
              key={item.id}
              className={`pointer-events-auto ${s.bg} ${s.border} ${s.text} border shadow-lg rounded-lg px-4 py-3 text-sm`}
            >
              <div className="whitespace-pre-wrap break-words">{item.message}</div>
            </div>
          )
        })}
      </div>

      {/* Modal */}
      {modal && (
        <div className="fixed inset-0 bg-black/30 z-[90] flex items-center justify-center p-6">
          <div className="w-full max-w-[680px] bg-white rounded-lg border border-gray-200 shadow-xl overflow-hidden">
            <div className="p-6 space-y-4">
              {(modal.opts as any).title && (
                <div className="text-lg font-medium text-gray-800">{(modal.opts as any).title}</div>
              )}

              <div className="text-sm text-gray-700 whitespace-pre-wrap max-h-[50vh] overflow-auto">
                {modal.opts.message}
              </div>

              {modal.type === 'prompt' && (
                <textarea
                  autoFocus
                  value={promptValue}
                  onChange={(e) => setPromptValue(e.target.value)}
                  placeholder={modal.opts.placeholder}
                  className="w-full min-h-[96px] p-3 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              )}

              <div className="flex justify-end gap-3">
                {modal.type !== 'alert' && (
                  <button
                    className="btn h-10 px-4 bg-gray-100 text-gray-700 hover:bg-gray-200"
                    onClick={() => {
                      if (modal.type === 'confirm') modal.resolve(false)
                      if (modal.type === 'prompt') modal.resolve(null)
                    }}
                  >
                    {('cancelText' in modal.opts && modal.opts.cancelText) ? modal.opts.cancelText : t('common.cancel')}
                  </button>
                )}

                <button
                  className="btn h-10 px-4 bg-blue-600 text-white hover:bg-blue-700"
                  onClick={() => {
                    if (modal.type === 'alert') modal.resolve()
                    if (modal.type === 'confirm') modal.resolve(true)
                    if (modal.type === 'prompt') modal.resolve(promptValue)
                  }}
                >
                  {('okText' in modal.opts && modal.opts.okText) ? (modal.opts as any).okText : t('common.ok')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </UIOverlayContext.Provider>
  )
}


