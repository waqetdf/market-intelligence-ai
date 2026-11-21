import {useEffect, useRef, useState, type FormEvent} from 'react'
import {createRoot} from 'react-dom/client'
import {CandlestickSeries, ColorType, createChart, type UTCTimestamp} from 'lightweight-charts'
import './style.css'

type Asset = {symbol:string; source:string; ticker:string}
type Bar = {time:UTCTimestamp; open:number; high:number; low:number; close:number}
type Event = {kind:string; side:string; level:number; time:number}
type Result = {bars:Bar[]; source:string; technical:{trend:string; events:Event[]; indicators:Record<string, number | number[] | null>}}
type Simulation = Record<string,unknown>
type News = {title:string; url:string; source:string; published:string|null}
type Alert = {symbol:string; direction:string; price:number; observed_at:number; evidence:string[];
  risks?:string[]; invalidation?:number|null; target?:number|null; reward_risk?:number|null;
  chart?:string|null; news?:News[]; assessment?:{text:string}; trends?:Record<string,string>}
type Integration = 'ai' | 'discord' | 'telegram'
type Settings = {feeds:{allowed:string[]; enabled:string[]}; ai:{provider:string; model:string|null};
  configured:Record<Integration,boolean>; integrations:Record<Integration,boolean>}
type Server = {started_at:number; monitor:{last_cycle?:number; error?:string|null}}
const dateTime = (timestamp:number) => new Date(timestamp*1000).toLocaleString()

function Signal({signal}:{signal:Alert}) {
  return <details>
    <summary>{signal.symbol} · {signal.direction} · {signal.price} · {dateTime(signal.observed_at)}</summary>
    {!!signal.evidence.length && <p>{signal.evidence.join(' · ')}</p>}
    {!!signal.trends && <p>{Object.entries(signal.trends).map(([frame, trend])=>frame+' '+trend).join(' · ')}</p>}
    {!!signal.risks?.length && <p>{signal.risks.join(' · ')}</p>}
    {signal.invalidation != null && <p>Invalidación {signal.invalidation} · Objetivo {signal.target ?? '—'} · R/B {signal.reward_risk?.toFixed(2) ?? '—'}</p>}
    {signal.chart && <p><a href={signal.chart} target="_blank" rel="noreferrer">Gráfico del proveedor</a></p>}
    {signal.assessment?.text && <p>{signal.assessment.text}</p>}
    {signal.news?.map(item=><p key={item.url}><a href={item.url} target="_blank" rel="noreferrer">{item.title}</a> · {item.source}</p>)}
  </details>
}

async function api<T>(path:string, init?:RequestInit):Promise<T> {
  const response = await fetch('/api'+path, init)
  if (!response.ok) {
    const payload = await response.json()
    throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Revisa los campos')
  }
  return response.json()
}

function Chart({result, overlays, levels}:{result:Result; overlays:boolean; levels:boolean}) {
  const element = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!element.current) return
    const chart = createChart(element.current, {autoSize:true, height:420,
      layout:{background:{type:ColorType.Solid,color:'#121b23'},textColor:'#b2c0cd'},
      grid:{vertLines:{color:'#1e2c37'},horzLines:{color:'#1e2c37'}},
      timeScale:{timeVisible:true}})
    const series = chart.addSeries(CandlestickSeries,{upColor:'#4bd7a4',downColor:'#fa8191',borderVisible:false,wickUpColor:'#4bd7a4',wickDownColor:'#fa8191'})
    series.setData(result.bars)
    if (overlays) {
      result.technical.events.filter(event => ['BOS','CHoCH','FVG','IFVG','MSS','Liquidity Sweep','Order Block','Breaker Block'].includes(event.kind)).slice(-8).forEach(event =>
        series.createPriceLine({price:event.level,color:event.side === 'alcista' ? '#67bfab' : '#f190a2',title:event.kind,lineWidth:1}))
    }
    if (levels) {
      for (const key of ['ema', 'sma', 'vwap', 'bollinger']) {
        const value = result.technical.indicators[key]
        for (const price of Array.isArray(value) ? value : [value]) {
          if (typeof price === 'number') series.createPriceLine({price, color:'#91a4f5', title:key.toUpperCase(), lineWidth:1})
        }
      }
    }
    chart.timeScale().fitContent()
    return () => chart.remove()
  }, [result, overlays, levels])
  return <div ref={element}/>
}

const initialParams = new URLSearchParams(window.location.search)
const timeframes = ['1m','5m','15m','30m','1h','4h','1d','1w']

