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
