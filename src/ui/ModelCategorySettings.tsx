import React from 'react'
import type { ModelConfig, ModelCategory } from '../utils/types'
import { getModelCategoryName } from '../utils/types'
import { Dropdown } from './Dropdown'

interface ModelCategorySettingsProps {
  models: ModelConfig[]
  vlModel?: string
  lightModel?: string
  advancedModel?: string
  onVlModelChange: (model: string) => void
  onLightModelChange: (model: string) => void
  onAdvancedModelChange: (model: string) => void
  language?: 'zh-CN' | 'en'
}

export const ModelCategorySettings: React.FC<ModelCategorySettingsProps> = ({
  models,
  vlModel,
  lightModel,
  advancedModel,
  onVlModelChange,
  onLightModelChange,
  onAdvancedModelChange,
  language = 'zh-CN'
}) => {
  // 按分类过滤模型
  const getModelsByCategory = (category: ModelCategory) => {
    return models.filter(model => model.category === category)
  }

  // 获取所有模型（作为后备选项）
  const getAllModels = () => {
    return models.map(model => ({
      value: model.name,
      label: model.name
    }))
  }

  // 获取分类模型选项
  const getCategoryModelOptions = (category: ModelCategory) => {
    const categoryModels = getModelsByCategory(category)
    if (categoryModels.length > 0) {
      return categoryModels.map(model => ({
        value: model.name,
        label: model.name
      }))
    }
    // 如果该分类没有模型，显示所有模型
    return getAllModels()
  }

  return (
    <div className="space-y-6">
      <div className="text-lg font-medium text-gray-900">
        {language === 'zh-CN' ? '模型分类设置' : 'Model Category Settings'}
      </div>
      
      <div className="space-y-4">
        {/* VL模型设置 */}
        <div className="space-y-2">
          <label className="block text-sm font-medium text-gray-700">
            {getModelCategoryName('vl', language)}
          </label>
          <div className="text-xs text-gray-500 mb-2">
            {language === 'zh-CN' 
              ? '支持图片+文字输入，适合图像理解、图文分析等任务' 
              : 'Supports image + text input, suitable for image understanding and analysis'}
          </div>
          <Dropdown
            value={vlModel}
            options={getCategoryModelOptions('vl')}
            onChange={onVlModelChange}
            placeholder={language === 'zh-CN' ? '选择多模态模型' : 'Select VL Model'}
          />
        </div>

        {/* 轻量模型设置 */}
        <div className="space-y-2">
          <label className="block text-sm font-medium text-gray-700">
            {getModelCategoryName('light', language)}
          </label>
          <div className="text-xs text-gray-500 mb-2">
            {language === 'zh-CN' 
              ? '快速响应，低延迟，适合简单对话和快速查询' 
              : 'Fast response, low latency, suitable for simple conversations'}
          </div>
          <Dropdown
            value={lightModel}
            options={getCategoryModelOptions('light')}
            onChange={onLightModelChange}
            placeholder={language === 'zh-CN' ? '选择轻量模型' : 'Select Light Model'}
          />
        </div>

        {/* 高级模型设置 */}
        <div className="space-y-2">
          <label className="block text-sm font-medium text-gray-700">
            {getModelCategoryName('advanced', language)}
          </label>
          <div className="text-xs text-gray-500 mb-2">
            {language === 'zh-CN' 
              ? '复杂推理，深度分析，适合专业任务和复杂问题' 
              : 'Complex reasoning, deep analysis, suitable for professional tasks'}
          </div>
          <Dropdown
            value={advancedModel}
            options={getCategoryModelOptions('advanced')}
            onChange={onAdvancedModelChange}
            placeholder={language === 'zh-CN' ? '选择高级模型' : 'Select Advanced Model'}
          />
        </div>
      </div>

      {/* 模型分类统计 */}
      <div className="mt-6 p-4 bg-gray-50 rounded-lg">
        <div className="text-sm font-medium text-gray-700 mb-2">
          {language === 'zh-CN' ? '模型分类统计' : 'Model Statistics'}
        </div>
        <div className="grid grid-cols-3 gap-4 text-sm">
          <div className="text-center">
            <div className="font-medium text-gray-600">
              {getModelsByCategory('vl').length}
            </div>
            <div className="text-gray-500">
              {language === 'zh-CN' ? '多模态' : 'VL Models'}
            </div>
          </div>
          <div className="text-center">
            <div className="font-medium text-green-600">
              {getModelsByCategory('light').length}
            </div>
            <div className="text-gray-500">
              {language === 'zh-CN' ? '轻量' : 'Light'}
            </div>
          </div>
          <div className="text-center">
            <div className="font-medium text-purple-600">
              {getModelsByCategory('advanced').length}
            </div>
            <div className="text-gray-500">
              {language === 'zh-CN' ? '高级' : 'Advanced'}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