function App() {
  const [assets,setAssets] = useState<Asset[]>([])
  const [symbol,setSymbol] = useState('')
  const requestedInterval = initialParams.get('interval') ?? ''
  const [interval,setInterval] = useState(timeframes.includes(requestedInterval) ? requestedInterval : '15m')
  const [result,setResult] = useState<Result>()
  const [alerts,setAlerts] = useState<Alert[]>([])
  const [overlays,setOverlays] = useState(true)
  const [levels,setLevels] = useState(false)
  const [history,setHistory] = useState<Alert[]>([])
  const [settings,setSettings] = useState<Settings>()
  const [server,setServer] = useState<Server>()
  const [settingsError,setSettingsError] = useState('')
  const [simulationError,setSimulationError] = useState('')
  const [error,setError] = useState('')
  const [formError,setFormError] = useState('')
  const [simulation,setSimulation] = useState<Simulation>()
  const [loading,setLoading] = useState(false)
  const [news,setNews] = useState<News[]>([])
  const [context,setContext] = useState('')
  const [references,setReferences] = useState<News[]>([])
  const [sources,setSources] = useState<Record<string,{status:string}>>({})
  const [source,setSource] = useState('mt5-csv')
  useEffect(() => {
    api<Asset[]>('/assets').then(items => {setAssets(items); setSymbol(items.find(item=>item.symbol === initialParams.get('symbol'))?.symbol ?? items[0]?.symbol ?? '')}).catch(e => setError(e.message))
    api<Settings>('/settings').then(setSettings).catch(e=>setSettingsError(e.message))
    const refresh = () => {
      void Promise.allSettled([
        api<Alert[]>('/alerts').then(setAlerts),
        api<Alert[]>('/history').then(setHistory),
        api<{items:News[]}>('/news').then(data=>setNews(data.items)),
        api<Server>('/server').then(setServer),
        api<Record<string,{status:string}>>('/status').then(setSources),
      ])
    }
    void refresh()
    const timer = setIntervalGlobal(refresh)
    return () => window.clearInterval(timer)
  }, [])
  useEffect(() => {
    setResult(undefined)
    setSimulation(undefined)
    setSimulationError('')
    setContext('')
    setReferences([])
    if (!symbol) return
    const controller = new AbortController()
    setLoading(true)
    setError('')
    const refresh = () => api<Result>('/candles?'+new URLSearchParams({symbol,interval}),{signal:controller.signal})
      .then(setResult).catch(e => {if (!controller.signal.aborted) setError(e.message)})
      .finally(() => {if (!controller.signal.aborted) {setLoading(false); api<Record<string,{status:string}>>('/status').then(setSources).catch(()=>{})}})
    void refresh()
    const timer = setIntervalGlobal(refresh)
    return () => {controller.abort(); window.clearInterval(timer)}
  }, [symbol,interval])
  async function add(event:FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setFormError('')
    try {
      const item = await api<Asset>('/assets',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({symbol:String(form.get('symbol')).toUpperCase(),ticker:form.get('ticker'),source})})
      setAssets(items=>[...items,item]); setSymbol(item.symbol)
    } catch(e) {setFormError((e as Error).message)}
  }
  async function updateFeed(url:string, active:boolean) {
    if (!settings) return
    setSettingsError('')
    const urls = active ? [...settings.feeds.enabled,url] : settings.feeds.enabled.filter(item=>item !== url)
    try {
      setSettings(await api<Settings>('/settings/feeds',{method:'PUT',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({urls})}))
    } catch(e) {setSettingsError((e as Error).message)}
  }

  async function updateIntegration(key:Integration, active:boolean) {
    if (!settings) return
    setSettingsError('')
    try {
      setSettings(await api<Settings>('/settings/integrations',{method:'PUT',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({...settings.integrations,[key]:active})}))
    } catch(e) {setSettingsError((e as Error).message)}
  }

  async function runSimulation(event:FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const params = new URLSearchParams({symbol})
    for (const input of ['count','fee_bps','slippage_bps']) params.set(input, String(form.get(input)))
    setSimulationError('')
    try {setSimulation(await api<Simulation>('/backtest?'+params))}
    catch(e) {setSimulationError((e as Error).message)}
  }
  const holdout = simulation?.out_of_sample as {count:number; expectancy:number|null}|null|undefined
  const folds = simulation?.walk_forward as {start:number; end:number; count:number}[]|undefined
  return <main>
    <header><span>MARKET INTELLIGENCE</span><h1>Observatorio de mercados</h1></header>
    <section className="workspace">
      <article className="panel">
        <div className="controls">
          <select aria-label="Activo" value={symbol} onChange={e=>setSymbol(e.target.value)}>{!assets.length && <option value="">Sin activos</option>}{assets.map(a=><option key={a.symbol}>{a.symbol}</option>)}</select>
          <select aria-label="Temporalidad" value={interval} onChange={e=>setInterval(e.target.value)}>{timeframes.map(i=><option key={i}>{i}</option>)}</select>
          <label><input type="checkbox" checked={levels} onChange={e=>setLevels(e.target.checked)}/> Niveles de indicadores</label>
          <label><input type="checkbox" checked={overlays} onChange={e=>setOverlays(e.target.checked)}/> Patrones</label>
        </div>
        {error ? <p role="alert">{error}</p> : loading ? <p>Cargando velas cerradas…</p> : result?.bars.length ? <><Chart result={result} overlays={overlays} levels={levels}/><p>{result.source} · Tendencia {result.technical.trend} · Último cierre {result.bars.at(-1)?.close}</p><dl>{Object.entries(result.technical.indicators).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{Array.isArray(value) ? value.map(v=>v.toFixed(2)).join(' – ') : value?.toFixed(2) ?? '—'}</dd></div>)}</dl></> : <p>{symbol ? 'Sin velas cerradas disponibles' : 'Añade un activo para ver sus velas'}</p>}
      </article>
      <aside className="panel">
        <h2>Añadir activo</h2>
        <form onSubmit={add}>
          <label>Símbolo <input name="symbol" required maxLength={24} placeholder="XAUUSD"/></label>
          <label>Fuente <select value={source} onChange={e=>setSource(e.target.value)}><option value="mt5-csv">MetaTrader 5 CSV</option><option value="binance">Binance Spot</option></select></label>
          <label>{source === 'mt5-csv' ? 'Prefijo del CSV' : 'Ticker del proveedor'} <input name="ticker" required maxLength={32}/></label>
          <button>Añadir</button>{formError && <p role="alert">{formError}</p>}
        </form>
      </aside>
    </section>
    <section className="workspace">
      <article className="panel"><h2>Alertas recientes</h2>{alerts.length
        ? alerts.map(signal=><Signal key={signal.symbol+signal.observed_at} signal={signal}/>)
        : <p>Sin alertas registradas</p>}
        <h2>Historial de decisiones</h2>{history.filter(signal=>signal.symbol===symbol).slice(0,30)
          .map(signal=><Signal key={signal.observed_at} signal={signal}/>)}
      </article>
      <article className="panel"><h2>Simulación histórica</h2>
        <form onSubmit={runSimulation}>
          <label>Velas <input name="count" type="number" min={300} max={5000} defaultValue={3000} required/></label>
          <label>Comisión (pb) <input name="fee_bps" type="number" min={0} max={500} step=".1" defaultValue={10} required/></label>
          <label>Deslizamiento (pb) <input name="slippage_bps" type="number" min={0} max={500} step=".1" defaultValue={5} required/></label>
          <button disabled={!symbol}>Ejecutar</button>
        </form>{simulationError && <p role="alert">{simulationError}</p>}{simulation && <dl>{Object.entries(simulation).filter(([,value])=>value == null || typeof value !== 'object').map(([key,value])=><div key={key}><dt>{key}</dt><dd>{typeof value === 'number' ? Number(value.toFixed(4)) : String(value ?? '—')}</dd></div>)}</dl>}
        {holdout && <p>Último tramo · {holdout.count} señales · Expectativa {holdout.expectancy?.toFixed(4) ?? '—'}</p>}
        {!!folds?.length && <p>Ventanas cronológicas · {folds.map(fold=>fold.count).join(' / ')} señales</p>}
      </article>
    </section>
    <section className="workspace">
      <article className="panel"><h2>Noticias</h2>{news.length ? news.slice(0,12).map(n=><p key={n.url}><a href={n.url} target="_blank" rel="noreferrer">{n.title}</a><br/>{n.source} {n.published}</p>) : <p>Sin titulares disponibles</p>}
      <button disabled={!symbol} onClick={()=>api<{text:string|null; error?:string; references?:News[]}>('/context?'+new URLSearchParams({symbol})).then(value=>{setContext(value.text ?? value.error ?? 'IA desactivada'); setReferences(value.references ?? [])}).catch(e=>setContext(e.message))}>Consultar contexto</button>{context && <p>{context}</p>}
      {references.map(item=><p key={item.url}><a href={item.url} target="_blank" rel="noreferrer">{item.title}</a> · {item.source}</p>)}</article>
      <aside className="panel"><h2>Motor de análisis</h2>
      {server && <p>Inicio {dateTime(server.started_at)} · {server.monitor.error ?? (server.monitor.last_cycle ? 'Último ciclo '+dateTime(server.monitor.last_cycle) : 'Esperando primer ciclo')}</p>}
      <h2>Estado de las fuentes</h2>{Object.entries(sources).length ? Object.entries(sources).map(([key,value])=><p key={key}>{key} · {value.status}</p>) : <p>Sin consultas registradas</p>}</aside>
    </section>
    <section className="panel">
      <h2>Configuración</h2>
      {settingsError && <p role="alert">{settingsError}</p>}
      {settings && <>
        {(['ai','discord','telegram'] as const).map(key=><p key={key}><label>
          <input type="checkbox" checked={settings.integrations[key]} disabled={!settings.configured[key]}
            onChange={e=>void updateIntegration(key,e.target.checked)}/>
          {key === 'ai' ? 'IA · '+settings.ai.provider+' '+(settings.ai.model ?? '') : key === 'discord' ? 'Discord' : 'Telegram'}
          {!settings.configured[key] && ' · sin configurar'}
        </label></p>)}
        <h3>Fuentes de noticias</h3>
        {settings.feeds.allowed.length ? settings.feeds.allowed.map(url=><p key={url}><label>
          <input type="checkbox" checked={settings.feeds.enabled.includes(url)} onChange={e=>void updateFeed(url,e.target.checked)}/> {new URL(url).hostname}
        </label></p>) : <p>Configura fuentes autorizadas en el servidor.</p>}
      </>}
    </section>
  </main>
}
function setIntervalGlobal(fn:()=>void) {return window.setInterval(fn,30000)}
createRoot(document.getElementById('root')!).render(<App/>)
