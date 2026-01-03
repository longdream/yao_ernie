import React, { useEffect, useMemo, useRef, useState } from 'react'
import { SettingsDrawer } from './SettingsDrawer'
import { ChatBubble } from './ChatBubble'
import { useStore } from '../utils/store'
import { fetchModels, streamChat, streamChatWithMCP } from '../utils/proxy'
import { t, tf, setLocale, getCurrentLocale } from '../utils/i18n'
import { IconSend, IconStop, IconGlobe, IconCloud, IconList, IconEdit, IconBrain, IconLanguage, IconMCP } from './icons'
import { Dropdown } from './Dropdown'
import { createConversationId, loadConversations, saveConversations, type Conversation } from '../utils/conversations'
import { log } from '../utils/log'
import { ModelPullDialog } from './ModelPullDialog'
import { ImageUpload } from './ImageUpload'
// Loading现在在HTML中处理，不需要React组件
import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import type { ImageAttachment, ModelCategory, getModelCategoryName } from '../utils/types'
import type { GlobalMessage } from '../utils/store'
import { setupWindowCloseHandler } from '../utils/window'
import { useUIOverlay } from './UIOverlay'

export type Message = {
  role: 'user' | 'assistant'
  content: string
  images?: ImageAttachment[]
}

// Context target from Ctrl+LeftClick
interface ContextTarget {
  app_name: string
  window_title: string
  cursor_x: number
  cursor_y: number
  timestamp: number
}

// Step progress for taskflow visualization
interface StepProgress {
  step_id?: number
  tool?: string
  description?: string
  status: 'pending' | 'running' | 'done' | 'error'
  error?: string
}

interface TaskflowProgress {
  steps: StepProgress[]
  currentStep?: string
  isComplete: boolean
}

let renderCount = 0

