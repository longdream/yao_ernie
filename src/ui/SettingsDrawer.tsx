import React, { useState, useEffect } from 'react'
import { useStore } from '../utils/store'
import type { ModelConfig, MCPConfig, MCPServerInfo, ModelCategory, getModelCategoryName } from '../utils/types'
import { Dropdown } from './Dropdown'
import { ModelCategorySettings } from './ModelCategorySettings'
import { invoke } from '@tauri-apps/api/core'
import { Command } from '@tauri-apps/plugin-shell'
import { t, tf, getCurrentLocale } from '../utils/i18n'
import { useUIOverlay } from './UIOverlay'

type Tab = 'models' | 'chat' | 'mcp' | 'python' | 'taskflow' | 'memory'

export const SettingsDrawer: React.FC<{ close: () => void }> = ({ close }) => {
  const { config, setConfig, persist } = useStore()
  const ui = useUIOverlay()
  const [tab, setTab] = useState<Tab>('models')
  const [local, setLocal] = useState(config)
  const [modelList, setModelList] = useState<ModelConfig[]>(config.models || [])
  const [mcpList, setMcpList] = useState<MCPConfig[]>(config.mcpServers || [])
  const [currentLang, setCurrentLang] = useState(getCurrentLocale())
  
  // Agent服务状态管理
  const [agentServiceStatus, setAgentServiceStatus] = useState<'running' | 'stopped' | 'checking'>('checking')
  const [isServiceOperating, setIsServiceOperating] = useState(false)
  
  // Task Flow 管理状态
  const [taskFlows, setTaskFlows] = useState<any[]>([])
  const [selectedFlow, setSelectedFlow] = useState<any | null>(null)
  const [flowJsonText, setFlowJsonText] = useState('')
  const [jsonError, setJsonError] = useState<string | null>(null)
  const [isSavingFlow, setIsSavingFlow] = useState(false)
  
  // 新建 Plan 状态
  const [showCreatePlanDialog, setShowCreatePlanDialog] = useState(false)
  const [newPlanTask, setNewPlanTask] = useState('')
  const [newPlanApp, setNewPlanApp] = useState('')
  const [isCreatingPlan, setIsCreatingPlan] = useState(false)
  
  // Prompt 编辑状态
  const [showEditPromptDialog, setShowEditPromptDialog] = useState(false)
  const [editingPrompt, setEditingPrompt] = useState('')
  const [currentEditStep, setCurrentEditStep] = useState<any | null>(null)
  const [isSavingPrompt, setIsSavingPrompt] = useState(false)
  
  // Memory 管理状态
  const [qaRecords, setQaRecords] = useState<any[]>([])
  const [selectedQA, setSelectedQA] = useState<any | null>(null)
  const [qaFilter, setQaFilter] = useState<'all' | 'correct' | 'incorrect' | 'unmarked'>('all')
  const [modelTypeFilter, setModelTypeFilter] = useState<'all' | 'vl' | 'llm'>('all')
  const [qaStats, setQaStats] = useState<any>(null)
  const [qaSearchQuery, setQaSearchQuery] = useState('')
  const [markingStatus, setMarkingStatus] = useState<'correct' | 'incorrect' | 'unmarked'>('correct')
  
  // LLM调试状态
  const [showDebugDialog, setShowDebugDialog] = useState(false)
  const [debugPrompt, setDebugPrompt] = useState('')
  const [debugResponse, setDebugResponse] = useState('')
  const [isDebugging, setIsDebugging] = useState(false)
  const [markReason, setMarkReason] = useState('')
  
  // 确保local状态与最新的config同步
  React.useEffect(() => {
    console.log('设置页面打开，当前配置:', config);
    setLocal(config);
    setModelList(config.models || []);
    setMcpList(config.mcpServers || []);
  }, [config]);

  // 监听语言变化，强制重新渲染
  React.useEffect(() => {
    const newLang = getCurrentLocale();
    if (newLang !== currentLang) {
      setCurrentLang(newLang);
      console.log('Settings drawer language changed to:', newLang);
    }
  }, [config.language]); // 监听config.language变化

  // 检查Agent服务状态
  const checkAgentServiceStatus = async () => {
    try {
      const status = await invoke<string>('agent_service_status')
      setAgentServiceStatus(status as 'running' | 'stopped')
    } catch (error) {
      console.error('Failed to check agent service status:', error)
      setAgentServiceStatus('stopped')
    }
  }

  // 启动Agent服务
  const startAgentService = async () => {
    if (isServiceOperating) return
    
    setIsServiceOperating(true)
    try {
      await invoke('agent_service_start')
      await checkAgentServiceStatus()
    } catch (error) {
      console.error('Failed to start agent service:', error)
    } finally {
      setIsServiceOperating(false)
    }
  }

  // 停止Agent服务
  const stopAgentService = async () => {
    if (isServiceOperating) return
    
    setIsServiceOperating(true)
    try {
      await invoke('agent_service_stop')
      await checkAgentServiceStatus()
    } catch (error) {
      console.error('Failed to stop agent service:', error)
    } finally {
      setIsServiceOperating(false)
    }
  }

  // 组件挂载时检查服务状态
  useEffect(() => {
    if (tab === 'python') {
      checkAgentServiceStatus()
      // 每5秒检查一次状态
      const interval = setInterval(checkAgentServiceStatus, 5000)
      return () => clearInterval(interval)
    }
  }, [tab])

  const getDirectoryPath = (fullPath: string) => {
    const lastSlash = Math.max(fullPath.lastIndexOf('/'), fullPath.lastIndexOf('\\'))
    return lastSlash > 0 ? fullPath.substring(0, lastSlash) : fullPath
  }

  const openLogDirectory = async () => {
    try {
      const p = await invoke<string>('get_log_path')
      const dir = getDirectoryPath(p)
      console.log('打开日志目录:', dir)
      // 使用 shell open 命令，更安全可靠
      await invoke('shell_open', { path: dir })
    } catch (error) {
      console.error('打开日志目录失败:', error)
      ui.toast('error', tf('settings.open_log_dir_failed', { error: String(error) }))
    }
  }

  const openConfigDirectory = async () => {
    try {
      const p = await invoke<string>('get_config_path')
      const dir = getDirectoryPath(p)
      console.log('打开配置目录:', dir)
      // 使用 shell open 命令，更安全可靠
      await invoke('shell_open', { path: dir })
    } catch (error) {
      console.error('打开配置目录失败:', error)
      ui.toast('error', tf('settings.open_config_dir_failed', { error: String(error) }))
    }
  }

  const saveSettings = async () => {
    try {
      const configToSave = { 
        ...local, 
        models: modelList, 
        mcpServers: mcpList,
        // 确保包含 embedding 和 rerank 服务配置
        embeddingUrl: local.embeddingUrl,
        embeddingModel: local.embeddingModel,
        embeddingApiKey: local.embeddingApiKey,
        rerankUrl: local.rerankUrl,
        rerankModel: local.rerankModel,
        rerankApiKey: local.rerankApiKey
      }
      console.log('保存前的配置:', configToSave)
      setConfig(configToSave)
      console.log('调用persist前...')
      await persist()
      console.log('persist完成，等待配置同步到其他窗口...')
      
      // 发送配置到YaoScope服务
      console.log('发送配置到YaoScope服务...')
      try {
        await invoke('update_python_service_config')
        console.log('✅ 配置已发送到YaoScope服务')
      } catch (error) {
        console.error('❌ 发送配置到YaoScope失败:', error)
        ui.toast('warning', tf('settings.config_saved_but_send_failed', { error: String(error) }))
      }
      
      // 等待500ms确保config-updated事件已经发送并被其他窗口接收
      await new Promise(resolve => setTimeout(resolve, 500))
      
      console.log('准备重启主窗口...')
      location.reload()
    } catch (error) {
      console.error('保存失败:', error)
      ui.toast('error', tf('settings.config_save_failed', { error: String(error) }))
    }
  }

  const refreshMCPTools = async (mcpConfig: MCPConfig) => {
    try {
      const { getMCPTools } = await import('../utils/proxy')
      const serverInfo = await getMCPTools(mcpConfig)
      
      // 更新配置中的MCP服务器信息
      const updatedConfig = {
        ...config,
        mcpServerInfos: {
          ...config.mcpServerInfos,
          [mcpConfig.id]: serverInfo
        }
      }
      setConfig(updatedConfig)
      
      console.log('MCP工具刷新成功:', serverInfo)
      ui.toast('success', tf('settings.mcp_refresh_success', { name: mcpConfig.name, count: serverInfo.tools?.length || 0 }))
    } catch (error) {
      console.error('刷新MCP工具失败:', error)
      ui.toast('error', tf('settings.mcp_refresh_failed', { error: String(error) }))
    }
  }

  // Task Flow 相关函数
  const fetchTaskFlows = async () => {
    try {
      const response = await fetch('http://127.0.0.1:8765/flows/list')
      const data = await response.json()
      if (data.success) {
        const flows = data.flows || []
        
        // 直接使用后端返回的数据，不再逐个验证
        // 后端已经从文件系统读取，确保数据真实存在
        setTaskFlows(flows)
        console.log(`Task Flows列表已更新，共 ${flows.length} 个流程`)
      }
    } catch (error) {
      console.error('获取任务流程列表失败:', error)
    }
  }

  const createNewPlan = async () => {
    if (!newPlanTask.trim()) {
      ui.toast('warning', t('settings.taskflow_task_required'))
      return
    }

    setIsCreatingPlan(true)
    try {
      const response = await fetch('http://127.0.0.1:8765/flows/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task_description: newPlanTask,
          app_name: newPlanApp
        })
      })

      const data = await response.json()
      if (data.success) {
        ui.toast('success', t('settings.taskflow_create_success'))
        setShowCreatePlanDialog(false)
        setNewPlanTask('')
        setNewPlanApp('')
        await fetchTaskFlows()
        // 自动加载新创建的 Plan
        await loadFlowDetails(data.flow_id)
      } else {
        ui.toast('error', t('settings.taskflow_create_failed') + ': ' + (data.error || 'Unknown error'))
      }
    } catch (error) {
      console.error('创建 Plan 失败:', error)
      ui.toast('error', t('settings.taskflow_create_failed') + ': ' + String(error))
    } finally {
      setIsCreatingPlan(false)
    }
  }

  const loadFlowDetails = async (flowId: string) => {
    try {
      const response = await fetch(`http://127.0.0.1:8765/flows/${flowId}`)
      const data = await response.json()
      if (data.success && data.flow) {
        setSelectedFlow(data.flow)
        setFlowJsonText(JSON.stringify(data.flow, null, 2))
        setJsonError(null)
      } else {
        // Flow不存在或已被删除，清空选中状态
        console.warn('Flow不存在或已被删除:', flowId)
        setSelectedFlow(null)
        setFlowJsonText('')
        ui.toast('error', t('settings.taskflow_load_failed') + ': ' + (data.error || 'Flow不存在'))
      }
    } catch (error) {
      console.error('加载任务流程详情失败:', error)
      setSelectedFlow(null)
      setFlowJsonText('')
      ui.toast('error', t('settings.taskflow_load_failed') + ': ' + String(error))
    }
  }

  const saveTaskFlow = async () => {
    if (!selectedFlow) return
    
    try {
      setIsSavingFlow(true)
      setJsonError(null)
      
      // 验证JSON格式
      const flowData = JSON.parse(flowJsonText)
      
      // 发送更新请求
      const response = await fetch(`http://127.0.0.1:8765/flows/${selectedFlow.flow_id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: flowJsonText
      })
      
      const result = await response.json()
      if (result.success) {
        ui.toast('success', t('settings.taskflow_save_success'))
        await fetchTaskFlows()
        await loadFlowDetails(selectedFlow.flow_id)
      } else {
        ui.toast('error', t('settings.taskflow_save_failed') + ': ' + result.error)
      }
    } catch (error: any) {
      console.error('保存任务流程失败:', error)
      if (error instanceof SyntaxError) {
        setJsonError(error.message)
      } else {
        ui.toast('error', t('settings.taskflow_save_failed') + ': ' + String(error))
      }
    } finally {
      setIsSavingFlow(false)
    }
  }

  const deleteTaskFlow = async (flowId: string) => {
    const ok = await ui.confirm({ title: t('common.confirm'), message: `${t('settings.taskflow_delete_confirm')} ${flowId}?` })
    if (!ok) {
      return
    }
    
    try {
      const response = await fetch(`http://127.0.0.1:8765/flows/${flowId}`, {
        method: 'DELETE'
      })
      
      const result = await response.json()
      if (result.success) {
        // 先清空选中状态
        if (selectedFlow?.flow_id === flowId) {
          setSelectedFlow(null)
          setFlowJsonText('')
        }
        
        // 立即从本地状态移除
        setTaskFlows(prev => prev.filter(flow => flow.flow_id !== flowId))
        
        ui.toast('success', t('settings.taskflow_delete_success'))
        
        // 再次刷新确保同步
        await fetchTaskFlows()
      } else {
        ui.toast('error', t('settings.taskflow_delete_failed') + ': ' + result.error)
      }
    } catch (error) {
      console.error('删除任务流程失败:', error)
      ui.toast('error', t('settings.taskflow_delete_failed') + ': ' + String(error))
    }
  }

  // Prompt 编辑相关函数
  const openEditPromptDialog = (step: any) => {
    setCurrentEditStep(step)
    setEditingPrompt(step.tool_input?.prompt || '')
    setShowEditPromptDialog(true)
  }

  const savePrompt = async () => {
    if (!selectedFlow || !currentEditStep) return

    setIsSavingPrompt(true)
    try {
      const response = await fetch(
        `http://127.0.0.1:8765/flows/${selectedFlow.flow_id}/steps/${currentEditStep.step_id}/prompt`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ new_prompt: editingPrompt })
        }
      )

      const data = await response.json()
      if (data.success) {
        ui.toast('success', t('settings.prompt_save_success'))
        setShowEditPromptDialog(false)
        await loadFlowDetails(selectedFlow.flow_id)
      } else {
        ui.toast('error', t('settings.prompt_save_failed') + ': ' + (data.error || 'Unknown error'))
      }
    } catch (error) {
      console.error('保存 Prompt 失败:', error)
      ui.toast('error', t('settings.prompt_save_failed') + ': ' + String(error))
    } finally {
      setIsSavingPrompt(false)
    }
  }

  const regeneratePrompt = async (step: any) => {
    if (!selectedFlow) return

    const additionalInstructions = await ui.prompt({
      title: t('settings.prompt_regenerate_title'),
      message: t('settings.prompt_regenerate_hint'),
      defaultValue: ''
    })
    if (additionalInstructions === null) return // 用户取消

    try {
      const response = await fetch(
        `http://127.0.0.1:8765/flows/${selectedFlow.flow_id}/steps/${step.step_id}/regenerate_prompt`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ additional_instructions: additionalInstructions || '' })
        }
      )

      const data = await response.json()
      if (data.success) {
        await ui.alert({ title: t('settings.prompt_regenerate_success'), message: data.new_prompt || '' })
        await loadFlowDetails(selectedFlow.flow_id)
      } else {
        ui.toast('error', t('settings.prompt_regenerate_failed') + ': ' + (data.error || 'Unknown error'))
      }
    } catch (error) {
      console.error('重新生成 Prompt 失败:', error)
      ui.toast('error', t('settings.prompt_regenerate_failed') + ': ' + String(error))
    }
  }

  const deleteStepAndReconstruct = async (stepId: number) => {
    if (!selectedFlow) return
    
    const ok = await ui.confirm({ title: t('common.confirm'), message: tf('settings.step_delete_confirm', { stepId }) })
    if (!ok) {
      return
    }
    
    try {
      const response = await fetch(
        `http://127.0.0.1:8765/flows/${selectedFlow.flow_id}/steps/${stepId}/delete_and_reconstruct`,
        { method: 'POST' }
      )
      
      const result = await response.json()
      if (result.success) {
        ui.toast('success', t('settings.step_deleted_plan_rebuilt'))
        await loadFlowDetails(selectedFlow.flow_id)
      } else {
        ui.toast('error', tf('settings.step_delete_failed', { error: String(result.error) }))
      }
    } catch (error) {
      console.error('删除步骤失败:', error)
      ui.toast('error', tf('settings.step_delete_failed', { error: String(error) }))
    }
  }

  // 监听 Task Flow 标签切换
  useEffect(() => {
    if (tab === 'taskflow') {
      fetchTaskFlows()
    }
  }, [tab])

  // Memory 相关函数
  const fetchQARecords = async () => {
    try {
      const statusParam = qaFilter === 'all' ? '' : `status=${qaFilter}&`
      const modelTypeParam = modelTypeFilter === 'all' ? '' : `model_type=${modelTypeFilter}&`
      const response = await fetch(`http://127.0.0.1:8765/llm_qa/list?${statusParam}${modelTypeParam}limit=100`)
      const data = await response.json()
      if (data.success) {
        setQaRecords(data.records || [])
      }
    } catch (error) {
      console.error('获取LLM问答记录失败:', error)
    }
  }

  const fetchQAStats = async () => {
    try {
      const response = await fetch('http://127.0.0.1:8765/llm_qa/statistics')
      const data = await response.json()
      if (data.success) {
        setQaStats(data.statistics)
      }
    } catch (error) {
      console.error('获取统计信息失败:', error)
    }
  }

  const loadQADetails = async (qaId: string) => {
    try {
      const response = await fetch(`http://127.0.0.1:8765/llm_qa/${qaId}`)
      const data = await response.json()
      if (data.success && data.record) {
        setSelectedQA(data.record)
        setMarkingStatus(data.record.status || 'unmarked')
        setMarkReason(data.record.mark_reason || '')
      }
    } catch (error) {
      console.error('加载问答详情失败:', error)
    }
  }

  const markQAStatus = async () => {
    if (!selectedQA) return
    
    try {
      const response = await fetch(`http://127.0.0.1:8765/llm_qa/${selectedQA.qa_id}/mark`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          status: markingStatus,
          reason: markReason || null
        })
      })
      
      const result = await response.json()
      if (result.success) {
        ui.toast('success', t('settings.mark_success'))
        await fetchQARecords()
        await fetchQAStats()
        await loadQADetails(selectedQA.qa_id)
      } else {
        ui.toast('error', tf('settings.mark_failed', { error: String(result.error) }))
      }
    } catch (error) {
      console.error('标记问答状态失败:', error)
      ui.toast('error', tf('settings.mark_failed', { error: String(error) }))
    }
  }

  // 打开LLM调试对话框
  const openDebugDialog = () => {
    if (selectedQA) {
      setDebugPrompt(selectedQA.prompt)
      setDebugResponse(selectedQA.response)
      setShowDebugDialog(true)
    }
  }

  // 执行LLM调试
  const runDebug = async () => {
    if (!debugPrompt.trim()) {
      ui.toast('warning', t('settings.debug_prompt_required'))
      return
    }

    setIsDebugging(true)
    try {
      const response = await fetch('http://127.0.0.1:8765/llm/debug', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: debugPrompt,
          model_type: selectedQA?.model_used || 'llm'
        })
      })

      const result = await response.json()
      if (result.success) {
        setDebugResponse(result.response)
      } else {
        ui.toast('error', t('settings.debug_failed') + ': ' + result.error)
      }
    } catch (error) {
      console.error('LLM调试失败:', error)
      ui.toast('error', t('settings.debug_failed') + ': ' + String(error))
    } finally {
      setIsDebugging(false)
    }
  }

  // 监听 Memory 标签切换
  useEffect(() => {
    if (tab === 'memory') {
      fetchQARecords()
      fetchQAStats()
    }
  }, [tab, qaFilter, modelTypeFilter])

  return (
    <>
      {/* 新建 Plan 对话框 */}
      {showCreatePlanDialog && (
        <div className="fixed inset-0 bg-black/50 z-[60] flex items-center justify-center">
          <div className="bg-white rounded-lg p-6 w-[600px] max-h-[80vh] overflow-auto">
            <div className="flex items-center justify-between mb-4">
              <div className="text-lg font-medium">{t('settings.taskflow_create')}</div>
              <button onClick={() => setShowCreatePlanDialog(false)} className="text-gray-500 hover:text-gray-700">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {t('settings.taskflow_task_desc')} <span className="text-red-500">*</span>
                </label>
                <textarea
                  value={newPlanTask}
                  onChange={(e) => setNewPlanTask(e.target.value)}
                  placeholder={t('settings.taskflow_task_placeholder')}
                  className="w-full h-32 p-3 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {t('settings.taskflow_app_name')} ({t('settings.optional')})
                </label>
                <input
                  type="text"
                  value={newPlanApp}
                  onChange={(e) => setNewPlanApp(e.target.value)}
                  placeholder={t('settings.taskflow_app_placeholder')}
                  className="w-full h-10 p-3 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 mt-6">
              <button
                onClick={() => setShowCreatePlanDialog(false)}
                className="px-4 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50"
              >
                {t('settings.cancel')}
              </button>
              <button
                onClick={createNewPlan}
                disabled={isCreatingPlan}
                className="px-4 py-2 text-sm bg-blue-500 text-white rounded hover:bg-blue-600 disabled:bg-gray-300"
              >
                {isCreatingPlan ? t('settings.taskflow_creating') : t('settings.taskflow_generate')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 编辑 Prompt 对话框 */}
      {showEditPromptDialog && currentEditStep && (
        <div className="fixed inset-0 bg-black/50 z-[60] flex items-center justify-center">
          <div className="bg-white rounded-lg p-6 w-[800px] max-h-[80vh] overflow-auto">
            <div className="flex items-center justify-between mb-4">
              <div className="text-lg font-medium">
                {t('settings.prompt_edit_title', { step_id: currentEditStep.step_id })}
              </div>
              <button onClick={() => setShowEditPromptDialog(false)} className="text-gray-500 hover:text-gray-700">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {t('settings.tool')}: {currentEditStep.tool}
                </label>
                <textarea
                  value={editingPrompt}
                  onChange={(e) => setEditingPrompt(e.target.value)}
                  placeholder={t('settings.prompt_placeholder')}
                  className="w-full h-64 p-3 border border-gray-300 rounded font-mono text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div className="p-3 bg-blue-50 border border-blue-200 rounded text-sm text-blue-800">
                💡 {t('settings.prompt_sync_hint')}
              </div>
            </div>

            <div className="flex justify-end gap-2 mt-6">
              <button
                onClick={() => setShowEditPromptDialog(false)}
                className="px-4 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50"
              >
                {t('settings.cancel')}
              </button>
              <button
                onClick={savePrompt}
                disabled={isSavingPrompt}
                className="px-4 py-2 text-sm bg-blue-500 text-white rounded hover:bg-blue-600 disabled:bg-gray-300"
              >
                {isSavingPrompt ? t('settings.saving') : t('settings.save')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* LLM调试对话框 */}
      {showDebugDialog && (
        <div className="fixed inset-0 bg-black/50 z-[60] flex items-center justify-center">
          <div className="bg-white rounded-lg p-6 w-[900px] max-h-[85vh] flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <div className="text-lg font-medium flex items-center gap-2">
                <svg className="w-5 h-5 text-purple-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                </svg>
                {t('settings.debug_title')}
              </div>
              <button onClick={() => setShowDebugDialog(false)} className="text-gray-500 hover:text-gray-700">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="flex-1 overflow-auto space-y-4">
              {/* Prompt (Q) - 可编辑 */}
              <div>
                <div className="text-sm font-medium text-gray-700 mb-2 flex items-center gap-2">
                  <span className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs font-bold">Q</span>
                  {t('settings.debug_prompt')}
                </div>
                <textarea
                  value={debugPrompt}
                  onChange={(e) => setDebugPrompt(e.target.value)}
                  placeholder={t('settings.debug_prompt_placeholder')}
                  className="w-full h-[200px] p-3 border border-gray-300 rounded text-sm font-mono resize-none focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>

              {/* Response (A) - 只读 */}
              <div>
                <div className="text-sm font-medium text-gray-700 mb-2 flex items-center gap-2">
                  <span className="px-2 py-0.5 bg-green-100 text-green-700 rounded text-xs font-bold">A</span>
                  {t('settings.debug_response')}
                </div>
                <div className="w-full min-h-[200px] p-3 bg-gray-50 border border-gray-200 rounded text-sm font-mono whitespace-pre-wrap">
                  {debugResponse || t('settings.debug_response_placeholder')}
                </div>
              </div>
            </div>

            <div className="flex justify-between items-center gap-2 mt-6 pt-4 border-t border-gray-200">
              <div className="text-xs text-gray-500">
                💡 {t('settings.debug_tip')}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setShowDebugDialog(false)}
                  className="px-4 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50"
                >
                  {t('settings.close')}
                </button>
                <button
                  onClick={runDebug}
                  disabled={isDebugging || !debugPrompt.trim()}
                  className="px-4 py-2 text-sm bg-purple-500 text-white rounded hover:bg-purple-600 disabled:bg-gray-300 flex items-center gap-2"
                >
                  {isDebugging ? (
                    <>
                      <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                      {t('settings.debug_generating')}
                    </>
                  ) : (
                    <>
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                      </svg>
                      {t('settings.debug_generate')}
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="fixed inset-0 bg-white z-50 flex">
      <div className="w-[240px] h-full border-r border-gray-200 p-4 flex flex-col gap-2 bg-gray-50">
        <div className="flex items-center justify-between mb-2">
          <div className="text-xs text-gray-500 px-1">{t('settings.title')}</div>
          <button className="text-gray-500 hover:text-gray-700 p-1" onClick={close}>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <button 
          className={`w-full h-10 rounded-lg text-left px-3 ${tab==='models'?'bg-gray-900 text-white':'bg-white text-gray-800 border border-gray-200'}`} 
          onClick={() => setTab('models')}
        >
          {t('settings.models')}
        </button>
        <button 
          className={`w-full h-10 rounded-lg text-left px-3 ${tab==='chat'?'bg-gray-900 text-white':'bg-white text-gray-800 border border-gray-200'}`} 
          onClick={() => setTab('chat')}
        >
          {t('settings.chat')}
        </button>
        <button 
          className={`w-full h-10 rounded-lg text-left px-3 ${tab==='mcp'?'bg-gray-900 text-white':'bg-white text-gray-800 border border-gray-200'}`} 
          onClick={() => setTab('mcp')}
        >
          {t('settings.mcp')}
        </button>
        <button 
          className={`w-full h-10 rounded-lg text-left px-3 ${tab==='python'?'bg-gray-900 text-white':'bg-white text-gray-800 border border-gray-200'}`} 
          onClick={() => setTab('python')}
        >
          {t('settings.python')}
        </button>
        <button 
          className={`w-full h-10 rounded-lg text-left px-3 ${tab==='taskflow'?'bg-gray-900 text-white':'bg-white text-gray-800 border border-gray-200'}`} 
          onClick={() => setTab('taskflow')}
        >
          {t('settings.taskflow')}
        </button>
        <button 
          className={`w-full h-10 rounded-lg text-left px-3 ${tab==='memory'?'bg-gray-900 text-white':'bg-white text-gray-800 border border-gray-200'}`} 
          onClick={() => setTab('memory')}
        >
          Memory
        </button>
        <div className="mt-auto text-[11px] text-gray-400 px-1">Yao Desktop</div>
      </div>
      
      <div className="flex-1 h-full flex flex-col">
        <div className="h-12 border-b border-gray-200 flex items-center justify-between px-4">
          <div className="text-sm text-gray-700">
            {tab === 'models' ? t('settings.models') : 
             tab === 'chat' ? t('settings.chat') : 
             tab === 'mcp' ? t('settings.mcp') : 
             tab === 'taskflow' ? t('settings.taskflow_title') :
             tab === 'memory' ? 'LLM Memory & Corrections' :
             t('settings.python')}
          </div>
        </div>
        
        <div className="flex-1 overflow-auto p-6">
          {tab === 'models' && (
            <div className="space-y-6 max-w-[760px]">
              <div className="space-y-2">
                <div className="text-sm text-gray-600">{t('settings.default_provider')}</div>
                <Dropdown 
                  value={local.provider} 
                  options={[{label:'openai',value:'openai'}]} 
                  onChange={(v) => setLocal({...local, provider: v as any})} 
                />
              </div>
              
              {/* 模型分类设置 */}
              <div className="border border-gray-200 rounded-lg p-4">
                <ModelCategorySettings
                  models={modelList}
                  vlModel={local.vlModel}
                  lightModel={local.lightModel}
                  advancedModel={local.advancedModel}
                  onVlModelChange={(model) => setLocal({...local, vlModel: model})}
                  onLightModelChange={(model) => setLocal({...local, lightModel: model})}
                  onAdvancedModelChange={(model) => setLocal({...local, advancedModel: model})}
                  language={currentLang}
                />
              </div>
              
              <div className="pt-2 text-sm text-gray-800">{t('settings.model_list')}</div>
              <div className="space-y-3">
                {modelList.map((m, idx) => (
                  <div key={idx} className="border border-gray-200 rounded-lg p-3 grid grid-cols-1 md:grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <div className="text-xs text-gray-500">{t('settings.name')}</div>
                      <input 
                        className="input h-10 w-full" 
                        value={m.name} 
                        onChange={(e) => {
                          const next = [...modelList]
                          next[idx] = {...m, name: e.target.value}
                          setModelList(next)
                        }} 
                      />
                    </div>
                    <div className="space-y-1">
                      <div className="text-xs text-gray-500">Provider</div>
                      <Dropdown 
                        value={m.provider} 
                        options={[{label:'openai',value:'openai'}]} 
                        onChange={(v) => {
                          const next = [...modelList]
                          next[idx] = {...m, provider: v as any}
                          setModelList(next)
                        }} 
                      />
                    </div>
                    <div className="space-y-1">
                      <div className="text-xs text-gray-500">{currentLang === 'zh-CN' ? '模型分类' : 'Category'}</div>
                      <Dropdown 
                        value={m.category || ''} 
                        options={[
                          {label: currentLang === 'zh-CN' ? '未分类' : 'Uncategorized', value: ''},
                          {label: currentLang === 'zh-CN' ? 'VL模型（多模态）' : 'VL Model (Multimodal)', value: 'vl'},
                          {label: currentLang === 'zh-CN' ? '轻量模型' : 'Light Model', value: 'light'},
                          {label: currentLang === 'zh-CN' ? '高级模型' : 'Advanced Model', value: 'advanced'}
                        ]} 
                        onChange={(v) => {
                          const next = [...modelList]
                          next[idx] = {...m, category: v as ModelCategory}
                          setModelList(next)
                        }} 
                      />
                    </div>
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <input 
                          type="checkbox" 
                          checked={!!m.supportsVision} 
                          onChange={(e) => {
                            const next = [...modelList]
                            next[idx] = {...m, supportsVision: e.target.checked}
                            setModelList(next)
                          }} 
                        />
                        <span className="text-xs text-gray-500">
                          {currentLang === 'zh-CN' ? '支持图像识别' : 'Supports Vision'}
                        </span>
                      </div>
                    </div>
                    <div className="space-y-1 md:col-span-2">
                      <div className="text-xs text-gray-500">Base URL</div>
                      <input 
                        className="input h-10 w-full" 
                        placeholder={t('settings.base_url_placeholder')} 
                        value={m.baseUrl || ''} 
                        onChange={(e) => {
                          const next = [...modelList]
                          next[idx] = {...m, baseUrl: e.target.value}
                          setModelList(next)
                        }} 
                      />
                    </div>
                    {m.provider === 'openai' && (
                      <div className="space-y-1 md:col-span-2">
                        <div className="text-xs text-gray-500">API Key</div>
                        <input 
                          className="input h-10 w-full" 
                          placeholder={t('settings.api_key_placeholder')} 
                          value={m.apiKey || ''} 
                          onChange={(e) => {
                            const next = [...modelList]
                            next[idx] = {...m, apiKey: e.target.value}
                            setModelList(next)
                          }} 
                        />
                      </div>
                    )}
                    <div className="md:col-span-2 flex justify-end">
                      <button 
                        className="btn h-9 px-3" 
                        onClick={() => {
                          const next = [...modelList]
                          next.splice(idx, 1)
                          setModelList(next)
                        }}
                      >
                        {t('settings.delete')}
                      </button>
                    </div>
                  </div>
                ))}
                <button 
                  className="btn h-10 px-3" 
                  onClick={() => setModelList([
                    ...(modelList || []), 
                    { 
                      name: 'gpt-3.5-turbo', 
                      provider: 'openai', 
                      baseUrl: 'https://api.openai.com/v1',
                      category: 'light',
                      supportsVision: false
                    }
                  ])}
                >
                  {t('settings.add_model')}
                </button>
              </div>
            </div>
          )}
          
          {tab === 'chat' && (
            <div className="space-y-6 max-w-[760px]">
              <div className="text-sm text-gray-600">{t('settings.chat')}</div>
              <div className="space-y-2">
                <label className="flex items-center gap-2 text-sm text-gray-700">
                  <input 
                    type="checkbox" 
                    checked={!!local.streamingEnabled} 
                    onChange={(e) => setLocal({ ...local, streamingEnabled: e.target.checked })} 
                  />
                  {t('settings.streaming_enabled')}
                </label>
                <label className="flex items-center gap-2 text-sm text-gray-700">
                  <input 
                    type="checkbox" 
                    checked={!!local.defaultThink} 
                    onChange={(e) => setLocal({ ...local, defaultThink: e.target.checked })} 
                  />
                  {t('settings.default_think')}
                </label>
                <div className="space-y-1">
                  <div className="text-sm text-gray-600">{t('settings.max_context_messages')}</div>
                  <input 
                    type="number" 
                    min={0} 
                    className="input w-[160px]" 
                    value={local.maxContextMessages ?? 20} 
                    onChange={(e) => setLocal({ ...local, maxContextMessages: Number(e.target.value) || 0 })} 
                  />
                </div>
                <div className="space-y-1">
                  <div className="text-sm text-gray-600">{t('settings.temperature')}</div>
                  <input 
                    type="number" 
                    min={0} 
                    max={2} 
                    step={0.1} 
                    className="input w-[160px]" 
                    value={local.temperature ?? 0.6} 
                    onChange={(e) => setLocal({ ...local, temperature: Number(e.target.value) || 0.6 })} 
                  />
                  <div className="text-xs text-gray-500">{t('settings.temperature_desc')}</div>
                </div>
              </div>
            </div>
          )}
          
          {tab === 'mcp' && (
            <div className="space-y-6 max-w-[760px]">
              {/* MCP全局设置 */}
              <div className="border border-gray-200 rounded-lg p-4 space-y-4">
                <div className="text-sm font-medium text-gray-700">{t('settings.mcp_global_settings')}</div>
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <div className="text-xs text-gray-500">{t('settings.mcp_max_retries')}</div>
                    <input 
                      type="number"
                      min="1"
                      max="10"
                      className="input h-10 w-full" 
                      value={local.mcpMaxRetries || 3}
                      onChange={(e) => setLocal({...local, mcpMaxRetries: parseInt(e.target.value) || 3})}
                    />
                  </div>
                  
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <input 
                        type="checkbox" 
                        checked={local.mcpReflectionEnabled ?? true}
                        onChange={(e) => setLocal({...local, mcpReflectionEnabled: e.target.checked})}
                      />
                      <span className="text-xs text-gray-500">{t('settings.mcp_reflection_enabled')}</span>
                    </div>
                  </div>
                </div>
              </div>
              
              <div className="text-sm text-gray-600">{t('settings.mcp_servers')}</div>
              <div className="space-y-3">
                {mcpList.map((mcp, idx) => (
                  <div key={idx} className="border border-gray-200 rounded-lg p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <input 
                          type="checkbox" 
                          checked={mcp.enabled} 
                          onChange={(e) => {
                            const next = [...mcpList]
                            next[idx] = {...mcp, enabled: e.target.checked}
                            setMcpList(next)
                          }} 
                        />
                        <span className="text-sm font-medium">{t('settings.mcp_enabled')}</span>
                      </div>
                      <div className="flex gap-2">
                        <button 
                          className="btn h-9 px-3 text-sm" 
                          onClick={() => refreshMCPTools(mcp)}
                          disabled={!mcp.enabled}
                        >
                          {t('settings.refresh_tools')}
                        </button>
                        <button 
                          className="btn h-9 px-3" 
                          onClick={() => {
                            const next = [...mcpList]
                            next.splice(idx, 1)
                            setMcpList(next)
                          }}
                        >
                          {t('settings.delete')}
                        </button>
                      </div>
                    </div>
                    
                    <div className="space-y-1">
                      <div className="text-xs text-gray-500">{t('settings.mcp_name')}</div>
                      <input 
                        className="input h-10 w-full" 
                        value={mcp.name} 
                        onChange={(e) => {
                          const next = [...mcpList]
                          next[idx] = {...mcp, name: e.target.value}
                          setMcpList(next)
                        }} 
                      />
                    </div>
                    
                    <div className="space-y-1">
                      <div className="text-xs text-gray-500">{t('settings.mcp_json_config')}</div>
                      <textarea 
                        className="input w-full min-h-[120px] font-mono text-sm" 
                        placeholder={t('settings.mcp_json_placeholder')} 
                        value={JSON.stringify({
                          command: mcp.command,
                          args: mcp.args || [],
                          env: mcp.env || {}
                        }, null, 2)} 
                        onChange={(e) => {
                          try {
                            const config = JSON.parse(e.target.value)
                            const next = [...mcpList]
                            next[idx] = {
                              ...mcp,
                              command: config.command || '',
                              args: config.args || [],
                              env: config.env || {}
                            }
                            setMcpList(next)
                          } catch (error) {
                            // 忽略JSON解析错误，让用户继续编辑
                          }
                        }} 
                      />
                    </div>
                    
                    <div className="space-y-1">
                      <div className="text-xs text-gray-500">{t('settings.mcp_description')}</div>
                      <input 
                        className="input h-10 w-full" 
                        placeholder={t('settings.mcp_description_placeholder')} 
                        value={mcp.description || ''} 
                        onChange={(e) => {
                          const next = [...mcpList]
                          next[idx] = {...mcp, description: e.target.value}
                          setMcpList(next)
                        }} 
                      />
                    </div>
                    
                    {/* 显示工具列表 */}
                    {config.mcpServerInfos?.[mcp.id]?.tools && config.mcpServerInfos[mcp.id].tools!.length > 0 && (
                      <div className="space-y-1">
                        <div className="text-xs text-gray-500">{t('settings.available_tools')} ({config.mcpServerInfos[mcp.id].tools!.length})</div>
                        <div className="max-h-32 overflow-y-auto bg-gray-50 rounded p-2">
                          {config.mcpServerInfos[mcp.id].tools!.map((tool, toolIdx) => (
                            <div key={toolIdx} className="text-xs text-gray-700 py-1 border-b border-gray-200 last:border-b-0">
                              <div className="font-medium">{tool.name}</div>
                              {tool.description && (
                                <div className="text-gray-500 mt-1">{tool.description}</div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
                <div className="flex gap-2">
                  <button 
                    className="btn h-10 px-3" 
                    onClick={() => setMcpList([
                      ...mcpList, 
                      { 
                        id: `mcp-${Date.now()}`, 
                        name: 'New MCP Server', 
                        command: '', 
                        args: [],
                        env: {},
                        enabled: true 
                      }
                    ])}
                  >
                    {t('settings.add_mcp')}
                  </button>
                  <button 
                    className="btn h-10 px-3" 
                    onClick={() => setMcpList([
                      ...mcpList, 
                      { 
                        id: 'excel-mcp',
                        name: 'Excel MCP Server', 
                        command: 'powershell',
                        args: ['-Command', 'npx --yes @negokaz/excel-mcp-server'],
                        env: {
                          'EXCEL_MCP_PAGING_CELLS_LIMIT': '4000'
                        },
                        enabled: true,
                        description: 'MCP server for Excel file operations'
                      }
                    ])}
                  >
                    {t('settings.add_excel_mcp')}
                  </button>
                </div>
              </div>
            </div>
          )}
          
          {tab === 'python' && (
            <div className="space-y-6 max-w-[760px]">
              <div className="text-sm text-gray-600">{t('settings.python')}</div>
              
              <div className="space-y-4">
                {/* Agent服务控制 */}
                <div className="space-y-4 p-4 border border-gray-200 rounded-lg">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-sm font-medium text-gray-700">{t('settings.python_service')}</div>
                      <div className="text-xs text-gray-500">{t('settings.python_service_desc')}</div>
                    </div>
                    <div className="flex items-center space-x-3">
                      {/* 服务状态指示器 */}
                      <div className="flex items-center space-x-2">
                        <div className={`w-2 h-2 rounded-full ${
                          agentServiceStatus === 'running' ? 'bg-green-500' : 
                          agentServiceStatus === 'stopped' ? 'bg-red-500' : 
                          'bg-yellow-500 animate-pulse'
                        }`}></div>
                        <span className="text-xs text-gray-600">
                          {agentServiceStatus === 'running' ? t('settings.python_service_running') :
                           agentServiceStatus === 'stopped' ? t('settings.python_service_stopped') :
                           t('settings.python_service_checking')}
                        </span>
                      </div>
                    </div>
                  </div>
                  
                  {/* 控制按钮 */}
                  <div className="flex space-x-2">
                    <button
                      onClick={startAgentService}
                      disabled={isServiceOperating || agentServiceStatus === 'running'}
                      className={`px-4 py-2 text-sm rounded-lg transition-colors ${
                        isServiceOperating || agentServiceStatus === 'running'
                          ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                          : 'bg-green-500 text-white hover:bg-green-600'
                      }`}
                    >
                      {isServiceOperating ? '启动中...' : t('settings.python_service_start')}
                    </button>
                    
                    <button
                      onClick={stopAgentService}
                      disabled={isServiceOperating || agentServiceStatus === 'stopped'}
                      className={`px-4 py-2 text-sm rounded-lg transition-colors ${
                        isServiceOperating || agentServiceStatus === 'stopped'
                          ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                          : 'bg-red-500 text-white hover:bg-red-600'
                      }`}
                    >
                      {isServiceOperating ? '停止中...' : t('settings.python_service_stop')}
                    </button>
                    
                    <button
                      onClick={checkAgentServiceStatus}
                      disabled={isServiceOperating}
                      className="px-4 py-2 text-sm rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 transition-colors"
                    >
                      刷新状态
                    </button>
                  </div>
                </div>
                
                {/* Embedding模型配置 */}
                <div className="space-y-4 p-4 bg-gray-50 rounded-lg">
                  <div className="text-sm font-medium text-gray-700">Embedding 模型配置</div>
                  
                  {/* Embedding API URL */}
                  <div className="space-y-2">
                    <div className="text-sm text-gray-600">API 地址</div>
                    <input 
                      type="text"
                      className="input w-full" 
                      placeholder="https://api.siliconflow.cn/v1/embeddings"
                      value={local.embeddingUrl || ''} 
                      onChange={(e) => {
                        console.log('Embedding URL changed:', e.target.value);
                        setLocal({ ...local, embeddingUrl: e.target.value });
                      }} 
                    />
                    <div className="text-xs text-gray-500">Embedding 服务的 API 地址</div>
                  </div>
                  
                  {/* Embedding Model */}
                  <div className="space-y-2">
                    <div className="text-sm text-gray-600">模型名称</div>
                    <input 
                      type="text"
                      className="input w-full" 
                      placeholder="BAAI/bge-m3"
                      value={local.embeddingModel || ''} 
                      onChange={(e) => {
                        console.log('Embedding Model changed:', e.target.value);
                        setLocal({ ...local, embeddingModel: e.target.value });
                      }} 
                    />
                    <div className="text-xs text-gray-500">Embedding 模型的名称</div>
                  </div>
                  
                  {/* Embedding API Key */}
                  <div className="space-y-2">
                    <div className="text-sm text-gray-600">API Key</div>
                    <input 
                      type="password"
                      className="input w-full" 
                      placeholder="sk-..."
                      value={local.embeddingApiKey || ''} 
                      onChange={(e) => {
                        console.log('Embedding API Key changed:', e.target.value);
                        setLocal({ ...local, embeddingApiKey: e.target.value });
                      }} 
                    />
                    <div className="text-xs text-gray-500">Embedding 服务的 API 密钥</div>
                  </div>
                </div>
                
                {/* Rerank模型配置 */}
                <div className="space-y-4 p-4 bg-gray-50 rounded-lg">
                  <div className="text-sm font-medium text-gray-700">Rerank 模型配置</div>
                  
                  {/* Rerank API URL */}
                  <div className="space-y-2">
                    <div className="text-sm text-gray-600">API 地址</div>
                    <input 
                      type="text"
                      className="input w-full" 
                      placeholder="https://api.siliconflow.cn/v1/rerank"
                      value={local.rerankUrl || ''} 
                      onChange={(e) => {
                        console.log('Rerank URL changed:', e.target.value);
                        setLocal({ ...local, rerankUrl: e.target.value });
                      }} 
                    />
                    <div className="text-xs text-gray-500">Rerank 服务的 API 地址</div>
                  </div>
                  
                  {/* Rerank Model */}
                  <div className="space-y-2">
                    <div className="text-sm text-gray-600">模型名称</div>
                    <input 
                      type="text"
                      className="input w-full" 
                      placeholder="BAAI/bge-reranker-v2-m3"
                      value={local.rerankModel || ''} 
                      onChange={(e) => {
                        console.log('Rerank Model changed:', e.target.value);
                        setLocal({ ...local, rerankModel: e.target.value });
                      }} 
                    />
                    <div className="text-xs text-gray-500">Rerank 模型的名称</div>
                  </div>
                  
                  {/* Rerank API Key */}
                  <div className="space-y-2">
                    <div className="text-sm text-gray-600">API Key</div>
                    <input 
                      type="password"
                      className="input w-full" 
                      placeholder="sk-..."
                      value={local.rerankApiKey || ''} 
                      onChange={(e) => {
                        console.log('Rerank API Key changed:', e.target.value);
                        setLocal({ ...local, rerankApiKey: e.target.value });
                      }} 
                    />
                    <div className="text-xs text-gray-500">Rerank 服务的 API 密钥</div>
                  </div>
                </div>
              </div>
            </div>
          )}
          
          {tab === 'taskflow' && (
            <div className="flex gap-4 h-full max-w-full">
              {/* 左侧：任务流程列表 */}
              <div className="w-[300px] border-r border-gray-200 pr-4 flex flex-col">
                <div className="flex items-center justify-between mb-4">
                  <div className="text-sm font-medium text-gray-700">
                    {t('settings.taskflow_list')}
                  </div>
                  <div className="flex gap-2">
                    <button 
                      onClick={() => setShowCreatePlanDialog(true)}
                      className="text-xs px-3 py-1 rounded bg-blue-500 text-white hover:bg-blue-600 transition-colors"
                    >
                      + {t('settings.taskflow_create')}
                    </button>
                    <button 
                      onClick={fetchTaskFlows}
                      className="text-xs px-2 py-1 rounded border border-gray-300 hover:bg-gray-50"
                    >
                      {t('settings.taskflow_refresh')}
                    </button>
                  </div>
                </div>
                
                <div className="flex-1 overflow-y-auto space-y-2">
                  {taskFlows.length === 0 ? (
                    <div className="text-xs text-gray-400 text-center py-8">
                      {t('settings.taskflow_empty')}
                    </div>
                  ) : (
                    taskFlows.map(flow => (
                      <div
                        key={flow.flow_id}
                        onClick={() => loadFlowDetails(flow.flow_id)}
                        className={`p-3 border rounded-lg cursor-pointer transition-colors ${
                          selectedFlow?.flow_id === flow.flow_id
                            ? 'border-blue-500 bg-blue-50'
                            : 'border-gray-200 hover:bg-gray-50'
                        }`}
                      >
                        <div className="text-sm font-medium text-gray-800 truncate">
                          {flow.app_name}
                        </div>
                        <div className="text-xs text-gray-500 mt-1 line-clamp-2">
                          {flow.original_query}
                        </div>
                        <div className="flex items-center justify-between mt-2">
                          <span className="text-xs text-gray-400">
                            {flow.steps_count} steps
                          </span>
                          <span className="text-xs text-gray-400">
                            {flow.created_at ? new Date(flow.created_at).toLocaleString('zh-CN', {
                              month: 'numeric',
                              day: 'numeric',
                              hour: '2-digit',
                              minute: '2-digit'
                            }) : ''}
                          </span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
              
              {/* 右侧：步骤预览和JSON编辑器 */}
              <div className="flex-1 flex flex-col">
                {selectedFlow ? (
                  <>
                    <div className="flex items-center justify-between mb-4">
                      <div>
                        <div className="text-sm font-medium text-gray-700">
                          {selectedFlow.flow_id}
                        </div>
                        <div className="text-xs text-gray-500 mt-1">
                          {selectedFlow.app_name || 'Unknown App'} - {selectedFlow.steps?.length || 0} {t('settings.taskflow_steps')}
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <button
                          onClick={saveTaskFlow}
                          disabled={isSavingFlow}
                          className="px-4 py-2 text-sm rounded-lg bg-blue-500 text-white hover:bg-blue-600 disabled:bg-gray-300"
                        >
                          {isSavingFlow ? t('settings.taskflow_saving') : t('settings.taskflow_save')}
                        </button>
                        <button
                          onClick={() => deleteTaskFlow(selectedFlow.flow_id)}
                          className="px-4 py-2 text-sm rounded-lg border border-red-500 text-red-500 hover:bg-red-50"
                        >
                          {t('settings.taskflow_delete')}
                        </button>
                      </div>
                    </div>

                    {/* 步骤预览（带 Prompt 编辑按钮） */}
                    <div className="mb-4 border border-gray-200 rounded-lg p-4 max-h-[300px] overflow-y-auto">
                      <div className="text-xs font-medium text-gray-700 mb-3">{t('settings.taskflow_steps_preview')}</div>
                      <div className="space-y-3">
                        {selectedFlow.steps?.map((step: any) => (
                          <div key={step.step_id} className="border-l-2 border-blue-400 pl-3 pb-3">
                            <div className="flex items-start justify-between">
                              <div className="flex-1">
                                <div className="text-sm font-medium text-gray-800">
                                  {t('settings.taskflow_step')} {step.step_id}: {step.tool}
                                </div>
                                {step.description && (
                                  <div className="text-xs text-gray-600 mt-1">{step.description}</div>
                                )}
                                {step.tool_input?.prompt && (
                                  <div className="mt-2 text-xs text-gray-500 bg-gray-50 p-2 rounded border border-gray-200">
                                    <span className="font-medium">Prompt:</span> {step.tool_input.prompt.substring(0, 100)}...
                                  </div>
                                )}
                              </div>
                              <div className="flex gap-1 ml-2">
                                {step.tool_input?.prompt && (
                                  <>
                                    <button
                                      onClick={() => openEditPromptDialog(step)}
                                      className="px-2 py-1 text-xs rounded border border-gray-300 hover:bg-gray-50 transition-colors"
                                      title={t('settings.prompt_edit')}
                                    >
                                      ✏️ {t('settings.prompt_edit')}
                                    </button>
                                    <button
                                      onClick={() => regeneratePrompt(step)}
                                      className="px-2 py-1 text-xs rounded border border-gray-300 hover:bg-gray-50 transition-colors"
                                      title={t('settings.prompt_regenerate')}
                                    >
                                      🔄 {t('settings.prompt_regenerate')}
                                    </button>
                                  </>
                                )}
                                <button
                                  onClick={() => deleteStepAndReconstruct(step.step_id)}
                                  className="px-2 py-1 text-xs rounded border border-red-300 text-red-600 hover:bg-red-50 transition-colors"
                                  title="删除步骤"
                                >
                                  🗑️ 删除
                                </button>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* JSON 编辑区标题 */}
                    <div className="text-xs font-medium text-gray-700 mb-2">
                      {t('settings.taskflow_json_editor')}
                    </div>
                    
                    {jsonError && (
                      <div className="mb-2 p-2 bg-red-50 border border-red-200 rounded text-xs text-red-600">
                        {t('settings.taskflow_json_error')}: {jsonError}
                      </div>
                    )}
                    
                    <textarea
                      value={flowJsonText}
                      onChange={(e) => {
                        setFlowJsonText(e.target.value)
                        setJsonError(null)
                      }}
                      className="flex-1 font-mono text-xs border border-gray-300 rounded-lg p-4 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                      spellCheck={false}
                    />
                    
                    <div className="mt-2 text-xs text-gray-500">
                      {t('settings.taskflow_edit_hint')}
                    </div>
                  </>
                ) : (
                  <div className="flex-1 flex items-center justify-center text-gray-400">
                    <div className="text-center">
                      <svg className="w-16 h-16 mx-auto mb-4 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                      <div className="text-sm">
                        {t('settings.taskflow_select_hint')}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {tab === 'memory' && (
            <div className="flex gap-4 h-full max-w-full">
              {/* 左侧：统计和过滤 */}
              <div className="w-[280px] border-r border-gray-200 pr-4 flex flex-col">
                {/* 统计信息 */}
                {qaStats && (
                  <div className="mb-4 p-3 bg-gray-50 rounded-lg border border-gray-200">
                    <div className="text-xs font-medium text-gray-700 mb-2">Statistics</div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div>
                        <span className="text-gray-500">Total:</span>
                        <span className="ml-1 font-medium">{qaStats.total}</span>
                      </div>
                      <div>
                        <span className="text-gray-500">Rate:</span>
                        <span className="ml-1 font-medium text-green-600">{qaStats.correct_rate}</span>
                      </div>
                      <div>
                        <span className="text-gray-500">✅ Correct:</span>
                        <span className="ml-1 font-medium">{qaStats.correct}</span>
                      </div>
                      <div>
                        <span className="text-gray-500">❌ Incorrect:</span>
                        <span className="ml-1 font-medium">{qaStats.incorrect}</span>
                      </div>
                      <div>
                        <span className="text-gray-500">⚪ Unmarked:</span>
                        <span className="ml-1 font-medium">{qaStats.unmarked}</span>
                      </div>
                      <div>
                        <span className="text-gray-500">Light:</span>
                        <span className="ml-1 font-medium">{qaStats.light_model_usage}</span>
                      </div>
                      <div>
                        <span className="text-gray-500">🖼️ VL:</span>
                        <span className="ml-1 font-medium">{qaStats.vl_count || 0}</span>
                      </div>
                      <div>
                        <span className="text-gray-500">💬 LLM:</span>
                        <span className="ml-1 font-medium">{qaStats.llm_count || 0}</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* 过滤器 */}
                <div className="mb-4">
                  <div className="text-xs font-medium text-gray-700 mb-2">Status Filter</div>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      onClick={() => setQaFilter('all')}
                      className={`px-3 py-2 text-xs rounded ${qaFilter === 'all' ? 'bg-blue-500 text-white' : 'bg-white border border-gray-200'}`}
                    >
                      All
                    </button>
                    <button
                      onClick={() => setQaFilter('correct')}
                      className={`px-3 py-2 text-xs rounded ${qaFilter === 'correct' ? 'bg-green-500 text-white' : 'bg-white border border-gray-200'}`}
                    >
                      ✅ Correct
                    </button>
                    <button
                      onClick={() => setQaFilter('incorrect')}
                      className={`px-3 py-2 text-xs rounded ${qaFilter === 'incorrect' ? 'bg-red-500 text-white' : 'bg-white border border-gray-200'}`}
                    >
                      ❌ Incorrect
                    </button>
                    <button
                      onClick={() => setQaFilter('unmarked')}
                      className={`px-3 py-2 text-xs rounded ${qaFilter === 'unmarked' ? 'bg-gray-500 text-white' : 'bg-white border border-gray-200'}`}
                    >
                      ⚪ Unmarked
                    </button>
                  </div>
                </div>

                {/* Model Type 过滤器 */}
                <div className="mb-4">
                  <div className="text-xs font-medium text-gray-700 mb-2">Model Type</div>
                  <div className="grid grid-cols-3 gap-2">
                    <button
                      onClick={() => setModelTypeFilter('all')}
                      className={`px-3 py-2 text-xs rounded ${modelTypeFilter === 'all' ? 'bg-blue-500 text-white' : 'bg-white border border-gray-200'}`}
                    >
                      All
                    </button>
                    <button
                      onClick={() => setModelTypeFilter('vl')}
                      className={`px-3 py-2 text-xs rounded ${modelTypeFilter === 'vl' ? 'bg-purple-500 text-white' : 'bg-white border border-gray-200'}`}
                    >
                      🖼️ VL
                    </button>
                    <button
                      onClick={() => setModelTypeFilter('llm')}
                      className={`px-3 py-2 text-xs rounded ${modelTypeFilter === 'llm' ? 'bg-indigo-500 text-white' : 'bg-white border border-gray-200'}`}
                    >
                      💬 LLM
                    </button>
                  </div>
                </div>

                {/* 记录列表 */}
                <div className="flex-1 overflow-auto">
                  <div className="text-xs font-medium text-gray-700 mb-2">
                    QA Records ({qaRecords.length})
                  </div>
                  {qaRecords.length === 0 ? (
                    <div className="text-xs text-gray-400 text-center py-8">
                      No records found
                    </div>
                  ) : (
                    qaRecords.map((record) => (
                      <div
                        key={record.qa_id}
                        onClick={() => loadQADetails(record.qa_id)}
                        className={`p-2 mb-2 border rounded cursor-pointer hover:bg-gray-50 ${
                          selectedQA?.qa_id === record.qa_id ? 'border-blue-500 bg-blue-50' : 'border-gray-200'
                        }`}
                      >
                        <div className="text-xs truncate font-medium text-gray-800 mb-1">
                          {record.prompt_preview}
                        </div>
                        <div className="flex items-center justify-between text-[10px] text-gray-500">
                          <span className={`px-1.5 py-0.5 rounded ${
                            record.status === 'correct' ? 'bg-green-100 text-green-700' :
                            record.status === 'incorrect' ? 'bg-red-100 text-red-700' :
                            'bg-gray-100 text-gray-700'
                          }`}>
                            {record.model_used}
                          </span>
                          <span>{new Date(record.created_at).toLocaleString('zh-CN', {month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'})}</span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* 右侧：详情面板 */}
              <div className="flex-1 flex flex-col">
                {selectedQA ? (
                  <>
                    <div className="mb-4">
                      <div className="text-sm font-medium text-gray-700 mb-2">QA ID: {selectedQA.qa_id}</div>
                      <div className="text-xs text-gray-500">
                        Created: {new Date(selectedQA.created_at).toLocaleString('zh-CN')}
                        {selectedQA.task_id && ` | Task: ${selectedQA.task_id}`}
                      </div>
                    </div>

                    <div className="flex-1 overflow-auto space-y-4">
                      {/* Prompt */}
                      <div>
                        <div className="text-xs font-medium text-gray-700 mb-2">Prompt</div>
                        <div className="p-3 bg-gray-50 border border-gray-200 rounded text-xs whitespace-pre-wrap max-h-[200px] overflow-auto">
                          {selectedQA.prompt}
                        </div>
                      </div>

                      {/* Response */}
                      <div>
                        <div className="text-xs font-medium text-gray-700 mb-2">Response</div>
                        <div className="p-3 bg-gray-50 border border-gray-200 rounded text-xs whitespace-pre-wrap max-h-[200px] overflow-auto">
                          {selectedQA.response}
                        </div>
                      </div>

                      {/* 状态标记 */}
                      <div>
                        <div className="text-xs font-medium text-gray-700 mb-2">Mark Status</div>
                        <div className="flex gap-3">
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input
                              type="radio"
                              name="status"
                              value="correct"
                              checked={markingStatus === 'correct'}
                              onChange={() => setMarkingStatus('correct')}
                              className="w-4 h-4 text-green-600 focus:ring-green-500"
                            />
                            <span className="text-sm">Correct</span>
                          </label>
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input
                              type="radio"
                              name="status"
                              value="incorrect"
                              checked={markingStatus === 'incorrect'}
                              onChange={() => setMarkingStatus('incorrect')}
                              className="w-4 h-4 text-red-600 focus:ring-red-500"
                            />
                            <span className="text-sm">Incorrect</span>
                          </label>
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input
                              type="radio"
                              name="status"
                              value="unmarked"
                              checked={markingStatus === 'unmarked'}
                              onChange={() => setMarkingStatus('unmarked')}
                              className="w-4 h-4 text-gray-600 focus:ring-gray-500"
                            />
                            <span className="text-sm">Unmarked</span>
                          </label>
                        </div>
                      </div>

                      {/* 纠错信息（仅在标记为incorrect时显示） */}
                      {markingStatus === 'incorrect' && (
                        <div>
                          <div className="text-xs font-medium text-gray-700 mb-2">
                            Correction Info <span className="text-red-500">*</span>
                          </div>
                          <textarea
                            value={markReason}
                            onChange={(e) => setMarkReason(e.target.value)}
                            placeholder="请输入纠错信息，例如：应该使用expand_content工具而不是generate_reply..."
                            className="w-full h-24 p-3 border border-gray-300 rounded text-xs resize-none focus:outline-none focus:border-blue-500"
                          />
                          <div className="text-xs text-gray-500 mt-1">
                            💡 纠错信息将自动注入到相似问题的prompt中，帮助LLM避免重复错误
                          </div>
                        </div>
                      )}

                      {/* 保存按钮 */}
                      <div className="flex gap-2">
                        <button
                          onClick={markQAStatus}
                          className="px-4 py-2 text-sm rounded-lg bg-blue-500 text-white hover:bg-blue-600"
                        >
                          Save Mark
                        </button>
                        <button
                          onClick={openDebugDialog}
                          className="px-4 py-2 text-sm rounded-lg bg-purple-500 text-white hover:bg-purple-600 flex items-center gap-1"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                          </svg>
                          {t('settings.debug')}
                        </button>
                        <button
                          onClick={() => setSelectedQA(null)}
                          className="px-4 py-2 text-sm rounded-lg border border-gray-300 hover:bg-gray-50"
                        >
                          Close
                        </button>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="flex-1 flex items-center justify-center">
                    <div className="text-center text-gray-400">
                      <svg className="w-16 h-16 mx-auto mb-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                      <div className="text-sm">
                        Select a record to view details
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
        
        <div className="h-14 border-t border-gray-200 px-4 flex items-center justify-end gap-2 bg-white">
          <button className="btn h-10 px-3" onClick={close}>
            {t('settings.cancel')}
          </button>
          <button className="btn h-10 px-3" onClick={saveSettings}>
            {t('settings.save_and_restart')}
          </button>
          <button className="btn h-10 px-3" onClick={openLogDirectory}>
            {t('settings.open_log_dir')}
          </button>
          <button className="btn h-10 px-3" onClick={openConfigDirectory}>
            {t('settings.open_config_dir')}
          </button>
        </div>
      </div>
      </div>
    </>
  )
}