import { invoke } from '@tauri-apps/api/core'
import { AppConfig } from './store'

/**
 * 统一的配置管理工具类
 * 负责配置的读取、写入、验证和默认值管理
 */
export class ConfigManager {
  private static instance: ConfigManager
  private configCache: AppConfig | null = null

  private constructor() {}

  public static getInstance(): ConfigManager {
    if (!ConfigManager.instance) {
      ConfigManager.instance = new ConfigManager()
    }
    return ConfigManager.instance
  }

  /**
   * 获取默认配置
   */
  public getDefaultConfig(): AppConfig {
    return {
      provider: 'openai',
      baseUrl: 'https://api.openai.com/v1',
      apiKey: '',
      model: 'gpt-3.5-turbo',
      models: [
        { name: 'gpt-4o', provider: 'openai', baseUrl: 'https://api.openai.com/v1', category: 'vl', supportsVision: true },
        { name: 'ernie-0.3b', provider: 'openai', baseUrl: 'http://localhost:8766/v1', apiKey: 'dummy', category: 'light', supportsVision: false },
        { name: 'gpt-3.5-turbo', provider: 'openai', baseUrl: 'https://api.openai.com/v1', category: 'light', supportsVision: false },
        { name: 'gpt-4', provider: 'openai', baseUrl: 'https://api.openai.com/v1', category: 'advanced', supportsVision: false },
        { name: 'BAAI/bge-m3', provider: 'openai', baseUrl: 'https://api.siliconflow.cn/v1/embeddings', category: 'embedding', supportsVision: false }
      ],
      vlModel: 'gpt-4o',
      lightModel: 'ernie-0.3b',
      advancedModel: 'gpt-4',
      embeddingModel: 'BAAI/bge-m3',
      streamingEnabled: true,
      defaultThink: true,
      maxContextMessages: 20,
      temperature: 0.6,
      language: 'zh-CN',
      mcpServers: [],
      mcpServerInfos: {},
      mcpMaxRetries: 3,
      mcpReflectionEnabled: true,
      // Legacy embedding fields (保留用于向后兼容)
      embeddingUrl: 'https://api.siliconflow.cn/v1/embeddings',
      embeddingApiKey: '',
    }
  }

  /**
   * 读取配置文件
   */
  public async loadConfig(): Promise<AppConfig> {
    try {
      // 获取配置文件路径
      console.log('[ConfigManager] Step 1: Getting config path...')
      const configPath = await invoke<string>('get_config_path')
      console.log('[ConfigManager] Step 2: Config path =', configPath)

      // 尝试读取配置文件
      console.log('[ConfigManager] Step 3: Importing fs module...')
      const fs = await import('@tauri-apps/plugin-fs')
      console.log('[ConfigManager] Step 4: Reading file...')
      const configContent = await fs.readTextFile(configPath)
      console.log('[ConfigManager] Step 5: File content length =', configContent.length)
      
      // 解析配置
      console.log('[ConfigManager] Step 6: Parsing JSON...')
      const parsedConfig = JSON.parse(configContent) as Partial<AppConfig>
      console.log('[ConfigManager] Step 7: Parsed config baseUrl =', parsedConfig.baseUrl)
      
      // 合并默认配置和读取的配置
      const mergedConfig = this.mergeWithDefaults(parsedConfig)
      console.log('[ConfigManager] Step 8: Merged config baseUrl =', mergedConfig.baseUrl)
      
      // 验证配置
      const validatedConfig = this.validateConfig(mergedConfig)
      console.log('[ConfigManager] Step 9: Validated config baseUrl =', validatedConfig.baseUrl)
      
      // 缓存配置
      this.configCache = validatedConfig
      
      console.log('[ConfigManager] ✅ Config loaded successfully. Final baseUrl:', validatedConfig.baseUrl)
      return validatedConfig

    } catch (error) {
      console.error('[ConfigManager] ❌ Failed to load config:', error)
      console.error('[ConfigManager] Error details:', {
        message: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined,
        type: typeof error,
        error: error
      })
      
      // 如果读取失败，返回默认配置
      const defaultConfig = this.getDefaultConfig()
      this.configCache = defaultConfig
      
      console.log('[ConfigManager] Using default config. Default baseUrl:', defaultConfig.baseUrl)
      
      // 尝试保存默认配置
      try {
        await this.saveConfig(defaultConfig)
        console.log('[ConfigManager] 💾 Default config saved')
      } catch (saveError) {
        console.error('[ConfigManager] ❌ Failed to save default config:', saveError)
      }
      
      return defaultConfig
    }
  }

