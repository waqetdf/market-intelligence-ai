# Reglas del motor

Cada vela se representa con sus instantes de apertura y cierre UTC. Un pivote
requiere un extremo estricto frente a dos velas anteriores y dos posteriores.
Se confirma al cierre de la segunda vela posterior. HH/LH y HL/LL comparan
pivotes consecutivos del mismo tipo. La tolerancia relativa para máximos y
mínimos iguales es 0,1 %. Ambos parámetros son argumentos de `analyze`.

Un cierre que excede el último pivote confirmado marca una ruptura. Se etiqueta
BOS si mantiene la dirección o establece la primera y CHoCH si la invierte.
Un CHoCH con cuerpo superior al rango medio de las 14 barras anteriores
también recibe MSS. Una mecha que atraviesa el nivel y cierra dentro marca
un barrido. La resistencia y el soporte corresponden a los pivotes más
recientes. Su punto medio divide el rango en dos mitades.

Un FVG alcista existe cuando el mínimo de la tercera vela supera el máximo de
la primera. El bajista usa la desigualdad inversa. El primer solapamiento
posterior lo marca mitigado. Un cierre más allá del extremo opuesto lo invalida
y genera IFVG. El gráfico dibuja los niveles de los ocho últimos eventos
BOS, CHoCH y FVG.

SMA y Bollinger usan 20 cierres y dos desviaciones estándar poblacionales.
EMA usa el primer cierre como semilla y ponderación 2/(N+1). MACD utiliza
12, 26 y una señal EMA de 9. RSI y ATR usan ventanas simples de 14. VWAP
se calcula en la ventana cargada, ponderando el precio típico por volumen.
MT5 usa volumen de ticks. El volumen relativo compara la última vela con la
media de las 20 anteriores.

La señal inicial requiere una ruptura reciente en 15m, tendencia concordante en
4h, volumen relativo mínimo de 1 y un pivote válido como invalidación. Usa
solo contexto superior cerrado al momento de la señal. El objetivo opcional
es el pivote superior más cercano que queda en la dirección de la señal.

La simulación entra en la apertura siguiente y sale a su cierre. Resta
comisiones y deslizamiento de ida y vuelta y no utiliza objetivos ni niveles
de invalidación para simular la salida. Las métricas son descriptivas del
histórico cargado. Cuando hay al menos 20 barras evaluables, separa el último cuarto como
tramo de reserva e informa tres ventanas cronológicas con historia
creciente. Las reglas son fijas y no se optimizan en cada ventana.
La calibración de confianza sigue pendiente.

Para detectar un Order Block se toma el rango de la última vela contraria
entre las diez anteriores a un BOS o CHoCH. El primer solapamiento posterior
marca Mitigation Block. Un cierre por el lado opuesto del rango lo invalida
y marca Breaker Block. Son definiciones operativas de esta implementación.
La liquidez compradora y vendedora se representa mediante el último swing
alto y bajo confirmado.

El monitor consulta las ocho temporalidades, limita a tres las solicitudes
simultáneas y descarta contexto posterior al cierre evaluado o con dos
periodos de antigüedad. Persiste también «sin señal» por activo y cierre de
15 minutos. El contexto adicional muestra FVG abiertos y barridos concordantes,
distancia en ATR y tendencias contrarias en 1h, 1d o 1w. El volumen mínimo y
la ventana de rupturas se configuran con `MARKET_RELATIVE_VOLUME_MIN` y
`MARKET_STRUCTURE_WINDOW`. Se omite la puntuación hasta disponer de calibración.

El backtest admite de 300 a 5.000 velas de 15m, costes configurables en
puntos básicos y deduplicación por ruptura. Omite huecos entre decisión y
entrada y contextos de 4h desactualizados. Para precision y recall, la
etiqueta de referencia es el signo del retorno apertura-cierre de la vela
siguiente si su magnitud supera el coste redondo. Una alerta en sentido
equivocado cuenta como falso positivo y oportunidad omitida. Las velas sin
alerta forman parte del denominador del recall. Estas etiquetas describen
la prueba de una vela y no calibran la probabilidad de nuevas señales.

