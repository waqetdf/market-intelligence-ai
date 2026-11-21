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
  `libxcb-cursor0`, `libxkbcommon-x11-0`, `libnss3` y `libasound2t64`.

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

Mientras la ventana siga abierta, el monitor continúa trabajando aunque
la minimices. Al salir o suspender el equipo se interrumpe la vigilancia.
Para respaldar datos locales, cierra la app y copia su carpeta de datos.
Contiene los secretos de integraciones si creaste un archivo `.env`.

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
uv run --locked --group desktop pyinstaller --noconfirm --windowed --name MarketIntelligenceAI --add-data frontend/dist:frontend/dist desktop.py
```

El resultado está en `dist/MarketIntelligenceAI/`. La ventana se comunica
con el motor integrado mediante un puerto dinámico de loopback y un token
aleatorio por ejecución. El proceso cierra el motor al salir.
