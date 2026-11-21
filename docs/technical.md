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
