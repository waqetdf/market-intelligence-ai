import {useEffect, useRef, useState, type FormEvent} from 'react'
import {createRoot} from 'react-dom/client'
import {CandlestickSeries, ColorType, createChart, type UTCTimestamp} from 'lightweight-charts'
import './style.css'

type Asset = {symbol:string; source:string; ticker:string}
type Bar = {time:UTCTimestamp; open:number; high:number; low:number; close:number}
type Event = {kind:string; side:string; level:number; time:number}
type Result = {bars:Bar[]; source:string; technical:{trend:string; events:Event[]; indicators:Record<string, number | number[] | null>}}
type News = {title:string; url:string; source:string; published:string|null}
type Alert = {symbol:string; direction:string; price:number; observed_at:number; evidence:string[]}

async function api<T>(path:string, init?:RequestInit):Promise<T> {
  const response = await fetch('/api'+path, init)
  if (!response.ok) {
    const payload = await response.json()
    throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Revisa los campos')
  }
  return response.json()
}

function Chart({result, overlays}:{result:Result; overlays:boolean}) {
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
      result.technical.events.filter(event => ['BOS','CHoCH','FVG'].includes(event.kind)).slice(-8).forEach(event =>
        series.createPriceLine({price:event.level,color:event.side === 'alcista' ? '#67bfab' : '#f190a2',title:event.kind,lineWidth:1}))
    }
    chart.timeScale().fitContent()
    return () => chart.remove()
  }, [result, overlays])
  return <div ref={element}/>
}

function App() {
  const [assets,setAssets] = useState<Asset[]>([])
  const [symbol,setSymbol] = useState('')
  const [interval,setInterval] = useState('15m')
  const [result,setResult] = useState<Result>()
  const [alerts,setAlerts] = useState<Alert[]>([])
  const [overlays,setOverlays] = useState(true)
  const [error,setError] = useState('')
  const [formError,setFormError] = useState('')
  const [simulation,setSimulation] = useState<Record<string,number|string|null>>()
  const [loading,setLoading] = useState(false)
  const [news,setNews] = useState<News[]>([])
  const [context,setContext] = useState('')
  const [sources,setSources] = useState<Record<string,{status:string}>>({})
  const [source,setSource] = useState('mt5-csv')
  useEffect(() => {
    api<Asset[]>('/assets').then(items => {setAssets(items); setSymbol(items[0]?.symbol ?? '')}).catch(e => setError(e.message))
    api<{items:News[]}>('/news').then(data=>setNews(data.items)).catch(e=>setError(e.message))
    const refresh = () => api<Alert[]>('/alerts').then(setAlerts).catch(() => {})
    void refresh()
    const timer = setIntervalGlobal(refresh)
    return () => window.clearInterval(timer)
  }, [])
  useEffect(() => {
    setResult(undefined)
    setSimulation(undefined)
    setContext('')
    if (!symbol) return
    const controller = new AbortController()
    setLoading(true)
    setError('')
    api<Result>('/candles?'+new URLSearchParams({symbol,interval}),{signal:controller.signal})
      .then(setResult).catch(e => {if (!controller.signal.aborted) setError(e.message)})
      .finally(() => {if (!controller.signal.aborted) {setLoading(false); api<Record<string,{status:string}>>('/status').then(setSources).catch(()=>{})}})
    return () => controller.abort()
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
  return <main>
    <header><span>MARKET INTELLIGENCE</span><h1>Observatorio de mercados</h1></header>
    <section className="workspace">
      <article className="panel">
        <div className="controls">
          <select aria-label="Activo" value={symbol} onChange={e=>setSymbol(e.target.value)}>{!assets.length && <option value="">Sin activos</option>}{assets.map(a=><option key={a.symbol}>{a.symbol}</option>)}</select>
          <select aria-label="Temporalidad" value={interval} onChange={e=>setInterval(e.target.value)}>{['1m','5m','15m','30m','1h','4h','1d','1w'].map(i=><option key={i}>{i}</option>)}</select>
          <label><input type="checkbox" checked={overlays} onChange={e=>setOverlays(e.target.checked)}/> Patrones</label>
        </div>
        {error ? <p role="alert">{error}</p> : loading ? <p>Cargando velas cerradas…</p> : result?.bars.length ? <><Chart result={result} overlays={overlays}/><p>{result.source} · Tendencia {result.technical.trend} · Último cierre {result.bars.at(-1)?.close}</p><dl>{Object.entries(result.technical.indicators).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{Array.isArray(value) ? value.map(v=>v.toFixed(2)).join(' – ') : value?.toFixed(2) ?? '—'}</dd></div>)}</dl></> : <p>{symbol ? 'Sin velas cerradas disponibles' : 'Añade un activo para ver sus velas'}</p>}
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
      <article className="panel"><h2>Alertas recientes</h2>{alerts.length ? alerts.map(a=><p key={a.symbol+a.observed_at}>{a.symbol} · {a.direction} · {a.price} · {new Date(a.observed_at*1000).toLocaleString()}<br/>{a.evidence.join(' · ')}</p>) : <p>Sin alertas registradas</p>}</article>
      <article className="panel"><h2>Simulación histórica</h2><button disabled={!symbol} onClick={()=>api<Record<string,number|string|null>>('/backtest?'+new URLSearchParams({symbol})).then(setSimulation).catch(e=>setError(e.message))}>Ejecutar</button>{simulation && <dl>{Object.entries(simulation).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{typeof value === 'number' ? Number(value.toFixed(4)) : value ?? '—'}</dd></div>)}</dl>}</article>
    </section>
    <section className="workspace">
      <article className="panel"><h2>Noticias</h2>{news.length ? news.slice(0,12).map(n=><p key={n.url}><a href={n.url} target="_blank" rel="noreferrer">{n.title}</a><br/>{n.source} {n.published}</p>) : <p>Sin titulares disponibles</p>}
      <button disabled={!symbol} onClick={()=>api<{text:string|null; error?:string}>('/context?'+new URLSearchParams({symbol})).then(value=>setContext(value.text ?? value.error ?? 'IA desactivada')).catch(e=>setContext(e.message))}>Consultar contexto</button>{context && <p>{context}</p>}</article>
      <aside className="panel"><h2>Estado de las fuentes</h2>{Object.entries(sources).length ? Object.entries(sources).map(([key,value])=><p key={key}>{key} · {value.status}</p>) : <p>Sin consultas registradas</p>}</aside>
    </section>
  </main>
}
function setIntervalGlobal(fn:()=>void) {return window.setInterval(fn,30000)}
createRoot(document.getElementById('root')!).render(<App/>)
