import en from '../i18n/en.json'
import zh from '../i18n/zh-CN.json'

type Dict = Record<string, string>
const dict: Record<string, Dict> = { en, 'zh-CN': zh }

let current = 'zh-CN'

export function setLocale(locale: 'en' | 'zh-CN') { current = locale }
export function t(key: string): string { return dict[current]?.[key] ?? key }

export function tf(key: string, params: Record<string, string | number>): string {
  let s = t(key)
  for (const [k, v] of Object.entries(params)) {
    s = s.split(`{${k}}`).join(String(v))
  }
  return s
}

// 获取当前语言
export function getCurrentLocale(): 'en' | 'zh-CN' { return current as 'en' | 'zh-CN' }


