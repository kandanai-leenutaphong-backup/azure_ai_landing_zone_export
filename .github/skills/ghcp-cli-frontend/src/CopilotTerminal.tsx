import { useEffect, useRef, useState } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { CircleStop, Eraser, FileInput, List, Play, Sparkles, Square, TerminalSquare } from 'lucide-react'
import '@xterm/xterm/css/xterm.css'
import './copilot-terminal.css'

export interface TerminalSource { uid: string; path: string }
export interface PreparedTerminalAction { prompt: string; [key: string]: unknown }

/** A one-click instruction. Any listed files are staged before the prompt is sent. */
export interface TerminalAction {
  id: string
  label: string
  title?: string
  prompt?: string
  autopilot?: boolean
  stage?: TerminalSource[]
  prepare?: { operation: string; payload: object }
  onPrepared?: (result: PreparedTerminalAction) => void
}

export interface CopilotTerminalProps {
  apiBase: string
  active?: boolean
  source?: TerminalSource
  actions?: TerminalAction[]
}

interface Session { session_id: string; key: string; workspace: string; model: string }
interface Output { output: string; cursor: number; reset: boolean; running: boolean; exit_code: number | null }
interface Info { available: boolean; version?: string; model: string; detail?: string }
interface Controls {
  start: () => Promise<void>
  stop: () => Promise<void>
  interrupt: () => void
  clear: () => void
  fit: () => void
  attach: (source: TerminalSource) => Promise<void>
  insertCommand: (command: string) => void
  runAction: (action: TerminalAction) => Promise<void>
}

const nativeCommands = [
  { label: 'Help', command: '/help' },
  { label: 'Context', command: '/context' },
  { label: 'Usage', command: '/usage' },
  { label: 'Environment', command: '/env' },
  { label: 'Session', command: '/session info' },
  { label: 'Skills', command: '/skills list' },
  { label: 'MCP servers', command: '/mcp list' },
  { label: 'Allowed directories', command: '/list-dirs' },
] as const

