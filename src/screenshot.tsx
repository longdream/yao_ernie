import React from 'react'
import ReactDOM from 'react-dom/client'
import { FullScreenScreenshot } from './ui/FullScreenScreenshot'
import './index.css'

ReactDOM.createRoot(document.getElementById('screenshot-root')!).render(
  <React.StrictMode>
    <FullScreenScreenshot />
  </React.StrictMode>
)
