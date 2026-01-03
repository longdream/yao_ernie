import { invoke } from '@tauri-apps/api/core'
import { getCurrentWindow } from '@tauri-apps/api/window'
import { log } from './log'

// 显示主窗口
export async function showMainWindow(): Promise<void> {
  try {
    await invoke('show_main_window')
    await log('INFO', 'main_window_shown')
  } catch (error) {
    await log('ERROR', 'show_main_window_failed', { error: String(error) })
    throw error
  }
}

// 隐藏主窗口到托盘
export async function hideMainWindow(): Promise<void> {
  try {
    await invoke('hide_main_window')
    await log('INFO', 'main_window_hidden')
  } catch (error) {
    await log('ERROR', 'hide_main_window_failed', { error: String(error) })
    throw error
  }
}

// 最小化窗口到托盘
export async function minimizeToTray(): Promise<void> {
  try {
    const window = getCurrentWindow()
    await window.hide()
    await log('INFO', 'window_minimized_to_tray')
  } catch (error) {
    await log('ERROR', 'minimize_to_tray_failed', { error: String(error) })
    throw error
  }
}

// 检查窗口是否可见
export async function isWindowVisible(): Promise<boolean> {
  try {
    const window = getCurrentWindow()
    return await window.isVisible()
  } catch (error) {
    await log('ERROR', 'check_window_visibility_failed', { error: String(error) })
    return false
  }
}

// 设置窗口关闭行为（最小化到托盘而不是退出）
export function setupWindowCloseHandler(): void {
  const window = getCurrentWindow()
  
  window.listen('tauri://close-requested', async (event) => {
    try {
      // 阻止默认的关闭行为
      event.preventDefault?.()
      
      // 隐藏窗口到托盘
      await hideMainWindow()
      await log('INFO', 'window_closed_to_tray')
    } catch (error) {
      await log('ERROR', 'window_close_handler_failed', { error: String(error) })
      // 如果隐藏失败，允许正常关闭
      await window.close()
    }
  })
}
