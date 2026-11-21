import {useEffect, useRef, useState, type FormEvent} from 'react'
import {createRoot} from 'react-dom/client'
import {CandlestickSeries, ColorType, createChart, type UTCTimestamp} from 'lightweight-charts'
import './style.css'

type Asset = {symbol:string; source:string; ticker:string; enabled:boolean}
type Bar = {time:UTCTimestamp; open:number; high:number; low:number; close:number}
type Event = {kind:string; side:string; level:number; time:number}
type Result = {bars:Bar[]; source:string; technical:{trend:string; events:Event[]; indicators:Record<string, number | number[] | null>}}
type Simulation = Record<string,unknown> & {id:string; created_at:number; timeframe:string}
type Forward = {count:number; expectancy:number|null; positive:number;
  items:{observed_at:number; resolved_at:number; direction:string; net_return:number}[]}
type Release = {title:string; starts_at:number; source:string; url:string}
type Strategy = {window:number; volume_min:number; require_sweep:boolean; require_fvg:boolean; max_stop_atr:number; macro_pause_minutes:number}
type News = {title:string; url:string; source:string; published:string|null}
type Alert = {symbol:string; direction:string; price:number; observed_at:number; evidence:string[];
  quality?:{status:string; sample?:number}; interest_zone?:number[]; calendar?:Release[];
  risks?:string[]; invalidation?:number|null; target?:number|null; reward_risk?:number|null;
  chart?:string|null; news?:News[]; assessment?:{text:string}; trends?:Record<string,string>}