export const App: React.FC = () => {
  renderCount++
  console.log(`🔄 App component render #${renderCount}`)
  
  const [showSettings, setShowSettings] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [currentCid, setCurrentCid] = useState<string>('')
  const [input, setInput] = useState('')
  const [models, setModels] = useState<string[]>([])
  const [isSidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [typingIndex, setTypingIndex] = useState<number | null>(null)
  const [view, setView] = useState<'starter' | 'main'>('starter')
  const [isDrawerOpen, setDrawerOpen] = useState(false)
  const [thinkStartAt, setThinkStartAt] = useState<number | null>(null)
  const [thinkingMs, setThinkingMs] = useState<number>(0)
  const [assistantOutputStarted, setAssistantOutputStarted] = useState<boolean>(false)
  const [thinkEnabled, setThinkEnabled] = useState<boolean>(true)
  const [mcpEnabled, setMcpEnabled] = useState<boolean>(false)
  const [pullingModel, setPullingModel] = useState<string>('')
  const [currentLanguage, setCurrentLanguage] = useState(getCurrentLocale())
  const [isGenerating, setIsGenerating] = useState<boolean>(false)
  const [selectedImages, setSelectedImages] = useState<ImageAttachment[]>([])
  const [currentModelCategory, setCurrentModelCategory] = useState<ModelCategory>('light')
  const [isScreenshotting, setIsScreenshotting] = useState<boolean>(false)
  const [isScreenshotLoading, setIsScreenshotLoading] = useState<boolean>(false)
  
  // Context-aware mode state (merged from floating window)
  const [contextTarget, setContextTarget] = useState<ContextTarget | null>(null)
  const [agentEnabled, setAgentEnabled] = useState<boolean>(false)
  const [outputMode, setOutputMode] = useState<'R' | 'W'>('R') // R=show in UI, W=write to target app
  const [isExpanded, setIsExpanded] = useState(false)
  const [loopEnabled, setLoopEnabled] = useState(false)
  const [isAgentRunning, setIsAgentRunning] = useState(false)
  const [taskflowProgress, setTaskflowProgress] = useState<TaskflowProgress>({ steps: [], isComplete: true })
  const autoLoopTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const autoLoopStopFlag = useRef(false)
  const loopPromptRef = useRef<string>('')
  const eventSourceRef = useRef<EventSource | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  
  const abortControllerRef = useRef<AbortController | null>(null)

  const ui = useUIOverlay()
  const { config, messages: globalMessages, addMessage } = useStore()
  const listRef = useRef<HTMLDivElement | null>(null)

  // 应用数据初始化
  useEffect(() => {
    const initAppData = async () => {
      try {
        const list = await fetchModels(config)
        setModels(list)
        const cs = await loadConversations()
        setConversations(cs)
        if (cs.length) {
          setCurrentCid(cs[0].id)
          setMessages(cs[0].messages.map(m=>({ role:m.role, content:m.content })))
        }
        
        // 注册全局快捷键
        try {
          await invoke('register_global_shortcut')
          await log('INFO', 'global_shortcut_registered', { shortcut: 'Ctrl+Y' })
        } catch (error) {
          await log('ERROR', 'global_shortcut_register_failed', { error: String(error) })
        }
        
        // 设置窗口关闭处理程序（最小化到托盘）
        setupWindowCloseHandler()
        
      } catch (error) {
        setModels([])
      }
    }
    
    initAppData()

    // 监听全局快捷键事件
    const unlistenShortcut = listen('shortcut', (event: any) => {
      console.log('📸 Global shortcut triggered:', event.payload)
      if (event.payload === 'Ctrl+Alt+A') {
        startScreenshot()
      }
    })
    
    return () => {
      unlistenShortcut.then(fn => fn())
    }
  }, []) // 只在挂载时执行一次

  // 监听截图完成事件（用于主页面）
  useEffect(() => {
    console.log('🔧 Setting up screenshot listener in main window')
    
    const unlistenScreenshot = listen('screenshot-captured', (event: any) => {
      console.log('📸 Screenshot event received in main window:', event.payload)
      const data = event.payload
      if (data.success && data.imageData) {
        // 只有主窗口处理截图，悬浮窗口不处理
        // 通过检查窗口类型来判断 - 主窗口的URL路径是 '/' 或 '/index.html'
        const isMainWindow = window.location.pathname === '/' || window.location.pathname === '/index.html' || window.location.pathname === ''
        
        if (isMainWindow) {
          console.log('✅ Processing screenshot in main window')
          
          // 处理截图数据，确保格式正确
          let url: string
          let base64Data: string
          
          if (data.imageData.startsWith('data:image/')) {
            url = data.imageData
            const commaIndex = data.imageData.indexOf(',')
            base64Data = data.imageData.substring(commaIndex + 1)
          } else {
            url = `data:image/png;base64,${data.imageData}`
            base64Data = data.imageData
          }
          
          // 创建图片附件
          const imageAttachment: ImageAttachment = {
            id: `screenshot_${Date.now()}`,
            name: `screenshot_${Date.now()}.png`,
            url: url,
            base64: base64Data,
            mimeType: 'image/png',
            size: base64Data.length
          }
          
          // 添加到选中的图片列表
          setSelectedImages(prev => [...prev, imageAttachment])
          console.log('✅ Screenshot added to main window images')
        } else {
          console.log('⚠️ Ignoring screenshot - not main window')
        }
      }
    })

    // 监听截图页面准备就绪事件
    const unlistenReady = listen('screenshot-ready', () => {
      console.log('🎯 Screenshot page ready, hiding loading in main window')
      setIsScreenshotLoading(false)
    })

    return () => {
      console.log('🧹 Cleaning up screenshot listener in main window')
      unlistenScreenshot.then(fn => fn()).catch(error => {
        console.error('❌ Error cleaning up screenshot listener:', error)
      })
      unlistenReady.then(fn => fn()).catch(error => {
        console.error('❌ Error cleaning up ready listener:', error)
      })
    }
  }, [])
  
  // 监听 context-invoked 事件 (Ctrl+LeftClick from Rust)
  useEffect(() => {
    console.log('🔧 Setting up context-invoked listener')
    
    const unlistenContext = listen('context-invoked', (event: any) => {
      console.log('🎯 Context invoked event received:', event.payload)
      const data = event.payload as ContextTarget
      
      // Set the context target
      setContextTarget(data)
      // Defaults for Ctrl+LeftClick invoke:
      // Agent=On, Loop=Off, Output=W (write to app)
      setAgentEnabled(true)
      setLoopEnabled(false)
      setOutputMode('W')
      
      // Switch to main view and focus input
      setView('main')
      
      // Auto-expand the mode buttons
      setIsExpanded(true)
      
      // Focus the input after a short delay
      setTimeout(() => {
        if (inputRef.current) {
          inputRef.current.focus()
        }
      }, 100)
    })
    
    return () => {
      unlistenContext.then(fn => fn())
    }
  }, [])

  
  // 当config变化时重新获取models
  useEffect(() => {
    const updateModels = async () => {
      try {
        const list = await fetchModels(config)
        setModels(list)
      } catch (error) {
        setModels([])
      }
    }
    updateModels()
  }, [config.provider, config.baseUrl, config.apiKey])

  useEffect(() => {
    // Ensure think state matches config, but only update if config is actually loaded
    if (config.defaultThink !== undefined) {
      setThinkEnabled(!!config.defaultThink)
    }
  }, [config.defaultThink])

  // 初始化语言设置
  useEffect(() => {
    if (config.language) {
      setLocale(config.language)
      setCurrentLanguage(config.language)
    }
  }, [config.language])

  // 语言切换函数
  const toggleLanguage = async () => {
    const currentLang = getCurrentLocale()
    const newLang = currentLang === 'zh-CN' ? 'en' : 'zh-CN'
    setLocale(newLang)
    setCurrentLanguage(newLang)
    
    // 保存语言设置到配置中
    const { setConfig, persist } = useStore.getState()
    try {
      // 先更新store中的配置
      setConfig({ language: newLang })
      // 然后持久化到文件
      await persist()
      console.log('Language saved:', newLang)
    } catch (error) {
      console.error('Failed to save language:', error)
    }
  }

  useEffect(() => {
    if (!listRef.current) return
    listRef.current.scrollTop = listRef.current.scrollHeight
  }, [messages])

  const currentModel = useMemo(() => {
    // if configured models exist, restrict dropdown to them; otherwise fallback to fetched list
    if (config.models && config.models.length) {
      const names = config.models.map(m => m.name)
      const prefer = config.model && names.includes(config.model) ? config.model : (names[0] || '')
      return prefer
    }
    return config.model || models[0] || ''
  }, [config.model, config.models, models])
  const modelOptions = useMemo(() => {
    if (config.models && config.models.length) {
      return config.models.map(m => ({ label: m.name, value: m.name }))
    }
    return (models.length ? models : ['qwen3:0.6b']).map(m => ({ label: m, value: m }))
  }, [config.models, models])

  const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    setIsGenerating(false)
    setTypingIndex(null)
    setThinkStartAt(null)
    log('INFO', 'chat_generation_stopped_by_user', {})
  }

  const handleSend = async () => {
    if (!input.trim()) return
    if (isGenerating) {
      handleStop()
      return
    }
    if (view === 'starter') setView('main')
    
    // 智能模型选择：有图片时使用VL模型，否则使用高级模型
    let selectedModel: string | null = null
    if (selectedImages.length > 0) {
      // 有图片，使用VL模型
      const vlModel = config.vlModel || config.models?.find(m => m.supportsVision)?.name
      if (vlModel) {
        selectedModel = vlModel
        // 更新当前模型配置
        useStore.getState().setConfig({ model: vlModel })
        console.log('🔄 Auto-switched to VL model for image input:', vlModel)
      } else {
        // 没有配置VL模型
        await log('ERROR', 'no_vl_model_configured', { hasImages: true })
        ui.toast('error', t('errors.vl_model_required'))
        return
      }
    } else {
      // 纯文本，使用高级模型
      const advancedModel = config.advancedModel || config.models?.find(m => m.category === 'advanced')?.name
      if (advancedModel) {
        selectedModel = advancedModel
        // 更新当前模型配置
        useStore.getState().setConfig({ model: advancedModel })
        console.log('🔄 Auto-switched to advanced model for text input:', advancedModel)
      } else {
        // 没有配置高级模型，尝试使用当前模型
        selectedModel = currentModel
        if (!selectedModel) {
          await log('ERROR', 'no_model_configured', { hasImages: false })
          ui.toast('error', t('errors.no_model_configured'))
          return
        }
      }
    }
    
    const userMessage: Message = { role: 'user', content: input.trim(), images: selectedImages }
    const newMessages = [...messages, userMessage]
    setMessages(newMessages)
    // 主页面不需要调用全局addMessage，避免重复消息
    setInput('')
    setSelectedImages([]) // 清除选中的图片
    const cid = currentCid || createConversationId()
    if (!currentCid) setCurrentCid(cid)
    // 根据上下文限制截断
    const contextLimit = config.maxContextMessages ?? 20
    const history = newMessages.slice(Math.max(0, newMessages.length - contextLimit))
    await log('INFO', 'chat_send_start', { model: selectedModel, think: thinkEnabled, input: input.trim() })
    // 找到当前模型的配置，使用其特定的baseUrl和provider
    const modelConfig = config.models?.find(m => m.name === selectedModel)
    const modelBaseUrl = modelConfig?.baseUrl || config.baseUrl
    const modelProvider = modelConfig?.provider || config.provider
    
    await log('INFO', 'model_config_resolved', { 
      model: selectedModel, 
      provider: modelProvider, 
      baseUrl: modelBaseUrl,
      configProvider: config.provider 
    })
    
    // streaming assistant
    const assistant: Message = { role: 'assistant', content: '' }
    setMessages(prev => [...prev, assistant])
    const assistantIndex = newMessages.length
    setTypingIndex(assistantIndex)
    setThinkStartAt(Date.now())
    setAssistantOutputStarted(false)
    setIsGenerating(true)
    
    // 创建AbortController
    abortControllerRef.current = new AbortController()
    
    try {
      // 使用模型特定的配置
      const modelSpecificConfig = { 
        ...config, 
        baseUrl: modelBaseUrl, 
        provider: modelProvider,
        apiKey: modelConfig?.apiKey || config.apiKey
      }
      
      // 严格检查API Key - 没有API Key直接报错
      if (!modelSpecificConfig.apiKey || modelSpecificConfig.apiKey.trim() === '') {
        await log('ERROR', 'no_api_key_configured', { 
          model: selectedModel, 
          provider: modelProvider,
          hasGlobalApiKey: !!config.apiKey,
          hasModelApiKey: !!modelConfig?.apiKey
        })
        ui.toast('error', tf('errors.model_api_key_missing', { model: selectedModel || '' }))
        setIsGenerating(false)
        setTypingIndex(null)
        // 移除刚添加的空助手消息
        setMessages(prev => prev.slice(0, -1))
        return
      }
      
      await log('INFO', 'chat_stream_start', { 
        model: selectedModel, 
        provider: modelProvider, 
        baseUrl: modelBaseUrl,
        think: thinkEnabled,
        hasApiKey: !!(modelSpecificConfig.apiKey && modelSpecificConfig.apiKey.length > 0),
        apiKeyLength: modelSpecificConfig.apiKey?.length || 0
      })
      
      for await (const chunk of streamChatWithMCP({
        config: modelSpecificConfig,
        messages: history,
        model: selectedModel,
        think: thinkEnabled,
        mcpEnabled: mcpEnabled,
      })) {
        // typewriter effect for each chunk
        for (let i = 0; i < chunk.length; i++) {
          if (!assistantOutputStarted && chunk[i]) {
            setAssistantOutputStarted(true)
          }
          assistant.content += chunk[i]
          setMessages(prev => prev.map((m, i2) => (i2 === assistantIndex ? assistant : m)))
          await sleep(6)
        }
      }
      setTypingIndex(null)
      setThinkStartAt(null)
      setIsGenerating(false)
      abortControllerRef.current = null
      // 主页面不需要调用全局addMessage，避免重复消息
      await log('INFO', 'chat_send_end', { model: selectedModel, outputLen: assistant.content.length })
      // persist conversation
      const updated: Conversation = {
        id: cid,
        title: newMessages[0]?.content.slice(0, 24) || '对话',
        model: selectedModel,
        provider: config.provider as any,
        updatedAt: Date.now(),
        messages: [...newMessages, assistant].map(m=>({ role:m.role, content:m.content, createdAt: Date.now() }))
      }
      const others = conversations.filter(c=>c.id!==cid)
      const saved = [updated, ...others].sort((a,b)=> b.updatedAt - a.updatedAt)
      setConversations(saved)
      await saveConversations(saved)
    } catch (err) {
      assistant.content += '\n[Error] Request failed.'
      setMessages(prev => prev.map((m, i) => (i === assistantIndex ? assistant : m)))
      setTypingIndex(null)
      setThinkStartAt(null)
      setIsGenerating(false)
      abortControllerRef.current = null
      await log('ERROR', 'chat_send_error', { error: String(err) })
    }
  }

  // 检查当前模型是否支持视觉
  const currentModelConfig = config.models?.find(m => m.name === currentModel)
  const supportsVision = currentModelConfig?.supportsVision || false

  // 文件输入引用
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)

  // 处理文件选择
  const handleFileSelect = async (files: FileList | null) => {
    if (!files) return

    const validFiles: File[] = []
    const maxSize = 10 * 1024 * 1024 // 10MB
    const maxImages = 5

    Array.from(files).forEach(file => {
      if (!file.type.startsWith('image/')) return
      if (file.size > maxSize) return
      if (selectedImages.length + validFiles.length >= maxImages) return
      validFiles.push(file)
    })

    const newImages: ImageAttachment[] = []
    for (const file of validFiles) {
      try {
        const base64 = await fileToBase64(file)
        const imageAttachment: ImageAttachment = {
          id: `img_${Date.now()}_${Math.random().toString(36).slice(2)}`,
          name: file.name,
          url: URL.createObjectURL(file),
          base64: base64,
          mimeType: file.type,
          size: file.size
        }
        newImages.push(imageAttachment)
      } catch (error) {
        console.error(`Failed to process ${file.name}:`, error)
      }
    }

    if (newImages.length > 0) {
      setSelectedImages([...selectedImages, ...newImages])
      
      // 自动切换到VL模型
      const vlModel = config.vlModel || config.models?.find(m => m.supportsVision)?.name
      if (vlModel && currentModel !== vlModel) {
        useStore.getState().setConfig({ model: vlModel })
        console.log('🔄 Auto-switched to VL model:', vlModel)
      }
    }
  }

  const fileToBase64 = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => {
        const result = reader.result as string
        const base64 = result.split(',')[1]
        resolve(base64)
      }
      reader.onerror = reject
      reader.readAsDataURL(file)
    })
  }

  // 拖拽处理
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    handleFileSelect(e.dataTransfer.files)
  }

  const handleImageUploadClick = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click()
    }
  }

  const removeImage = (imageId: string) => {
    const updatedImages = selectedImages.filter(img => {
      if (img.id === imageId) {
        URL.revokeObjectURL(img.url)
        return false
      }
      return true
    })
    setSelectedImages(updatedImages)
  }

  // 截图相关函数
  const startScreenshot = async () => {
    setIsScreenshotLoading(true)
    try {
      console.log('🖼️ Starting system screenshot...')
      // 添加短暂延迟以显示loading状态
      await new Promise(resolve => setTimeout(resolve, 100))
      await invoke('start_screenshot')
      // 不在这里隐藏loading，等待screenshot-ready事件
    } catch (error) {
      console.error('❌ Failed to start screenshot:', error)
      setIsScreenshotLoading(false)
    }
  }

  // Agent execution function (merged from floating window)
  const executeAgent = async (userInput: string): Promise<boolean> => {
    if (!contextTarget) {
      console.error('❌ No context target set')
      return false
    }
    
    try {
      setIsAgentRunning(true)
      setTaskflowProgress({ steps: [], isComplete: false })
      console.log('🤖 Executing Agent with input:', userInput)
      
      // Generate session_id
      const sessionId = `session_${Date.now()}`
      console.log('📋 Generated session_id:', sessionId)
      
      // Start SSE listener for progress
      console.log('🔌 Starting SSE listener...')
      const eventSource = new EventSource(`http://localhost:8765/agent/progress/${sessionId}`)
      eventSourceRef.current = eventSource
      
      // Wait for connection with timeout
      const connectionPromise = new Promise<void>((resolve) => {
        const timeoutId = setTimeout(() => {
          console.warn('⚠️ SSE connection wait timeout, continuing...')
          resolve()
        }, 2000)
        
        eventSource.onopen = () => {
          console.log('✅ SSE connection established')
          clearTimeout(timeoutId)
          resolve()
        }
      })
      
      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          console.log('📡 SSE progress received:', data)
          
          if (data.done || data.timeout || data.error) {
            console.log('🏁 SSE task complete, closing connection')
            eventSource.close()
            eventSourceRef.current = null
            setTaskflowProgress(prev => ({ ...prev, isComplete: true }))
            return
          }
          
          const kind = data.kind || 'status'
          
          if (kind === 'plan_ready' && data.data?.steps) {
            // Plan ready - initialize all steps as pending
            const steps: StepProgress[] = data.data.steps.map((s: any) => ({
              step_id: s.step_id,
              tool: s.tool,
              description: s.description,
              status: 'pending' as const
            }))
            setTaskflowProgress(prev => ({
              ...prev,
              steps,
              currentStep: data.status
            }))
          } else if (kind === 'step_start') {
            // Step started - mark as running
            setTaskflowProgress(prev => ({
              ...prev,
              currentStep: data.status,
              steps: prev.steps.map(s => 
                s.step_id === data.step_id 
                  ? { ...s, status: 'running' as const }
                  : s
              )
            }))
          } else if (kind === 'step_done') {
            // Step done - mark as done
            setTaskflowProgress(prev => ({
              ...prev,
              currentStep: data.status,
              steps: prev.steps.map(s => 
                s.step_id === data.step_id 
                  ? { ...s, status: 'done' as const }
                  : s
              )
            }))
          } else if (kind === 'step_error') {
            // Step error - mark as error
            setTaskflowProgress(prev => ({
              ...prev,
              currentStep: data.status,
              steps: prev.steps.map(s => 
                s.step_id === data.step_id 
                  ? { ...s, status: 'error' as const, error: data.error }
                  : s
              )
            }))
          } else if (data.status) {
            // Generic status update
            setTaskflowProgress(prev => ({
              ...prev,
              currentStep: data.status
            }))
          }
        } catch (e) {
          console.error('❌ Failed to parse SSE data:', e)
        }
      }
      
      eventSource.onerror = (error) => {
        console.error('❌ SSE connection error:', error)
        eventSource.close()
        eventSourceRef.current = null
      }
      
      await connectionPromise
      
      // Call Agent HTTP API
      console.log('🚀 Sending agent_execute request...')
      const response = await invoke('agent_execute', {
        request: {
          app_name: contextTarget.app_name,
          window_title: contextTarget.window_title,
          prompt: userInput,
          session_id: sessionId
        }
      }) as any
      
      console.log('🤖 Agent response:', response)
      
      if (response.success && response.result && response.result.trim()) {
        // Add to message history
        const userMessage: Message = { role: 'user', content: userInput }
        const assistantMessage: Message = { role: 'assistant', content: response.result }
        // Always keep a trace in main UI when agent runs
        setMessages(prev => [...prev, userMessage, assistantMessage])
        
        // Handle response based on output mode
        if (outputMode === 'W') {
          // W mode: Write result to target application
          await invoke('simulate_text_input', { text: response.result })
          console.log('✅ Agent result input to app:', response.result.substring(0, 50) + '...')
          
          // Wait for text input, then send Enter
          await new Promise(resolve => setTimeout(resolve, 500))
          await invoke('simulate_key_press', { key: 'Return' })
          console.log('✅ Sent Enter key to app')
        } else {
          // R mode: Show in UI only (already added to messages above)
          console.log('✅ Agent result displayed in UI (R mode)')
        }
        
        setTaskflowProgress(prev => ({ ...prev, isComplete: true }))
        return true
      } else {
        // Check for no-reply-needed case
        if (response.success && response.result === '') {
          console.log('ℹ️ Agent returned empty result (no reply needed)')
          setTaskflowProgress(prev => ({ ...prev, isComplete: true }))
          return true
        } else {
          console.log('⚠️ Agent returned no content')
          setTaskflowProgress(prev => ({ ...prev, isComplete: true }))
          return false
        }
      }
    } catch (error) {
      console.error('❌ Agent execution failed:', error)
      setTaskflowProgress(prev => ({ ...prev, isComplete: true }))
      return false
    } finally {
      setIsAgentRunning(false)
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
    }
  }
  
  const stopLoop = () => {
    autoLoopStopFlag.current = true
    if (autoLoopTimeoutRef.current) {
      clearTimeout(autoLoopTimeoutRef.current)
      autoLoopTimeoutRef.current = null
    }
    setLoopEnabled(false)
    console.log('🛑 Loop stopped')
  }

  const scheduleNextLoop = async () => {
    if (autoLoopStopFlag.current) return
    if (!contextTarget || !agentEnabled) return

    const prompt = loopPromptRef.current.trim()
    if (!prompt) return

    console.log('⏰ Scheduling next Loop iteration in 10 seconds')
    autoLoopTimeoutRef.current = setTimeout(async () => {
      if (autoLoopStopFlag.current) return
      console.log('🚀 Executing Agent in Loop:', new Date().toLocaleTimeString())
      await executeAgent(prompt)
      await scheduleNextLoop()
    }, 10000)
  }

  const startLoopWithPrompt = async (prompt: string) => {
    if (!contextTarget || !agentEnabled) return

    const p = prompt.trim()
    if (!p) {
      ui.toast('warning', t('context.loop_need_prompt'))
      return
    }

    loopPromptRef.current = p
    setLoopEnabled(true)
    autoLoopStopFlag.current = false

    console.log('🔄 Loop started')
    await executeAgent(p)
    await scheduleNextLoop()
  }

  const toggleLoop = async () => {
    if (loopEnabled) {
      stopLoop()
      return
    }
    // Start loop immediately if input is present; otherwise keep enabled and wait for next send
    if (input.trim()) {
      const p = input.trim()
      setInput('')
      await startLoopWithPrompt(p)
    } else {
      // Enable loop, but it will start after the next send (uses that prompt)
      setLoopEnabled(true)
      autoLoopStopFlag.current = false
      ui.toast('info', t('context.loop_armed'))
    }
  }
  
  // Handle context-aware send
  const handleContextSend = async () => {
    if (!input.trim() || isAgentRunning) return
    
    const userInput = input.trim()
    setInput('')
    
    if (contextTarget) {
      if (agentEnabled) {
        // Agent path
        const success = await executeAgent(userInput)
        if (!success) {
          console.log('❌ Agent execution failed')
        }
        // If loop is enabled, this prompt becomes the loop prompt and we schedule next iteration
        if (loopEnabled) {
          loopPromptRef.current = userInput
          autoLoopStopFlag.current = false
          await scheduleNextLoop()
        }
        return
      }
      
      // Manual path (Agent off): W writes to app, R shows in UI only
      if (outputMode === 'W') {
        await invoke('simulate_text_input', { text: userInput })
        await new Promise(resolve => setTimeout(resolve, 200))
        await invoke('simulate_key_press', { key: 'Return' })
        console.log('✅ Manual write (W) sent to app')
      } else {
        setMessages(prev => [...prev, { role: 'user', content: userInput }])
        console.log('✅ Manual read (R) shown in UI')
      }
    } else {
      // No context target, use normal chat
      handleSend()
    }
  }
  
  // Clear context target
  const clearContextTarget = () => {
    setContextTarget(null)
    setIsExpanded(false)
    stopLoop()
  }
  
  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (autoLoopTimeoutRef.current) {
        clearTimeout(autoLoopTimeoutRef.current)
      }
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
      }
    }
  }, [])


  const InputBar = (
    <div 
      className={`space-y-3 transition-colors ${
        dragOver ? 'bg-gray-50 bg-opacity-20 rounded-lg p-2' : ''
      }`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Taskflow progress panel - show when executing or when steps exist */}
      {(!taskflowProgress.isComplete || taskflowProgress.steps.length > 0) && (
        <div className="bg-gray-50 border border-gray-200 rounded-xl px-4 py-3 space-y-2">
          {/* Current status */}
          {taskflowProgress.currentStep && (
            <div className="flex items-center gap-3 mb-3">
              {!taskflowProgress.isComplete && (
                <div className="w-3 h-3 bg-blue-500 rounded-full animate-pulse" />
              )}
              <span className="text-sm text-gray-700 font-medium">{taskflowProgress.currentStep}</span>
            </div>
          )}
          
          {/* Step list */}
          {taskflowProgress.steps.length > 0 && (
            <div className="space-y-1.5">
              {taskflowProgress.steps.map((step, idx) => (
                <div 
                  key={step.step_id || idx} 
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                    step.status === 'running' ? 'bg-blue-100 border border-blue-300' :
                    step.status === 'done' ? 'bg-green-50 border border-green-200' :
                    step.status === 'error' ? 'bg-red-50 border border-red-200' :
                    'bg-white border border-gray-200'
                  }`}
                >
                  {/* Status indicator */}
                  <div className={`w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold ${
                    step.status === 'running' ? 'bg-blue-500 text-white' :
                    step.status === 'done' ? 'bg-green-500 text-white' :
                    step.status === 'error' ? 'bg-red-500 text-white' :
                    'bg-gray-300 text-gray-600'
                  }`}>
                    {step.status === 'running' ? (
                      <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                    ) : step.status === 'done' ? (
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                      </svg>
                    ) : step.status === 'error' ? (
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    ) : (
                      step.step_id || (idx + 1)
                    )}
                  </div>
                  
                  {/* Tool name */}
                  {step.tool && (
                    <span className={`font-medium ${
                      step.status === 'running' ? 'text-blue-700' :
                      step.status === 'done' ? 'text-green-700' :
                      step.status === 'error' ? 'text-red-700' :
                      'text-gray-600'
                    }`}>
                      {step.tool}
                    </span>
                  )}
                  
                  {/* Description */}
                  {step.description && (
                    <span className="text-gray-500 truncate flex-1" title={step.description}>
                      {step.description.length > 40 ? step.description.slice(0, 40) + '...' : step.description}
                    </span>
                  )}
                  
                  {/* Error message */}
                  {step.error && (
                    <span className="text-red-600 text-xs truncate max-w-[150px]" title={step.error}>
                      {step.error.slice(0, 30)}...
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
          
          {/* Close button when complete */}
          {taskflowProgress.isComplete && taskflowProgress.steps.length > 0 && (
            <button
              onClick={() => setTaskflowProgress({ steps: [], isComplete: true })}
              className="mt-2 text-xs text-gray-500 hover:text-gray-700 underline"
            >
              {t('settings.close') || 'Close'}
            </button>
          )}
        </div>
      )}
      
      {/* 已上传的图片预览 - 仅在有图片时显示 */}
      {selectedImages.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {selectedImages.map((image) => (
            <div key={image.id} className="relative group">
              <div className="w-16 h-16 rounded-lg overflow-hidden bg-gray-100">
                <img
                  src={image.url}
                  alt={image.name}
                  className="w-full h-full object-cover"
                />
              </div>
              <button
                onClick={() => removeImage(image.id)}
                className="absolute -top-2 -right-2 w-5 h-5 bg-red-500 text-white rounded-full flex items-center justify-center text-xs opacity-0 group-hover:opacity-100 transition-opacity"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}
      
      <div 
        className={`h-[72px] bg-gray-100 rounded-[24px] flex items-center px-6 gap-3 transition-colors ${
          dragOver ? 'bg-gray-100 ring-2 ring-gray-300' : ''
        } ${contextTarget ? 'ring-2 ring-blue-300' : ''}`}
      >
        {/* Context target app name display */}
        {contextTarget && (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-blue-100 rounded-full">
            <span className="text-xs font-medium text-blue-700 max-w-[100px] truncate" title={contextTarget.app_name}>
              {contextTarget.app_name}
            </span>
            <button
              onClick={clearContextTarget}
              className="text-blue-500 hover:text-blue-700 transition-colors"
              title={t('context.clear') || 'Clear target'}
            >
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}
        
        <input
          ref={inputRef}
          className="flex-1 bg-transparent outline-none text-gray-700 placeholder-gray-400"
          placeholder={contextTarget 
            ? (loopEnabled 
              ? (t('context.loop_running') || 'Loop running, click Loop to stop...') 
              : (t('context.input_task') || 'Enter task for this app...'))
            : t('chat.send_message_with_image')}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { 
            if (e.key === 'Enter' && !e.shiftKey) { 
              e.preventDefault()
              if (contextTarget) {
                handleContextSend()
              } else {
                handleSend()
              }
            }
            if (e.key === 'Escape') {
              clearContextTarget()
            }
          }}
          disabled={isAgentRunning}
        />
        
        {/* Expand/collapse button */}
        <button
          className="w-10 h-10 rounded-full flex items-center justify-center border bg-white text-gray-700 border-gray-200 hover:bg-gray-50"
          title={isExpanded ? (t('context.collapse') || 'Collapse') : (t('context.expand') || 'Expand')}
          onClick={() => setIsExpanded(!isExpanded)}
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            {isExpanded ? (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            )}
          </svg>
        </button>
        
        {/* Expanded mode buttons */}
        {isExpanded && (
          <>
            {/* Agent(A) toggle */}
            <button
              className={`w-10 h-10 rounded-full flex items-center justify-center border font-bold text-sm transition-colors ${
                agentEnabled
                  ? 'bg-blue-600 text-white border-blue-600 hover:bg-blue-700'
                  : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'
              }`}
              title={agentEnabled
                ? (t('context.agent_on') || 'Agent enabled')
                : (t('context.agent_off') || 'Agent disabled')}
              onClick={() => {
                const next = !agentEnabled
                setAgentEnabled(next)
                if (!next) {
                  stopLoop()
                }
              }}
              disabled={isAgentRunning}
            >
              A
            </button>
            
            {/* Output R/W toggle */}
            {contextTarget && (
              <button
                className={`w-10 h-10 rounded-full flex items-center justify-center border font-bold text-sm transition-colors ${
                  outputMode === 'W'
                    ? 'bg-green-600 text-white border-green-600 hover:bg-green-700'
                    : 'bg-purple-600 text-white border-purple-600 hover:bg-purple-700'
                }`}
                title={outputMode === 'W'
                  ? (t('context.output_w') || 'W: write to app')
                  : (t('context.output_r') || 'R: show in UI')}
                onClick={() => setOutputMode(outputMode === 'W' ? 'R' : 'W')}
                disabled={isAgentRunning}
              >
                {outputMode}
              </button>
            )}
            
            {/* Loop button: only when Agent is enabled */}
            {contextTarget && agentEnabled && (
              <button
                className={`w-10 h-10 rounded-full flex items-center justify-center border font-bold text-sm transition-colors ${
                  loopEnabled
                    ? 'bg-orange-500 text-white border-orange-500 hover:bg-orange-600'
                    : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'
                }`}
                title={loopEnabled 
                  ? (t('context.stop_loop') || 'Stop Loop')
                  : (t('context.start_loop') || 'Start Loop (10s interval)')}
                onClick={toggleLoop}
                disabled={false}
              >
                {loopEnabled ? (
                  <span className="flex items-center gap-1.5">
                    <span className="w-2 h-2 bg-white rounded-full animate-pulse" />
                    L
                  </span>
                ) : (
                  'L'
                )}
              </button>
            )}
            
            {/* 图片上传按钮 */}
            <button
              className="w-10 h-10 rounded-full flex items-center justify-center border bg-white text-gray-700 border-gray-200 hover:bg-gray-50"
              title={t('chat.upload_image') || 'Upload image'}
              onClick={handleImageUploadClick}
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 002 2z" />
              </svg>
            </button>

            {/* 截图按钮 */}
            <button
              className="w-10 h-10 rounded-full flex items-center justify-center border bg-white text-gray-700 border-gray-200 hover:bg-gray-50"
              title={t('chat.screenshot') || 'Screenshot'}
              onClick={startScreenshot}
              disabled={isScreenshotLoading}
            >
              {isScreenshotLoading ? (
                <div className="w-4 h-4 border-2 border-gray-400 border-t-gray-700 rounded-full animate-spin" />
              ) : (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              )}
            </button>
          </>
        )}
        
        {/* 隐藏的文件输入 */}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={(e) => handleFileSelect(e.target.files)}
        />
        
        {/* 发送按钮 */}
        <button
          className={`w-10 h-10 rounded-full flex items-center justify-center ${
            isGenerating || isAgentRunning
              ? 'bg-gray-900 text-white hover:bg-gray-800' 
              : 'bg-gray-900 text-white hover:bg-gray-800'
          }`}
          onClick={contextTarget ? handleContextSend : handleSend}
          aria-label={isGenerating ? t('chat.stop') : t('chat.send')}
          disabled={isAgentRunning}
        >
          {isGenerating || isAgentRunning ? (
            <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          ) : (
            <IconSend className="w-5 h-5" />
          )}
        </button>
      </div>
    </div>
  )

  const TopBar = (
    <div className="h-12 flex items-center justify-between px-4">
      <div className="flex items-center gap-4 text-gray-700">
        {/* 系统标题栏左上角图标由系统绘制；这里的内嵌 logo去除 */}
        <button className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center" onClick={() => setDrawerOpen(true)} aria-label={t('chat.menu')}>
          <IconList className="w-4 h-4" />
        </button>
        <button className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center" onClick={() => { setView('starter'); setMessages([]); setCurrentCid('') }} aria-label={t('chat.new_chat')}>
          <IconEdit className="w-4 h-4" />
        </button>
        <button className="px-3 h-8 rounded-full bg-gray-100 flex items-center justify-center text-xs font-medium text-gray-700 hover:bg-gray-200" onClick={toggleLanguage} aria-label={t('chat.language')}>
          {currentLanguage === 'zh-CN' ? 'EN' : '中'}
        </button>
        <div className="text-sm text-gray-600">Yao</div>
      </div>
      <div />
    </div>
  )

  const Drawer = (
    <div className={`fixed inset-0 z-50 ${isDrawerOpen ? 'pointer-events-auto' : 'pointer-events-none'}`}>
      <div
        className={`absolute inset-0 bg-black/30 transition-opacity duration-400 ${isDrawerOpen ? 'opacity-100' : 'opacity-0'}`}
        onClick={() => setDrawerOpen(false)}
      />
      <div
        className={`absolute left-0 top-0 bottom-0 w-[360px] bg-white border-r border-gray-200 p-4 flex flex-col will-change-transform transform transition-transform duration-400 ease-[cubic-bezier(0.22,1,0.36,1)] rounded-r-2xl shadow-2xl ${
          isDrawerOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="space-y-3">
          <button className="w-full h-11 rounded-lg bg-gray-100 text-gray-800 text-left px-3" onClick={() => { setView('starter'); setMessages([]); setCurrentCid(''); setDrawerOpen(false) }}>{t('chat.new_chat')}</button>
          <button className="w-full h-11 rounded-lg bg-gray-100 text-gray-800 text-left px-3" onClick={() => { setShowSettings(true); setDrawerOpen(false) }}>{t('chat.settings')}</button>
        </div>
        <div className="pt-4 text-xs text-gray-500">{t('chat.this_week')}</div>
        <div className="flex-1 overflow-y-auto space-y-3 pt-2">
          {conversations.map((c) => (
            <div key={c.id} className={`text-sm truncate cursor-pointer ${currentCid===c.id?'text-gray-900':'text-gray-800'}`} onClick={()=>{ setCurrentCid(c.id); setMessages(c.messages.map(m=>({role:m.role, content:m.content}))); setView('main'); setDrawerOpen(false) }}>
              {c.title}
            </div>
          ))}
        </div>
      </div>
    </div>
  )

  // Esc 关闭抽屉 & 打开时锁定滚动
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setDrawerOpen(false)
    }
    window.addEventListener('keydown', onKeyDown)
    try {
      if (isDrawerOpen) document.body.classList.add('overflow-hidden')
      else document.body.classList.remove('overflow-hidden')
    } catch {}
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      try { document.body.classList.remove('overflow-hidden') } catch {}
    }
  }, [isDrawerOpen])

  // thinking timer
  useEffect(() => {
    if (thinkStartAt === null || assistantOutputStarted) return
    const id = setInterval(() => {
      setThinkingMs(Date.now() - (thinkStartAt ?? 0))
    }, 250)
    return () => clearInterval(id)
  }, [thinkStartAt, assistantOutputStarted])

  if (view === 'starter') {
    const hasHistory = messages.length > 0
    return (
      <div className="relative h-screen w-screen bg-white text-gray-900 overflow-hidden">
        <div className={`h-full transition-[padding] duration-400 ease-[cubic-bezier(0.22,1,0.36,1)] ${isDrawerOpen ? 'pl-[360px]' : 'pl-0'}`}>
          <div
            className={`flex flex-col h-full w-full will-change-transform origin-center transform transition-[transform,border-radius,box-shadow] duration-400 ease-[cubic-bezier(0.22,1,0.36,1)] bg-white ${
              isDrawerOpen ? 'scale-[0.96] rounded-3xl shadow-[0_10px_40px_rgba(0,0,0,0.18)]' : 'scale-100'
            }`}
          >
          {TopBar}
          {!hasHistory ? (
            <div className="flex-1 w-full flex items-center justify-center">
              <img src="/images/yaologo-1.png" alt="logo" className="w-24 h-24 select-none" />
            </div>
          ) : (
            <div ref={listRef} className="flex-1 overflow-y-auto p-6 scrollbar">
              {messages.map((m, idx) => (
                <ChatBubble
                  key={idx}
                  role={m.role}
                  content={m.content}
                  images={m.images}
                  isStreaming={typingIndex === idx && m.role === 'assistant'}
                  thinkingMs={!assistantOutputStarted && typingIndex === idx && m.role === 'assistant' ? thinkingMs : undefined}
                  thinkEnabled={thinkEnabled}
                  onCopy={()=> navigator.clipboard.writeText(m.content)}
                  onRetry={m.role==='assistant'? ()=>{ setInput(messages.filter((_,i)=>i<idx).map(m=>m.content).join('\n')); handleSend() } : undefined}
                />
              ))}
            </div>
          )}
          <div className="flex-shrink-0 w-full px-6 pb-6 bg-white border-t border-gray-100">
            <div className="max-w-[1040px] mx-auto py-4">{InputBar}</div>
          </div>
          </div>
        </div>
        {Drawer}
        {showSettings && <SettingsDrawer key={currentLanguage} close={() => setShowSettings(false)} />}
        
        {/* 移除了内联截图覆盖层，改为使用独立窗口 */}
        
      </div>
    )
  }

  // 显示加载屏幕
  return (
    <div className="relative h-screen w-screen bg-white text-gray-900 overflow-hidden">
      <div className={`h-full transition-[padding] duration-400 ease-[cubic-bezier(0.22,1,0.36,1)] ${isDrawerOpen ? 'pl-[360px]' : 'pl-0'}`}>
        <div
          className={`flex flex-col h-full w-full will-change-transform origin-center transform transition-[transform,border-radius,box-shadow] duration-400 ease-[cubic-bezier(0.22,1,0.36,1)] bg-white ${
            isDrawerOpen ? 'scale-[0.96] rounded-3xl shadow-[0_10px_40px_rgba(0,0,0,0.18)]' : 'scale-100'
          }`}
        >
          {TopBar}
          {/* Chat Area */}
          <div className="flex-1 flex flex-col min-h-0">
            <div ref={listRef} className="flex-1 overflow-y-auto p-6 scrollbar">
              {messages.map((m, idx) => (
                <ChatBubble
                  key={idx}
                  role={m.role}
                  content={m.content}
                  images={m.images}
                  isStreaming={typingIndex === idx && m.role === 'assistant'}
                  thinkingMs={!assistantOutputStarted && typingIndex === idx && m.role === 'assistant' ? thinkingMs : undefined}
                  thinkEnabled={thinkEnabled}
                />
              ))}
            </div>
            <div className="flex-shrink-0 w-full px-6 pb-6 bg-white border-t border-gray-100">
              <div className="max-w-[920px] mx-auto py-4">{InputBar}</div>
            </div>
          </div>
        </div>
      </div>
      {Drawer}
      {showSettings && <SettingsDrawer close={() => setShowSettings(false)} />}
      {pullingModel && (
        <ModelPullDialog baseUrl={config.baseUrl} model={pullingModel} onClose={()=> setPullingModel('')} />
      )}
      
    </div>
  )
}