  /**
   * 保存配置文件
   */
  public async saveConfig(config: AppConfig): Promise<void> {
    try {
      // 验证配置
      const validatedConfig = this.validateConfig(config)
      
      // 获取配置文件路径
      const configPath = await invoke<string>('get_config_path')
      console.log('💾 Saving config to:', configPath)

      // 写入配置文件
      const fs = await import('@tauri-apps/plugin-fs')
      const configJson = JSON.stringify(validatedConfig, null, 2)
      await fs.writeTextFile(configPath, configJson)
      
      // 更新缓存
      this.configCache = validatedConfig
      
      console.log('✅ Config saved successfully')
      
      // 触发配置更新事件
      const { emit } = await import('@tauri-apps/api/event')
      await emit('config-updated', { config: validatedConfig })
      
    } catch (error) {
      console.error('❌ Failed to save config:', error)
      throw new Error(`保存配置失败: ${error}`)
    }
  }

  /**
   * 获取缓存的配置，如果没有缓存则读取配置
   */
  public async getConfig(): Promise<AppConfig> {
    if (this.configCache) {
      return this.configCache
    }
    return await this.loadConfig()
  }

  /**
   * 更新配置（部分更新）
   */
  public async updateConfig(partialConfig: Partial<AppConfig>): Promise<AppConfig> {
    const currentConfig = await this.getConfig()
    const updatedConfig = { ...currentConfig, ...partialConfig }
    await this.saveConfig(updatedConfig)
    return updatedConfig
  }

  /**
   * 清除配置缓存
   */
  public clearCache(): void {
    this.configCache = null
  }

  /**
   * 合并默认配置和用户配置
   */
  private mergeWithDefaults(userConfig: Partial<AppConfig>): AppConfig {
    const defaultConfig = this.getDefaultConfig()
    
    // 深度合并配置，确保所有必要字段都存在
    return {
      ...defaultConfig,
      ...userConfig,
      // 确保数组字段不为空
      models: userConfig.models && userConfig.models.length > 0 ? userConfig.models : defaultConfig.models,
      mcpServers: userConfig.mcpServers || defaultConfig.mcpServers,
      mcpServerInfos: userConfig.mcpServerInfos || defaultConfig.mcpServerInfos,
    }
  }

  /**
   * 验证配置的有效性
   */
  private validateConfig(config: AppConfig): AppConfig {
    // 基本验证
    if (!config.provider) config.provider = 'openai'
    if (!config.baseUrl) config.baseUrl = 'https://api.openai.com/v1'
    if (!config.models || config.models.length === 0) {
      config.models = this.getDefaultConfig().models
    }
    
    // 模型分类验证
    if (!config.embeddingModel) {
      // 尝试从 models 中找到 embedding 类型的模型
      const embeddingModelInList = config.models?.find(m => m.category === 'embedding')
      config.embeddingModel = embeddingModelInList?.name || 'BAAI/bge-m3'
    }
    
    // Legacy embedding fields (向后兼容)
    if (!config.embeddingUrl) {
      config.embeddingUrl = 'https://api.siliconflow.cn/v1/embeddings'
    }
    if (!config.embeddingApiKey) {
      config.embeddingApiKey = ''
    }
    
    // 数值验证
    if (typeof config.maxContextMessages !== 'number' || config.maxContextMessages < 1) {
      config.maxContextMessages = 20
    }
    if (typeof config.temperature !== 'number' || config.temperature < 0 || config.temperature > 2) {
      config.temperature = 0.6
    }
    if (typeof config.mcpMaxRetries !== 'number' || config.mcpMaxRetries < 1) {
      config.mcpMaxRetries = 3
    }
    
    return config
  }

  /**
   * 获取特定的配置值
   */
  public async getConfigValue<K extends keyof AppConfig>(key: K): Promise<AppConfig[K]> {
    const config = await this.getConfig()
    return config[key]
  }

  /**
   * 设置特定的配置值
   */
  public async setConfigValue<K extends keyof AppConfig>(key: K, value: AppConfig[K]): Promise<void> {
    await this.updateConfig({ [key]: value } as Partial<AppConfig>)
  }

  /**
   * 重置配置为默认值
   */
  public async resetConfig(): Promise<AppConfig> {
    const defaultConfig = this.getDefaultConfig()
    await this.saveConfig(defaultConfig)
    return defaultConfig
  }
}

// 导出单例实例
export const configManager = ConfigManager.getInstance()

// 导出便捷函数
export const loadConfig = () => configManager.loadConfig()
export const saveConfig = (config: AppConfig) => configManager.saveConfig(config)
export const getConfig = () => configManager.getConfig()
export const updateConfig = (partialConfig: Partial<AppConfig>) => configManager.updateConfig(partialConfig)
export const getConfigValue = <K extends keyof AppConfig>(key: K) => configManager.getConfigValue(key)
export const setConfigValue = <K extends keyof AppConfig>(key: K, value: AppConfig[K]) => configManager.setConfigValue(key, value)
export const resetConfig = () => configManager.resetConfig()