type MarketSummary = {asset:Asset; latest:Alert|null}
type Integration = 'ai' | 'discord' | 'telegram'
type Settings = {local_configuration:boolean; strategy:Strategy; feeds:{allowed:string[]; enabled:string[]; editable:boolean}; ai:{provider:string; model:string|null};
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
    {signal.quality && signal.direction !== 'sin señal' && <p>Calidad · {signal.quality.status}{signal.quality.sample != null && ' · '+signal.quality.sample+' señales históricas'}</p>}
    {signal.interest_zone && <p>Zona de interés · {signal.interest_zone.join(' – ')}</p>}
    {signal.calendar?.map(item=><p key={item.title+item.starts_at}><a href={item.url} target="_blank" rel="noreferrer">{item.title}</a> · {dateTime(item.starts_at)}</p>)}
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
  const [overview,setOverview] = useState<MarketSummary[]>([])
  const [symbol,setSymbol] = useState('')
  const requestedInterval = initialParams.get('interval') ?? ''
  const [interval,setInterval] = useState(timeframes.includes(requestedInterval) ? requestedInterval : '15m')
  const [result,setResult] = useState<Result>()
  const [alerts,setAlerts] = useState<Alert[]>([])
  const [overlays,setOverlays] = useState(true)
  const [levels,setLevels] = useState(false)
  const [forward,setForward] = useState<Forward>()
  const [history,setHistory] = useState<Alert[]>([])
  const [settings,setSettings] = useState<Settings>()
  const [server,setServer] = useState<Server>()
  const [settingsError,setSettingsError] = useState('')
  const [simulationError,setSimulationError] = useState('')
  const [error,setError] = useState('')
  const [formError,setFormError] = useState('')
  const [saved,setSaved] = useState<Simulation[]>([])
  const [simulationBusy,setSimulationBusy] = useState(false)
  const [calendar,setCalendar] = useState<{items:Release[]; error?:string|null}>({items:[]})
  const [strategySaved,setStrategySaved] = useState(false)
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
        api<MarketSummary[]>('/overview').then(setOverview),
        api<Alert[]>('/alerts').then(setAlerts),
        api<{items:News[]}>('/news').then(data=>setNews(data.items)),
        api<Server>('/server').then(setServer),
        api<{items:Release[]; error?:string|null}>('/calendar').then(setCalendar),
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
    setSaved([])
    setForward(undefined)
    setSimulationError('')
    setContext('')
    setReferences([])
    if (!symbol) return
    const controller = new AbortController()
    api<Simulation[]>('/simulations?'+new URLSearchParams({symbol}), {signal:controller.signal})
      .then(setSaved).catch(()=>{})
    setLoading(true)
    setError('')
    const refresh = () => {
      void api<Alert[]>('/history?'+new URLSearchParams({symbol}),{signal:controller.signal}).then(setHistory).catch(()=>{})
      void api<Forward>('/forward?'+new URLSearchParams({symbol}),{signal:controller.signal}).then(setForward).catch(()=>{})
      return api<Result>('/candles?'+new URLSearchParams({symbol,interval}),{signal:controller.signal})
      .then(setResult).catch(e => {if (!controller.signal.aborted) setError(e.message)})
      .finally(() => {if (!controller.signal.aborted) {setLoading(false); api<Record<string,{status:string}>>('/status').then(setSources).catch(()=>{})}})
    }
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

  async function toggleMonitor(asset:Asset) {
    setFormError('')
    try {
      const updated = await api<Asset>('/assets/monitor',{method:'PUT',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({symbol:asset.symbol,enabled:!asset.enabled})})
      setAssets(items=>items.map(item=>item.symbol===updated.symbol ? updated : item))
    } catch(e) {setFormError((e as Error).message)}
  }

  async function saveLocalIntegration(event:FormEvent<HTMLFormElement>, integration:Integration) {
    event.preventDefault()
    const element = event.currentTarget
    const form = new FormData(element)
    const fields = integration === 'ai' ? ['provider','endpoint','model','credential'] :
      integration === 'telegram' ? ['credential','chat'] : ['credential']
    const clear = (event.nativeEvent as SubmitEvent).submitter?.getAttribute('value') === 'clear'
    setSettingsError('')
    try {
      setSettings(await api<Settings>('/settings/local-integration',{method:'PUT',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({integration,values:fields.map(key=>String(form.get(key) ?? '')),clear})}))
      element.reset()
    } catch(e) {setSettingsError((e as Error).message)}
  }

  async function editFeed(url:string, remove=false) {
    if (!settings) return
    setSettingsError('')
    const urls = remove ? settings.feeds.allowed.filter(item=>item!==url) : [...settings.feeds.allowed, url]
    try {
      setSettings(await api<Settings>('/settings/feed-catalog',{method:'PUT',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({urls})}))
    } catch(e) {setSettingsError((e as Error).message)}
  }

  async function saveStrategy(event:FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setStrategySaved(false)
    setSettingsError('')
    const strategy = {
      window:Number(form.get('window')), volume_min:Number(form.get('volume_min')),
      max_stop_atr:Number(form.get('max_stop_atr')), macro_pause_minutes:Number(form.get('macro_pause_minutes')),
      require_sweep:form.has('require_sweep'), require_fvg:form.has('require_fvg'),
    }
    try {
      setSettings(await api<Settings>('/settings/strategy',{method:'PUT',headers:{'Content-Type':'application/json'},
        body:JSON.stringify(strategy)}))
      setStrategySaved(true)
    } catch(e) {setSettingsError((e as Error).message)}
  }

  async function runSimulation(event:FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const params = new URLSearchParams({symbol})
    for (const input of ['interval','count','fee_bps','slippage_bps']) params.set(input, String(form.get(input)))
    setSimulationError('')
    setSimulationBusy(true)
    try {
      const report = await api<Simulation>('/backtest?'+params,{method:'POST'})
      setSimulation(report)
      setSaved(items=>[report,...items].slice(0,30))
    } catch(e) {setSimulationError((e as Error).message)}
    finally {setSimulationBusy(false)}
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
        <h2>Resumen del mercado</h2>
        {assets.length ? assets.map(asset=>{
          const latest = overview.find(item=>item.asset.symbol===asset.symbol)?.latest
          return <p key={asset.symbol}>
            <button onClick={()=>setSymbol(asset.symbol)}>{asset.symbol}</button>
            {' '}{latest ? <span>{latest.price} · {latest.trends?.['4h'] ?? '4h sin datos'}<br/>{dateTime(latest.observed_at)}</span> : <span>Sin observaciones</span>}
            <br/><label><input type="checkbox" checked={asset.enabled} onChange={()=>void toggleMonitor(asset)}/> Vigilar</label>
          </p>
        }) : <p>Sin activos vigilados.</p>}
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
        <h2>Seguimiento simulado de alertas en vivo</h2>
        {forward?.count ? <>
          <p>Últimas {forward.count} evaluadas · {forward.positive} positivas · Expectativa {((forward.expectancy ?? 0)*100).toFixed(2)} %</p>
          <details><summary>Ver resultados</summary>{forward.items.slice(0,20).map(item=>
            <p key={item.observed_at}>{dateTime(item.observed_at)} · {item.direction} · {(item.net_return*100).toFixed(2)} % simulado</p>)}</details>
        </> : <p>Sin alertas con una vela posterior evaluable.</p>}
        <h2>Historial de decisiones</h2>{history.filter(signal=>signal.symbol===symbol).slice(0,30)
          .map(signal=><Signal key={signal.observed_at} signal={signal}/>)}
      </article>
      <article className="panel"><h2>Simulación histórica</h2>
        <form onSubmit={runSimulation}>
          <label>Temporalidad <select name="interval" defaultValue="15m">{timeframes.filter(frame=>frame!=='1w').map(frame=><option key={frame}>{frame}</option>)}</select></label>
          <label>Velas <input name="count" type="number" min={300} max={5000} defaultValue={3000} required/></label>
          <label>Comisión (pb) <input name="fee_bps" type="number" min={0} max={500} step=".1" defaultValue={10} required/></label>
          <label>Deslizamiento (pb) <input name="slippage_bps" type="number" min={0} max={500} step=".1" defaultValue={5} required/></label>
          <button disabled={!symbol || simulationBusy}>{simulationBusy ? 'Simulando…' : 'Ejecutar'}</button>
        </form>{simulationError && <p role="alert">{simulationError}</p>}{simulation && <dl>{Object.entries(simulation).filter(([,value])=>value == null || typeof value !== 'object').map(([key,value])=><div key={key}><dt>{key}</dt><dd>{typeof value === 'number' ? Number(value.toFixed(4)) : String(value ?? '—')}</dd></div>)}</dl>}
        {!!saved.length && <label>Resultados guardados <select value={simulation?.id ?? ''} onChange={e=>setSimulation(saved.find(item=>item.id===e.target.value))}>
          <option value="">Seleccionar simulación</option>
          {saved.map(item=><option key={item.id} value={item.id}>{item.timeframe} · {dateTime(item.created_at)}</option>)}
        </select></label>}
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
      <h2>Calendario macroeconómico</h2>
      {calendar.error && <p>Calendario BLS indisponible · {calendar.error}</p>}
      {calendar.items.length ? calendar.items.slice(0,8).map(item=><p key={item.title+item.starts_at}>
        <a href={item.url} target="_blank" rel="noreferrer">{item.title}</a><br/>{dateTime(item.starts_at)} · {item.source}
      </p>) : <p>Sin publicaciones próximas disponibles</p>}
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
        {settings.local_configuration && <details>
          <summary>Configurar IA y credenciales de notificaciones</summary>
          <form onSubmit={event=>void saveLocalIntegration(event,'ai')}>
            <label>Proveedor <select name="provider" defaultValue={settings.ai.provider}>
              <option value="off">Desactivado</option><option value="ollama">Ollama</option>
              <option value="openai-compatible">API compatible con OpenAI</option>
            </select></label>
            <label>URL del modelo <input name="endpoint" type="url" placeholder="http://127.0.0.1:11434"/></label>
            <label>Modelo <input name="model" defaultValue={settings.ai.model ?? ''}/></label>
            <label>Token opcional <input name="credential" type="password" autoComplete="new-password"/></label>
            <button>Guardar IA</button><button value="clear" formNoValidate>Quitar credenciales de IA</button>
          </form>
          <form onSubmit={event=>void saveLocalIntegration(event,'discord')}>
            <label>Webhook de Discord <input name="credential" type="password" autoComplete="new-password" required/></label>
            <button>Guardar Discord</button><button value="clear" formNoValidate>Quitar Discord</button>
          </form>
          <form onSubmit={event=>void saveLocalIntegration(event,'telegram')}>
            <label>Token del bot <input name="credential" type="password" autoComplete="new-password" required/></label>
            <label>ID del chat <input name="chat" required/></label>
            <button>Guardar Telegram</button><button value="clear" formNoValidate>Quitar Telegram</button>
          </form>
        </details>}
        <h3>Reglas de alertas y simulación</h3>
        <form key={JSON.stringify(settings.strategy)} onSubmit={saveStrategy}>
          <label>Ventana de ruptura en velas <input name="window" type="number" min={1} max={50} defaultValue={settings.strategy.window} required/></label>
          <label>Volumen relativo mínimo <input name="volume_min" type="number" min={0} max={20} step=".1" defaultValue={settings.strategy.volume_min} required/></label>
          <label><input name="require_sweep" type="checkbox" defaultChecked={settings.strategy.require_sweep}/> Exigir barrido</label>
          <label><input name="require_fvg" type="checkbox" defaultChecked={settings.strategy.require_fvg}/> Exigir FVG abierto en 5m</label>
          <label>Distancia máxima en ATR (0 desactiva) <input name="max_stop_atr" type="number" min={0} max={20} step=".1" defaultValue={settings.strategy.max_stop_atr} required/></label>
          <label>Pausa ante publicaciones BLS en minutos (0 desactiva) <input name="macro_pause_minutes" type="number" min={0} max={180} defaultValue={settings.strategy.macro_pause_minutes} required/></label>
          <button>Guardar reglas</button>{strategySaved && <p role="status">Reglas guardadas</p>}
        </form>
        <h3>Fuentes de noticias</h3>
        {settings.feeds.editable && <form onSubmit={event=>{
          event.preventDefault()
          const url = String(new FormData(event.currentTarget).get('feed')).trim()
          void editFeed(url)
        }}>
          <label>URL pública RSS o Atom <input name="feed" type="url" required placeholder="https://…"/></label>
          <button>Añadir fuente</button>
        </form>}
        {settings.feeds.allowed.length ? settings.feeds.allowed.map(url=><p key={url}><label>
          <input type="checkbox" checked={settings.feeds.enabled.includes(url)} onChange={e=>void updateFeed(url,e.target.checked)}/> {url}
        </label>{settings.feeds.editable && <button onClick={()=>void editFeed(url,true)}>Quitar</button>}</p>) : <p>Configura fuentes autorizadas en el servidor.</p>}
      </>}
    </section>
  </main>
}
function setIntervalGlobal(fn:()=>void) {return window.setInterval(fn,30000)}
createRoot(document.getElementById('root')!).render(<App/>)
