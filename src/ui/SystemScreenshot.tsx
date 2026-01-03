import React, { useState, useRef, useEffect, useCallback } from 'react'
import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import { t } from '../utils/i18n'

interface SystemScreenshotProps {
  onCapture: (imageData: string) => void
  onCancel: () => void
}

interface SelectionRect {
  startX: number
  startY: number
  endX: number
  endY: number
}

interface ScreenshotData {
  success: boolean
  imageData?: string
  width?: number
  height?: number
  error?: string
}

// 日志函数
const logInfo = (message: string) => {
  const timestamp = new Date().toISOString()
  const fullMessage = `[${timestamp}] SystemScreenshot: ${message}`
  console.log(fullMessage)
}

// 错误日志函数
const logError = (message: string, error?: any) => {
  const timestamp = new Date().toISOString()
  const errorDetails = error ? (typeof error === 'object' ? JSON.stringify(error) : String(error)) : ''
  const fullMessage = `[${timestamp}] SystemScreenshot: ${message}${errorDetails ? ` - ${errorDetails}` : ''}`
  
  // 只输出到控制台，不弹alert
  console.error(fullMessage, error)
}

// 安全的国际化函数
const safeT = (key: string, fallback: string = key) => {
  try {
    return t(key)
  } catch (error) {
    logError(`Translation error for key: ${key}`, error)
    return fallback
  }
}