Los pivotes provisionales se devuelven por separado y nunca se usan en
señales. Un cierre de vuelta al nivel roto en una de las tres velas
siguientes confirma una falsa ruptura. Cada evento publica la hora real
de confirmación en `confirmed_at`. Premium corresponde al intervalo entre
el punto medio y el swing alto, y Discount entre el swing bajo y el punto
medio, cuando el rango es válido. El FVG de tres velas es la definición de
desequilibrio empleada. El radio de pivote y la tolerancia de igualdad se
configuran con `MARKET_SWING_RADIUS` y `MARKET_EQUAL_TOLERANCE`, y el umbral
MSS y la ventana Order Block con `MARKET_MSS_RANGE_MULTIPLE` y
`MARKET_BLOCK_LOOKBACK`.

El monitor y el backtest evalúan cada marco de la regla principal con
hasta 150 velas previas cerradas. Una ruptura declarada falsa antes o en
el cierre evaluado deja de ser elegible como disparador.

Para comprobar el contrato del proveedor y la causalidad sobre velas
históricas reales de BTC/USDT, ejecuta desde la raíz:

```bash
MARKET_LIVE_TEST=1 uv run --locked python -m pytest -q
```

La prueba usa un corte UTC fijo y compara las confirmaciones obtenidas
en los prefijos con las del histórico completo. La CI habitual se puede
ejecutar sin llamadas al proveedor.

Las solicitudes del proceso a Binance se espacian al menos 200 ms,
incluida la paginación del backtest. El panel reutiliza una caché breve
de velas, y consulta el estado y los resultados cada 30 segundos.

## Reglas y evaluación en escritorio

La estrategia editable usa valores cerrados y compartidos entre el escaneo
de 15m y el backtest. El umbral ATR acota la distancia al nivel de
invalidación. El barrido debe haberse confirmado en la ventana de ruptura,
en la misma dirección. El FVG adicional de 5m debe estar abierto en el
instante de decisión. La simulación habilita esa condición entre 1m y 30m.
Una pausa macro opcional bloquea nuevas alertas alrededor de CPI, PPI,
Employment Situation y JOLTS del calendario oficial del BLS. Si el
calendario falla y se exige la pausa, el monitor se abstiene. El backtest
usa datos de precio y volumen, y declara que excluye el calendario, las
noticias y el modelo.

La etiqueta de respaldo solo utiliza una simulación guardada del mismo
activo, marco y configuración, creada antes de la alerta. Con menos de 50
señales en reserva se informa muestra insuficiente. Por encima de ese
umbral, la etiqueta preliminar requiere expectativa neta positiva y
un límite inferior de Wilson al 95 % por encima del 50 % de precisión.
Es una comprobación exploratoria, ya que puede haber dependencia entre
observaciones. La condición macro activa impide aplicar esta etiqueta.

El seguimiento en vivo conserva por separado el resultado simulado de la
primera vela posterior de cada alerta. Usa apertura y cierre de esa vela,
con 10 pb de comisión y 5 pb de deslizamiento por lado. Si falta esa vela,
la alerta no se puntúa. La vista calcula resultados sobre las últimas 100
evaluaciones disponibles.

Los períodos RSI, ATR, EMA/SMA, volumen de referencia y MACD, y el ancho
de Bollinger se pueden ajustar con las variables de [.env.example](../.env.example).
La ventana de falsa ruptura, la referencia del desplazamiento MSS y la
amplitud mínima relativa del FVG también son configurables. El ancho mínimo
compara la separación entre las dos sombras externas con el valor
absoluto del borde de la primera vela. Los períodos deben dejar un tramo
evaluable dentro de las 150 velas de la estrategia. Las líneas EMA, SMA,
VWAP acumulado y Bollinger del gráfico se construyen con prefijos
cronológicos y pueden activarse individualmente.
