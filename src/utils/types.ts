export type Provider = 'openai'

export type ModelCategory = 'vl' | 'light' | 'advanced' | 'embedding'

export type ModelConfig = {
  name: string
  provider: Provider
  baseUrl?: string
  apiKey?: string
  category?: ModelCategory
  supportsVision?: boolean
}

export type MCPConfig = {
  id: string
  name: string
  command: string
  args?: string[]
  env?: Record<string, string>
  enabled: boolean
  description?: string
}

export type MCPToolCall = {
  tool: string
  arguments: Record<string, any>
}

export type MCPToolResult = {
  success: boolean
  result?: any
  error?: string
}

export type ReActStep = {
  thought: string
  action?: MCPToolCall
  observation?: string
}

export type MCPTool = {
  name: string
  description?: string
  inputSchema?: any
}

export type MCPServerInfo = {
  name: string
  version?: string
  tools?: MCPTool[]
}

// ReAct循环执行相关类型
export type ReActCycle = {
  cycleId: number
  thought: string
  action?: MCPToolCall
  observation?: string
  reflection: string
  success: boolean
  error?: string
}

export type TaskExecution = {
  taskId: string
  description: string
  cycles: ReActCycle[]
  completed: boolean
  maxRetries: number
  currentRetry: number
}

// 模型分类显示名称
export const ModelCategoryNames = {
  vl: {
    en: 'Vision-Language Models',
    zh: '多模态模型',
    short: 'VL Models'
  },
  light: {
    en: 'Lightweight Models',
    zh: '轻量模型',
    short: 'Light Models'
  },
  advanced: {
    en: 'Advanced Models', 
    zh: '高级模型',
    short: 'Advanced Models'
  },
  embedding: {
    en: 'Embedding Models',
    zh: 'Embedding模型',
    short: 'Embedding'
  }
} as const

// 获取模型分类显示名称的工具函数
export function getModelCategoryName(category: ModelCategory, language: 'zh-CN' | 'en' = 'zh-CN', short: boolean = false): string {
  const names = ModelCategoryNames[category]
  if (short) {
    return names.short
  }
  return language === 'zh-CN' ? names.zh : names.en
}

// 图片附件类型
export type ImageAttachment = {
  id: string
  name: string
  url: string
  base64: string
  mimeType: string
  size: number
}