export function CopilotTerminal({ apiBase, active = true, source, actions = [] }: CopilotTerminalProps) {
  const host = useRef<HTMLDivElement>(null)
  const commandMenu = useRef<HTMLDetailsElement>(null)
  const controls = useRef<Controls | null>(null)
  const [state, setState] = useState('Disconnected')
  const [info, setInfo] = useState<Info | null>(null)
  const [workspace, setWorkspace] = useState('')
  const [error, setError] = useState('')
  const [attaching, setAttaching] = useState(false)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (!host.current) return
    const terminal = new Terminal({
      cursorBlink: true, cursorStyle: 'bar', fontFamily: '"IBM Plex Mono", monospace',
      fontSize: 13, lineHeight: 1.25, scrollback: 5000, screenReaderMode: true,
      theme: { background: '#171a1f', foreground: '#e1e4e7', cursor: '#35d9ff', selectionBackground: '#2f4a58' },
    })
    const fit = new FitAddon()
    terminal.loadAddon(fit)
    terminal.open(host.current)
    terminal.textarea?.setAttribute('aria-label', 'GitHub Copilot CLI input')
    const abort = new AbortController()
    const storageKey = `copilot-terminal:${apiBase}`
    let session: Session | null = null
    let queue = Promise.resolve()
    let outputLoop = 0
    let inputReady = false
    const screenWaiters = new Set<() => void>()

    function screenText() {
      const buffer = terminal.buffer.active
      return Array.from({ length: terminal.rows }, (_, index) =>
        buffer.getLine(buffer.baseY + index)?.translateToString(true) ?? '').join('\n')
    }

    function notifyScreen() { for (const check of screenWaiters) check() }

    function waitForScreen(current: Session, predicate: (text: string) => boolean): Promise<string> {
      return new Promise((resolve, reject) => {
        const finish = (reason?: Error, text = '') => {
          clearTimeout(timer)
          screenWaiters.delete(check)
          abort.signal.removeEventListener('abort', check)
          if (reason) reject(reason)
          else resolve(text)
        }
        const check = () => {
          if (abort.signal.aborted || session !== current) {
            finish(new Error('Terminal session changed while preparing the action'))
            return
          }
          const text = screenText()
          if (predicate(text)) finish(undefined, text)
        }
        const timer = setTimeout(() => finish(new Error('Copilot did not confirm the requested mode; no task was submitted')), 20000)
        screenWaiters.add(check)
        abort.signal.addEventListener('abort', check, { once: true })
        check()
      })
    }

    async function nativeCommand(current: Session, command: string) {
      await request('input', { ...current, data: command })
      await waitForScreen(current, text => text.includes(`\u2503 ${command}`))
      await request('input', { ...current, data: '\r' })
    }

    async function enableAutopilot(current: Session) {
      await nativeCommand(current, '/settings stayInAutopilot false')
      await waitForScreen(current, text => text.includes('Set stayInAutopilot = false.') && !text.includes('\u2503 /settings'))
      await nativeCommand(current, '/autopilot on')
      const enabled = /autopilot mode enabled|already in autopilot mode/i
      const text = await waitForScreen(current, visible => !visible.includes('\u2503 /autopilot on')
        && (visible.includes('Enable autopilot mode') || enabled.test(visible)))
      if (text.includes('Enable autopilot mode')) {
        if (!text.includes('Continue with limited permissions')) throw new Error('Unknown autopilot permission dialog; no permissions granted')
        await request('input', { ...current, data: '\x1b[B' })
        await waitForScreen(current, visible => /\u276f 2\. Continue with limited permissions/.test(visible))
        await request('input', { ...current, data: '\r' })
        await waitForScreen(current, visible => !visible.includes('Enable autopilot mode') && enabled.test(visible))
      }
    }

    async function request<Result>(action: string, body: object): Promise<Result> {
      const response = await fetch(`${apiBase}/${action}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Copilot-Terminal': '1' },
        body: JSON.stringify(body), signal: abort.signal,
      })
      const data = await response.json() as Result & { detail?: string }
      if (!response.ok) throw new Error(data.detail ?? `Terminal request failed (${response.status})`)
      return data
    }

    function report(reason: unknown) {
      if (!abort.signal.aborted) setError(reason instanceof Error ? reason.message : 'Terminal unavailable')
    }

    function enqueue(action: string, body: object) {
      const current = session
      if (!current) return
      queue = queue.then(async () => { await request(action, { ...current, ...body }) }).catch(report)
    }

    async function output(current: Session) {
      const loop = ++outputLoop
      let cursor = 0
      try {
        while (!abort.signal.aborted && session === current && outputLoop === loop) {
          const result = await request<Output>('output', { ...current, cursor })
          if (session !== current || abort.signal.aborted) break
          if (result.reset) terminal.reset()
          if (result.output) await new Promise<void>((resolve) => terminal.write(result.output, resolve))
          const buffer = terminal.buffer.active
          const footer = Array.from({ length: Math.min(5, terminal.rows) }, (_, index) =>
            buffer.getLine(buffer.baseY + terminal.rows - 1 - index)?.translateToString(true) ?? '').reverse().join(' ')
          inputReady = !/enter to select|esc interrupt/i.test(footer) && /\/ commands.*\? help|@ files.*# issues/i.test(footer)
          setReady(inputReady)
          notifyScreen()
          cursor = result.cursor
          if (!result.running) {
            session = null
            notifyScreen()
            sessionStorage.removeItem(storageKey)
            setState(`Exited (${result.exit_code ?? 0})`)
            await request('stop', current)
            break
          }
        }
      } catch (reason) {
        if (abort.signal.aborted || session !== current) return
        session = null
        notifyScreen()
        sessionStorage.removeItem(storageKey)
        setState('Disconnected')
        report(reason)
      }
    }

    function fitTerminal() {
      if (!host.current?.offsetWidth || !host.current.offsetHeight) return
      fit.fit()
    }

    controls.current = {
      async start() {
        if (session) return
        setError('')
        setState('Starting')
        inputReady = false
        setReady(false)
        fitTerminal()
        try {
          const current = await request<Session>('start', { columns: Math.min(400, Math.max(20, terminal.cols)), rows: Math.min(200, Math.max(5, terminal.rows)) })
          if (abort.signal.aborted) return
          session = current
          sessionStorage.setItem(storageKey, JSON.stringify(current))
          setWorkspace(current.workspace)
          setState('Connected')
          terminal.reset()
          terminal.focus()
          void output(current)
        } catch (reason) {
          if (!abort.signal.aborted) setState('Disconnected')
          report(reason)
        }
      },
      async stop() {
        const current = session
        if (!current) return
        session = null
        outputLoop += 1
        sessionStorage.removeItem(storageKey)
        setState('Closing')
        try {
          await request('stop', current)
          if (!abort.signal.aborted) setState('Disconnected')
        } catch (reason) { report(reason) }
      },
      interrupt: () => { enqueue('input', { data: '\x03' }); terminal.focus() },
      clear: () => { terminal.clear(); terminal.focus() },
      fit: fitTerminal,
      insertCommand(command) {
        if (!session || !inputReady || !nativeCommands.some(item => item.command === command)) return
        terminal.paste(command)
        if (commandMenu.current) commandMenu.current.open = false
        terminal.focus()
      },
      async attach(selected) {
        const current = session
        if (!current) return
        setAttaching(true)
        setError('')
        try {
          const result = await request<{ path: string }>('source', { ...current, source: selected })
          terminal.paste(`@${JSON.stringify(result.path)} `)
          terminal.focus()
        } catch (reason) { report(reason) }
        finally { if (!abort.signal.aborted) setAttaching(false) }
      },
      async runAction(action) {
        const current = session
        if (!current || !inputReady) return
        inputReady = false
        setReady(false)
        setAttaching(true)
        setError('')
        try {
          let prompt = action.prompt
          if (action.prepare) {
            const prepared = await request<PreparedTerminalAction>(action.prepare.operation, { ...action.prepare.payload, ...current })
            prompt = prepared.prompt
            action.onPrepared?.(prepared)
          }
          for (const item of action.stage ?? []) {
            await request('source', { ...current, source: item })
          }
          if (typeof prompt !== 'string' || !prompt.trim()) throw new Error('The action supplied no instruction')
          if (action.autopilot) await enableAutopilot(current)
          if (session !== current || abort.signal.aborted) return
          await request('input', { ...current, data: prompt })
          // A return arriving in the same chunk reads as a paste newline, so the
          // CLI would hold the text in its box. Submit it once the text settles.
          await new Promise((resolve) => setTimeout(resolve, 600))
          if (abort.signal.aborted) return
          await request('input', { ...current, data: '\r' })
          terminal.focus()
        } catch (reason) { report(reason) }
        finally { if (!abort.signal.aborted) setAttaching(false) }
      },
    }

    const input = terminal.onData((data) => {
      if (data.includes('\r')) { inputReady = false; setReady(false) }
      enqueue('input', { data })
    })
    const resize = terminal.onResize(({ cols, rows }) => {
      if (cols >= 20 && rows >= 5) enqueue('resize', { columns: cols, rows })
    })
    const observer = new ResizeObserver(fitTerminal)
    observer.observe(host.current)
    void request<Info>('info', {}).then((result) => {
      setInfo(result)
      if (!result.available) setError(result.detail ?? 'Copilot CLI unavailable')
      const stored = sessionStorage.getItem(storageKey)
      if (stored && result.available) {
        const current = JSON.parse(stored) as Session
        session = current
        setWorkspace(current.workspace)
        setState('Connected')
        fitTerminal()
        enqueue('resize', { columns: Math.min(400, Math.max(20, terminal.cols)), rows: Math.min(200, Math.max(5, terminal.rows)) })
        void output(current)
      }
    }).catch(report)

    return () => {
      abort.abort()
      outputLoop += 1
      observer.disconnect()
      input.dispose()
      resize.dispose()
      terminal.dispose()
      controls.current = null
    }
  }, [apiBase])

  useEffect(() => {
    if (active) {
      const frame = requestAnimationFrame(() => controls.current?.fit())
      return () => cancelAnimationFrame(frame)
    }
  }, [active])

  const connected = state === 'Connected'
  const pending = state === 'Starting' || state === 'Closing'
  return <section className="column copilot-terminal" aria-label="GitHub Copilot CLI" data-state={state}>
    <header className="copilot-terminal-toolbar">
      <span className="copilot-terminal-title"><TerminalSquare size={16} aria-hidden />GitHub Copilot CLI</span>
      <div className="copilot-terminal-actions">
        {!connected && <button type="button" className="copilot-terminal-start" disabled={pending || !info?.available} onClick={() => void controls.current?.start()}>
          <Play size={14} aria-hidden />{pending ? 'Starting' : 'Start Copilot'}
        </button>}
        {connected && <>
          <details ref={commandMenu} className="copilot-terminal-command-menu" onKeyDown={(event) => {
            if (event.key === 'Escape' && commandMenu.current) {
              commandMenu.current.open = false
              commandMenu.current.querySelector('summary')?.focus()
            }
          }}>
            <summary aria-label="Insert CLI command" title="Insert CLI command"><List size={16} aria-hidden /></summary>
            <div className="copilot-terminal-command-list" role="group" aria-label="Native CLI commands">
              {nativeCommands.map(item => <button key={item.command} type="button" disabled={attaching || !ready}
                title={`Insert ${item.command}`} onClick={() => controls.current?.insertCommand(item.command)}>
                <span>{item.label}</span><code>{item.command}</code>
              </button>)}
            </div>
          </details>
          {actions.map((action) => (
            <button
              key={action.id} type="button" className="copilot-terminal-action"
              title={action.title ?? action.label} disabled={attaching || !ready}
              onClick={() => void controls.current?.runAction(action)}
            >
              <Sparkles size={14} aria-hidden />{action.label}
            </button>
          ))}
          <button type="button" title="Use selected file in terminal" aria-label="Use selected file in terminal" disabled={!source || attaching} onClick={() => { if (source) void controls.current?.attach(source) }}><FileInput size={16} aria-hidden /></button>
          <button type="button" title="Interrupt current command" aria-label="Interrupt current command" onClick={() => controls.current?.interrupt()}><CircleStop size={16} aria-hidden /></button>
          <button type="button" title="End terminal session" aria-label="End terminal session" onClick={() => void controls.current?.stop()}><Square size={14} aria-hidden /></button>
        </>}
        <button type="button" title="Clear terminal viewport" aria-label="Clear terminal viewport" onClick={() => controls.current?.clear()}><Eraser size={16} aria-hidden /></button>
      </div>
    </header>
    {source && <div className="copilot-terminal-file" title={source.path}>{source.path}</div>}
    {error && <div role="alert" className="copilot-terminal-error">{error}</div>}
    <div className="copilot-terminal-surface"><div ref={host} className="copilot-terminal-host" /></div>
    <footer className="copilot-terminal-status" title={workspace}>
      <span role="status">{attaching ? 'Preparing file' : state}</span>
      <span>{info?.model ?? 'Copilot'}</span>
      <span>{info?.version ?? ''}</span>
    </footer>
  </section>
}