# Market Intelligence AI

Observatorio multiactivo en español con gráficos, análisis causal de velas y
alertas informativas. El dossier AURUM AI sirve de referencia para incorporar
XAUUSD y otros activos de MT5 por CSV. El backend también acepta símbolos
de Binance Spot. La elección de símbolo y proveedor se hace en el panel.

## Desarrollo en la nube

Requiere Python 3.12, uv y Node 24. Desde la raíz:

```bash
UV_CACHE_DIR=/tmp/market-uv uv sync --locked
npm --cache /tmp/market-npm --prefix frontend ci
UV_CACHE_DIR=/tmp/market-uv uv run --locked python -m pytest -q
npm --cache /tmp/market-npm --prefix frontend run build
UV_CACHE_DIR=/tmp/market-uv uv run --locked uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

Abre el puerto 8000. `GET /health` comprueba el arranque. Para editar el panel
en vivo, ejecuta también `npm --prefix frontend run dev` y abre el 5173.
El desarrollo local utiliza SQLite en `data/` y el despliegue usa PostgreSQL.

Para cripto, añade por ejemplo `BTC/USDT` con Binance Spot y ticker
`BTCUSDT`. Se requiere acceso a `data-api.binance.vision`.

## Datos de XAUUSD y otros símbolos de MT5

En Windows, abre MT5 con la sesión del proveedor iniciada y localiza el
símbolo exacto en Observación del mercado. Instala `MetaTrader5` para Python
3.12 y ejecuta, ajustando símbolo y carpeta de destino:

```powershell
py -3.12 -m pip install MetaTrader5
py -3.12 infrastructure/scripts/export_mt5.py --symbol XAUUSD --alias XAUUSD --output C:\MarketData
```

Copia los CSV a `data/mt5/`, o configura una transferencia periódica desde un
Windows en funcionamiento. También se aceptan las carpetas `scan_*_UTC`
del recolector del dossier. Añade `XAUUSD` en el panel con proveedor
MetaTrader 5 CSV y prefijo `XAUUSD`. Repite con cualquier otro instrumento
que ofrezca tu terminal. Los CSV deben incluir `time_utc` con zona horaria,
`open`, `high`, `low`, `close` y `tick_volume`.

## Servidor Ubuntu

Instala Docker Engine con Docker Compose v2 desde sus paquetes oficiales,
Git y OpenSSL. Clona el repositorio en el servidor y ejecuta
`bash infrastructure/scripts/install.sh`. El instalador genera contraseñas
locales en `.env` si el archivo aún no existe. Habilita Docker al arranque con
`sudo systemctl enable --now docker`. Compose reinicia los servicios según
la política `unless-stopped`.

El puerto queda en loopback. Para acceso desde la LAN o a distancia, sirve
la aplicación a través de HTTPS con un proxy en el servidor, o accede por un
túnel autenticado. Usa la cuenta y contraseña de `.env` para la API.
`infrastructure/scripts/backup.sh` crea una copia de PostgreSQL en
`backups/`. `infrastructure/scripts/update.sh` genera una copia y aplica
una actualización Git fast-forward antes de reconstruir.

## Integraciones opcionales

- `MARKET_NEWS_FEEDS` recibe URLs HTTPS de fuentes autorizadas separadas por comas.
- `MARKET_AI_PROVIDER=ollama` usa `MARKET_AI_URL` y `MARKET_AI_MODEL`. Para un API
  compatible con OpenAI usa `openai-compatible`, una URL base HTTPS que
  incluya la versión si corresponde y `MARKET_AI_TOKEN` si requiere autenticación.
  El resumen es orientativo y las alertas deterministas siguen disponibles.
- Para notificaciones, añade `DISCORD_WEBHOOK_URL` o el par
  `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` a `.env`. Se registra cada
  alerta de forma persistente y se intenta su envío una vez.

Consulta [las reglas del motor](docs/technical.md) para interpretar el análisis
y la simulación.

Si Docker se construye detrás de un proxy TLS corporativo, proporciona
su cadena de confianza mediante el secreto de compilación BuildKit
`build_ca`. El Dockerfile la usa solo durante la instalación y conserva
la verificación de TLS.

El monitor actualiza los RSS cada cinco minutos. El administrador puede
habilitar o retirar desde el panel las URLs declaradas en `MARKET_NEWS_FEEDS`.
El listado del servidor limita qué destinos puede consultar el backend.
El análisis vincula titulares por símbolo o evento macro, etiqueta el
sentimiento léxico y compara cierres observados antes y después. La etiqueta
«titular sin verificar» conserva la distinción entre lo publicado y lo
confirmado de forma independiente. Los titulares no determinan la dirección.

El modelo solo puede proponer una clasificación de sentimiento y contexto
con referencias a titulares ya recogidos. El servidor valida los índices
y construye la explicación con textos controlados y las fuentes originales.
Una respuesta inválida o una caída del modelo deja disponible todo el
análisis determinista.

La [guía de Ubuntu](docs/ubuntu.md) desarrolla el acceso HTTPS por LAN,
la conexión con Ollama en el host y la activación de copias diarias con
systemd. Una instalación nueva incluye los RSS oficiales de la Reserva
Federal y el BCE. Las demás fuentes requieren un endpoint autorizado
configurado por el operador.
