import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

const root = ReactDOM.createRoot(document.getElementById('root'))

window.addEventListener('error', (event) => {
  if (event.error && typeof event.error === 'object' && 'bid' in event.error) {
    console.warn('External script error (likely browser extension):', event.message)
    event.stopPropagation()
    event.preventDefault()
    return false
  }
  return true
})

root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)