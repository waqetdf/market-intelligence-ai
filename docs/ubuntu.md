# Despliegue en Ubuntu Server

1. Instala Git, OpenSSL y [Docker Engine con el complemento Compose](https://docs.docker.com/engine/install/ubuntu/). Habilita el servicio con `sudo systemctl enable --now docker`.
2. Clona el repositorio en `/opt/market-intelligence-ai` o en una carpeta de tu usuario. Desde esa carpeta ejecuta `bash infrastructure/scripts/install.sh`. Conserva `.env` con permisos 600. Las credenciales de PostgreSQL se aplican al crear el volumen por primera vez. Para reutilizar un volumen existente, usa su contraseña original.
3. Abre `http://127.0.0.1:8000` desde el servidor o a través de un túnel SSH. Usa `MARKET_USER` y `MARKET_PASSWORD` para entrar y añade un activo con su ticker real. `docker compose ps` muestra el estado de ambos servicios y `docker compose logs --tail=100 app` muestra los ciclos y fallos.
4. Para la LAN, mantén el enlace de Compose en loopback y configura un proxy inverso HTTPS en el mismo Ubuntu. Un ejemplo de Caddy para una LAN con DNS local es:

   ```caddyfile
   mercado.home.arpa {
       tls internal
       reverse_proxy 127.0.0.1:8000
   }
   ```

   Resuelve el nombre al IP LAN del servidor, permite HTTPS en el cortafuegos desde tu subred e instala la CA local de Caddy en los clientes. Para acceso por internet, emplea una VPN o un túnel autenticado y conserva la autenticación del panel. Evita exponer el puerto de Compose o PostgreSQL.
5. Para Ollama en el host, configura su escucha en una interfaz accesible desde la red de Docker y limita el puerto 11434 a esa red. Usa `MARKET_AI_PROVIDER=ollama`, `MARKET_AI_URL=http://host.docker.internal:11434` y el nombre de un modelo ya descargado. Con IA externa configura el proveedor compatible con OpenAI y su endpoint HTTPS. Los ajustes de proveedor y credenciales se aplican con `docker compose up -d`.
6. Para copias diarias, ajusta `WorkingDirectory` de la unidad al directorio clonado e instala las unidades:

   ```bash
   sudo install -m 644 infrastructure/systemd/market-backup.{service,timer} /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now market-backup.timer
   ```

   Puedes hacer una copia bajo demanda con `bash infrastructure/scripts/backup.sh`. Conserva copias cifradas fuera del equipo y comprueba su restauración en una base de datos aislada. El volcado contiene activos, decisiones, alertas y ajustes. Guarda por separado los CSV y `.env`.
7. Actualiza desde la rama que sigue GitHub con `bash infrastructure/scripts/update.sh`. El script exige que los archivos versionados estén limpios, genera primero una copia y aplica solo cambios fast-forward.
