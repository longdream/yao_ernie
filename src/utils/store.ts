import { log } from './log'
import { create } from 'zustand'
import { invoke } from '@tauri-apps/api/core'
import { emit } from '@tauri-apps/api/event'
import type { ModelConfig, Provider, MCPConfig, MCPServerInfo, ModelCategory, ImageAttachment } from './types'
import { configManager, loadConfig, saveConfig } from './config'

export type AppConfig = {
  provider: Provider
  baseUrl: string
  apiKey?: string
  model?: string
  models?: ModelConfig[]
  // model categories
  vlModel?: string
  lightModel?: string
  advancedModel?: string
  embeddingModel?: string  // 指向 models 中 category='embedding' 的模型名称
  // chat options
  streamingEnabled?: boolean
  defaultThink?: boolean
  maxContextMessages?: number
  temperature?: number
  // ui options
  language?: 'zh-CN' | 'en'
  // mcp options
  mcpServers?: MCPConfig[]
  mcpServerInfos?: Record<string, MCPServerInfo>
  mcpMaxRetries?: number
  mcpReflectionEnabled?: boolean
  // legacy embedding fields (保留用于向后兼容)
  embeddingUrl?: string
  embeddingApiKey?: string
}

export type GlobalMessage = {
  role: 'user' | 'assistant'
  content: string
  images?: ImageAttachment[]
  timestamp: number
  conversationId?: string
}

type StoreState = {
  config: AppConfig
  messages: GlobalMessage[]
  setConfig: (partial: Partial<AppConfig>) => void
  addMessage: (message: Omit<GlobalMessage, 'timestamp'>, source?: 'main' | 'quick') => void
  clearMessages: () => void
  persist: () => Promise<void>
}

export const useStore = create<StoreState>((set, get) => ({
  config: configManager.getDefaultConfig(),
  messages: [],
  setConfig(partial) {
    const merged = { ...get().config, ...partial }
    set({ config: merged })
    log('DEBUG', 'setConfig', merged)
  },
  addMessage(message, source = 'main') {
    const newMessage: GlobalMessage = {
      ...message,
      timestamp: Date.now()
    }
    
    // 使用函数式更新确保状态一致性
    set(state => {
      const updatedMessages = [...state.messages, newMessage]
      
      // 在状态更新的同时发送事件，确保数据一致
      setTimeout(() => {
        emit('messages-updated', { 
          messages: updatedMessages,
          source: source
        })
      }, 0)
      
      return { messages: updatedMessages }
    })
    
    log('DEBUG', 'addMessage', { message: newMessage, source })
  },
  clearMessages() {
    set({ messages: [] })
    emit('messages-updated', { messages: [] })
    log('DEBUG', 'clearMessages', {})
  },
  async persist() {
    try {
      console.log('persist开始，使用ConfigManager...');
      await saveConfig(get().config);
      log('INFO', 'settings saved via ConfigManager', get().config)
    } catch (error) {
      console.error('persist失败:', error);
      log('ERROR', 'settings save failed', { error: String(error), config: get().config })
      throw error
    }
  },
}))

export async function bootstrapConfig() {
  try {
    console.log('🚀 Bootstrapping config with ConfigManager...')
    const config = await loadConfig()
    useStore.setState({ config })
    log('INFO', 'config loaded via ConfigManager', config)
    
    // 初始化MCP服务器（如果有启用的服务器）
    const enabledMCPServers = config.mcpServers?.filter(mcp => mcp.enabled) || []
    if (enabledMCPServers.length > 0) {
      // 异步初始化MCP服务器，不阻塞应用启动
      initializeMCPServersAsync(config.mcpServers || [])
    }
    
    return config
  } catch (error) {
    log('ERROR', 'config bootstrap failed', error)
    // 如果加载失败，使用默认配置
    const defaultConfig = configManager.getDefaultConfig()
    useStore.setState({ config: defaultConfig })
    return defaultConfig
  }
}

// 异步初始化MCP服务器
async function initializeMCPServersAsync(mcpServers: MCPConfig[]) {
  try {
    const { initializeMCPServers } = await import('./proxy')
    const serverInfos = await initializeMCPServers(mcpServers)
    
    // 更新store中的MCP服务器信息
    const currentConfig = useStore.getState().config
    useStore.setState({ 
      config: { 
        ...currentConfig, 
        mcpServerInfos: serverInfos 
      } 
    })
  } catch (error) {
    log('ERROR', 'mcp_async_initialization_failed', { error: String(error) })
  }
}