export const SystemScreenshot: React.FC<SystemScreenshotProps> = ({ onCapture, onCancel }) => {
  const [isSelecting, setIsSelecting] = useState(false)
  const [selection, setSelection] = useState<SelectionRect | null>(null)
  const [screenshotData, setScreenshotData] = useState<string | null>(null)
  const [screenSize, setScreenSize] = useState<{ width: number; height: number } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const overlayRef = useRef<HTMLDivElement>(null)
  const imageRef = useRef<HTMLImageElement>(null)

  // 全局错误处理
  useEffect(() => {
    // 记录组件挂载
    logInfo('SystemScreenshot component mounted')
    
    const handleError = (event: ErrorEvent) => {
      const errorMsg = `JavaScript Error: ${event.message} at ${event.filename}:${event.lineno}`
      logError(errorMsg, event.error)
      setError(errorMsg)
    }

    const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
      const errorMsg = `Unhandled Promise Rejection: ${event.reason}`
      logError(errorMsg, event.reason)
      setError(errorMsg)
    }

    window.addEventListener('error', handleError)
    window.addEventListener('unhandledrejection', handleUnhandledRejection)

    return () => {
      window.removeEventListener('error', handleError)
      window.removeEventListener('unhandledrejection', handleUnhandledRejection)
      logInfo('SystemScreenshot component unmounted')
    }
  }, [])

  // 启动截图
  useEffect(() => {
    const startScreenshot = async () => {
      try {
        logInfo('Starting screenshot...')
        await invoke('start_screenshot')
        logInfo('Screenshot invoke successful')
      } catch (error) {
        logError('Failed to start screenshot', error)
        setError(`启动截图失败: ${error}`)
        onCancel()
      }
    }

    startScreenshot()

    // 截图现在通过URL导航直接处理，不需要事件监听器
  }, [onCancel])

  // 键盘事件处理
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      try {
        if (e.key === 'Escape') {
          logInfo('ESC key pressed, cancelling screenshot')
          onCancel()
        }
      } catch (error) {
        logError('Error in keyboard event handler', error)
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onCancel, selection])

  // 鼠标事件处理
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    try {
      logInfo(`Mouse down at: ${e.clientX}, ${e.clientY}`)
      if (e.target === overlayRef.current || e.target === imageRef.current) {
        setIsSelecting(true)
        
        const rect = overlayRef.current?.getBoundingClientRect()
        if (rect) {
          const startX = e.clientX - rect.left
          const startY = e.clientY - rect.top
          setSelection({
            startX,
            startY,
            endX: startX,
            endY: startY,
          })
          logInfo(`Selection started at: ${startX}, ${startY}`)
        }
      }
    } catch (error) {
      logError('Error in handleMouseDown', error)
    }
  }, [])

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    try {
      if (isSelecting && selection && overlayRef.current) {
        const rect = overlayRef.current.getBoundingClientRect()
        const endX = e.clientX - rect.left
        const endY = e.clientY - rect.top
        setSelection({
          ...selection,
          endX,
          endY,
        })
        // 移除过于频繁的鼠标移动日志
      }
    } catch (error) {
      logError('Error in handleMouseMove', error)
    }
  }, [isSelecting, selection])

  const handleMouseUp = useCallback(() => {
    try {
      logInfo(`Mouse up: isSelecting=${isSelecting}, selection exists=${!!selection}`)
      if (isSelecting && selection) {
        setIsSelecting(false)
        
        const width = Math.abs(selection.endX - selection.startX)
        const height = Math.abs(selection.endY - selection.startY)
        
        logInfo(`Selection size: ${width}x${height}`)
        
        if (width <= 10 || height <= 10) {
          setSelection(null)
          logInfo('Selection too small, clearing')
        }
      }
    } catch (error) {
      logError('Error in handleMouseUp', error)
    }
  }, [isSelecting, selection])


  // 获取选择区域样式
  const getSelectionStyle = () => {
    if (!selection) return {}
    
    const x = Math.min(selection.startX, selection.endX)
    const y = Math.min(selection.startY, selection.endY)
    const width = Math.abs(selection.endX - selection.startX)
    const height = Math.abs(selection.endY - selection.startY)

    return {
      left: x,
      top: y,
      width,
      height,
    }
  }


  if (!screenshotData) {
    return (
      <div className="fixed inset-0 z-50 bg-black bg-opacity-50 flex items-center justify-center">
        <div className="text-white text-lg">正在截图...</div>
        <div className="absolute bottom-4 left-4 text-white text-sm">
          Debug: Component rendered, waiting for screenshot data
        </div>
      </div>
    )
  }

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 cursor-crosshair select-none"
      style={{ backgroundColor: 'rgba(0, 0, 0, 0.3)' }}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
    >
      {/* 背景截图 */}
      <img
        ref={imageRef}
        src={`data:image/png;base64,${screenshotData}`}
        alt="Screenshot"
        className="absolute inset-0 w-full h-full object-cover pointer-events-none"
        style={{ filter: 'brightness(0.7)' }}
        draggable={false}
      />

      {/* 选择区域 */}
      {selection && (
        <>
          {/* 高亮选择区域 */}
          <div
            className="absolute border-2 border-blue-400 bg-transparent"
            style={{
              ...getSelectionStyle(),
              boxShadow: '0 0 0 9999px rgba(0, 0, 0, 0.3)',
            }}
          >
            {/* 选择区域内的原始图片 */}
            <div 
              className="absolute inset-0 overflow-hidden"
              style={{
                backgroundImage: `url(data:image/png;base64,${screenshotData})`,
                backgroundSize: `${screenSize?.width}px ${screenSize?.height}px`,
                backgroundPosition: `-${Math.min(selection.startX, selection.endX)}px -${Math.min(selection.startY, selection.endY)}px`,
                backgroundRepeat: 'no-repeat',
              }}
            />
          </div>

          {/* 尺寸信息 */}
          <div
            className="absolute bg-blue-500 text-white text-xs px-2 py-1 rounded pointer-events-none"
            style={{
              left: Math.min(selection.startX, selection.endX),
              top: Math.min(selection.startY, selection.endY) - 25,
            }}
          >
            {Math.abs(selection.endX - selection.startX)} × {Math.abs(selection.endY - selection.startY)}
          </div>
        </>
      )}


      {/* 错误显示 */}
      {error && (
        <div className="absolute top-4 left-1/2 transform -translate-x-1/2 bg-red-600 text-white px-4 py-2 rounded-lg max-w-md">
          <div className="font-bold mb-2">截图错误</div>
          <div className="text-sm mb-2">{error}</div>
          <button 
            onClick={onCancel}
            className="bg-white text-red-600 px-3 py-1 rounded text-sm hover:bg-gray-100"
          >
            关闭
          </button>
        </div>
      )}

      {/* 提示文字 */}
      {!selection && !error && (
        <div className="absolute top-4 left-1/2 transform -translate-x-1/2 text-white text-lg bg-black bg-opacity-70 px-4 py-2 rounded-lg pointer-events-none">
          {safeT('screenshot.instruction', '拖拽选择截图区域，ESC键取消')}
        </div>
      )}
    </div>
  )
}
