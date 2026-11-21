# Market Intelligence AI para escritorio

La aplicación se abre en una ventana propia. Incluye el motor de análisis,
el panel y SQLite. Solo necesita internet para consultar proveedores y
enviar notificaciones configuradas.

## Ejecutar el paquete

En [GitHub Actions](https://github.com/waqetdf/market-intelligence-ai/actions/workflows/desktop.yml),
abre una ejecución correcta de la rama `main` y descarga el artefacto
de tu sistema. GitHub solicita iniciar sesión para descargar artefactos.
Extrae también el ZIP o TAR.GZ incluido y conserva juntos los archivos
de la carpeta `MarketIntelligenceAI`.

- **Windows x64**. Abre `MarketIntelligenceAI.exe`.
- **Linux x64**. El paquete se compila para Ubuntu 24.04. Desde la carpeta
  extraída ejecuta `./MarketIntelligenceAI`. Si tu instalación de Ubuntu
  carece de bibliotecas gráficas de Qt o Chromium, instala
  `libegl1`, `libgl1`, `libgbm1`, `libxcb-cursor0`,
  `libxkbcommon-x11-0`, `libnss3` y `libasound2t64`.

Los paquetes son portátiles y se distribuyen sin firma de código.
Actualiza descargando una compilación nueva y sustituyendo los archivos
de la aplicación. Los datos del usuario se guardan fuera de esa carpeta.

## Datos e integraciones

En **Archivo → Abrir carpeta de datos** encontrarás la base `market.db`,
la carpeta `mt5` y el registro de la aplicación. Copia los CSV de MT5 a esa
carpeta y registra el activo en la ventana. Para Binance, por ejemplo,
añade `BTC/USDT` con el ticker `BTCUSDT`.

Para configurar Ollama, una API externa, fuentes RSS o canales de alerta,
crea un archivo `.env` en la carpeta de datos con las variables
correspondientes de [.env.example](../.env.example) y vuelve a abrir la
aplicación. Un Ollama local puede usar `http://127.0.0.1:11434`.
El escritorio crea su propia base SQLite. Los datos de instalaciones
PostgreSQL requieren una migración aparte.

La bandeja del sistema mantiene el monitor activo al cerrar la ventana y
muestra notificaciones nativas cuando el sistema admite bandeja. Usa **Salir**
en Archivo o en la bandeja para detener el motor. En escritorios sin bandeja,
minimiza la ventana para mantenerla activa. El equipo debe seguir encendido.

**Archivo → Crear copia de la base de datos** genera un archivo SQLite
consistente en `backups`. La aplicación guarda además una copia automática
por día UTC de uso y conserva las últimas 14. Para restaurar, sal de la app,
preserva el `market.db` actual y copia la instantánea seleccionada como
`market.db`. Conserva por separado los CSV y el archivo de secretos.

## Estrategia y resultados

Desde Configuración puedes ajustar la ventana de ruptura, exigir un barrido
o un FVG abierto en 5m, filtrar por volumen o distancia en ATR y pausar
señales alrededor de publicaciones oficiales del BLS. Añade o retira RSS
públicos autorizados en la misma sección. Mantén las credenciales del
proveedor en el archivo de configuración local.

La ventana separa el historial de decisiones, las simulaciones históricas
guardadas por activo y temporalidad y el seguimiento simulado de alertas
generadas en vivo. En todos los casos el usuario decide si opera por su cuenta.


## Ejecutar desde el código fuente

Con Python 3.12, uv y Node 24 instalados, ejecuta desde la raíz:

```bash
uv sync --locked --group desktop
npm ci --prefix frontend
npm run build --prefix frontend
uv run --locked --group desktop python desktop.py
```

Para compilar un paquete en el propio sistema de destino:

```bash
uv run --locked --group desktop pyinstaller --noconfirm --windowed --name MarketIntelligenceAI --collect-data tzdata --add-data frontend/dist:frontend/dist desktop.py
```

El resultado está en `dist/MarketIntelligenceAI/`. La ventana se comunica
con el motor integrado mediante un puerto dinámico de loopback y un token
aleatorio por ejecución. El proceso cierra el motor al salir.
