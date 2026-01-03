import React, { useEffect, useState } from 'react'
import { useStore } from '../utils/store'
import { fetchModels } from '../utils/proxy'
import { t } from '../utils/i18n'
import { Dropdown } from './Dropdown'
import type { ModelConfig } from '../utils/types'

export const SettingsModal: React.FC<{ close: () => void }> = ({ close }) => {
  const { config, setConfig, persist } = useStore()
  const [local, setLocal] = useState(config)
  const [modelList, setModelList] = useState<ModelConfig[]>(config.models || [])
  const [models, setModels] = useState<string[]>([])

  useEffect(() => {
    fetchModels(local).then(setModels).catch(() => setModels([]))
  }, [local.provider, local.baseUrl, local.apiKey])

  return (
    <div className="fixed inset-0 bg-black/20 flex items-center justify-center">
      <div className="w-[560px] bg-white text-gray-900 rounded-lg border border-gray-200 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="font-medium">{t('settings.title')}</div>
          <button className="btn h-8 px-2" onClick={close}>×</button>
        </div>
        <div className="space-y-3">
          <div className="space-y-1">
            <div className="text-sm text-gray-600">{t('settings.provider')}</div>
            <Dropdown
              value={local.provider}
              options={[
                { label: 'OpenAI', value: 'openai' },
              ]}
              onChange={(v) => setLocal({ ...local, provider: v as any })}
            />
          </div>

            <div className="space-y-2">
              <div>
                <div className="text-sm text-gray-600">{t('settings.api_key')}</div>
                <input
                  className="input w-full"
                  value={local.apiKey || ''}
                  onChange={(e) => setLocal({ ...local, apiKey: e.target.value })}
                  placeholder="sk-..."
                />
              </div>
              <div>
                <div className="text-sm text-gray-600">{t('settings.base_url')}</div>
                <input
                  className="input w-full"
                  value={local.baseUrl}
                  onChange={(e) => setLocal({ ...local, baseUrl: e.target.value })}
                  placeholder="https://api.openai.com/v1"
                />
              </div>
            </div>

          <div>
            <div className="text-sm text-gray-600">{t('settings.model')}</div>
            <input
              className="input w-full"
              placeholder={t('settings.model')}
              value={local.model || ''}
              onChange={(e) => setLocal({ ...local, model: e.target.value })}
            />
            <div className="pt-2 text-sm text-gray-600">Models</div>
            <div className="space-y-2 max-h-40 overflow-auto mt-1">
              {modelList.map((m, idx) => (
                <div key={idx} className="border border-gray-200 rounded-lg p-2 flex items-center gap-2">
                  <input className="input h-9 flex-1" value={m.name} onChange={(e)=>{
                    const next=[...modelList]; next[idx]={...m, name:e.target.value}; setModelList(next)
                  }} />
                  <Dropdown value={m.provider} options={[{label:'openai',value:'openai'}]} onChange={(v)=>{
                    const next=[...modelList]; next[idx]={...m, provider:v as any}; setModelList(next)
                  }} />
                  <input className="input h-9 flex-1" placeholder="Base URL" value={m.baseUrl || ''} onChange={(e)=>{
                    const next=[...modelList]; next[idx]={...m, baseUrl:e.target.value}; setModelList(next)
                  }} />
                  <input className="input h-9 flex-1" placeholder="API Key" value={m.apiKey || ''} onChange={(e)=>{
                    const next=[...modelList]; next[idx]={...m, apiKey:e.target.value}; setModelList(next)
                  }} />
                  <button className="btn h-9 px-2" onClick={()=>{ const next=[...modelList]; next.splice(idx,1); setModelList(next) }}>-</button>
                </div>
              ))}
              <button className="btn h-9 px-3" onClick={()=> setModelList([...modelList, { name:'gpt-3.5-turbo', provider:'openai', baseUrl: 'https://api.openai.com/v1' }]) }>+ Add Model</button>
            </div>
          </div>
        </div>

        <div className="pt-2 flex justify-end">
          <button
            className="btn h-10 px-3"
            onClick={async () => {
              setConfig({ ...local, models: modelList })
              await persist()
              try {
                const path = await import('../utils/log').then(m => m.getLogPath())
                console.log('settings saved to:', path)
              } catch {}
              location.reload()
            }}
          >
            {t('settings.save_and_restart')}
          </button>
        </div>
      </div>
    </div>
  )
}


