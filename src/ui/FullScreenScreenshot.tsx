import React, { useState, useEffect } from 'react'
import { listen } from '@tauri-apps/api/event'
import { invoke } from '@tauri-apps/api/core'

export const FullScreenScreenshot: React.FC = () => {
  const [screenshotData, setScreenshotData] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    console.log('🖼️ FullScreenScreenshot component mounted in screenshot window')
    console.log('🔍 Current window location:', window.location.href)
    
    // 添加一个定时器来检查组件状态
    const statusTimer = setInterval(() => {
      console.log('📊 Component status - isLoading:', isLoading, 'hasData:', !!screenshotData)
    }, 2000)
    
    // 移除事件监听器 - 现在使用内嵌HTML处理截图
    console.log('⚠️ FullScreenScreenshot component should not be used anymore')

    return () => {
      clearInterval(statusTimer)
    }
  }, [])

  const handleClose = async () => {
    console.log('🔒 Closing screenshot window')
    try {
      await invoke('close_screenshot_window')
    } catch (error) {
      console.error('Failed to close screenshot window:', error)
    }
  }

  if (isLoading) {
    return (
      <div className="w-full h-screen bg-gray-800 flex items-center justify-center">
        <div className="text-white text-xl">
          🖼️ 准备截图中...
        </div>
      </div>
    )
  }

  if (!screenshotData) {
    return (
      <div className="w-full h-screen bg-red-800 flex items-center justify-center">
        <div className="text-white text-xl">
          ❌ 截图数据加载失败
        </div>
      </div>
    )
  }

  return (
    <div className="w-full h-screen bg-black relative">
      <div className="absolute top-4 left-4 text-white bg-black bg-opacity-50 p-2 rounded">
        📸 截图测试窗口 - 数据已加载
      </div>
      
      <img
        src={`data:image/png;base64,${screenshotData}`}
        className="w-full h-full object-contain"
        alt="Screenshot"
      />
      
      <div className="absolute bottom-4 right-4">
        <button
          onClick={handleClose}
          className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
        >
          关闭测试
        </button>
      </div>
    </div>
  )
}