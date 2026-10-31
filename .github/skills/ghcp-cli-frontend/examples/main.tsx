import { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { CopilotTerminal } from 'copilot-terminal'
import './style.css'

function Example() {
  const [mode, setMode] = useState('Local')
  useEffect(() => {
    const abort = new AbortController()
    void fetch('/example-info', { signal: abort.signal }).then(response => response.json())
      .then((result: { mode: string }) => setMode(result.mode)).catch(() => {})
    return () => abort.abort()
  }, [])
  return <main className="example-layout">
    <header className="example-header"><h1>GHCP CLI Frontend</h1><span>{mode}</span></header>
    <CopilotTerminal apiBase="/api/terminal" source={{ uid: 'example', path: 'example.txt' }}
      actions={mode === 'Offline CLI'
        ? [{ id: 'autopilot-info', label: 'Autopilot session', autopilot: true, prompt: '/session info' }]
        : [{ id: 'inspect', label: 'Inspect source', stage: [{ uid: 'example', path: 'example.txt' }],
          prepare: { operation: 'prepare', payload: {} } }]} />
  </main>
}

createRoot(document.getElementById('root')!).render(<Example />)