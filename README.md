# FSR-KingSteam

Plugin de Decky que instala OptiScaler y aplica FSR 4 (INT8 Lite, INT8, versiones de comunidad) o XeSS a juegos de Steam y a juegos fuera de Steam, escribiendo las opciones de lanzamiento por ti.

## Qué hace

- Un solo desplegable con los juegos de Steam y los accesos directos (non-Steam). Para un juego que no está en la lista, eliges su `.exe` y se le crea la entrada en Steam.
- Detecta la carpeta del `.exe` real o te deja elegirla, y pone las opciones de lanzamiento sin tocar las tuyas (vuelven al quitar el parche).
- Cambio de modelo por juego sin reparchear, overlay de FPS grande con la relación de escalado, y "¿Funciona?" que lee el log de OptiScaler.
- "Quitar parche" restaura los archivos originales. Si cambiaste a mano un archivo parcheado (un fix, por ejemplo) no se toca nunca.
- Avisa de anticheat y de versiones de Proton que pueden quedarse cortas.
- Interfaz y mensajes en español o inglés según el idioma de Steam.

No lo uses en partidas online con anticheat (riesgo de baneo). Prueba primero en un juego offline.

## Cómo está hecho

- `main.py`: entrada de Decky, solo reparte llamadas.
- `py_modules/kingsteam/`: toda la lógica (Steam, carpetas, parcheador transaccional, instalación del runtime, diagnóstico).
- `src/`: interfaz en React/TypeScript.
- `data/runtime-assets.json`: versiones fijadas con su SHA-256 y los preajustes de FSR.
- Las DLL de AMD no se redistribuyen: se descargan de AMD en el dispositivo la primera vez y se comprueba su hash.
- Los juegos parcheados con la versión 1.0.x se reconocen y se pueden gestionar desde aquí.

## Desarrollo

```
pnpm install
pnpm run build
pnpm test
python3 scripts/package.py   # necesita bin/ con los archivos de OptiScaler fijados
```

## Licencia

MIT para el código propio. Avisos y licencias de terceros en `THIRD_PARTY.md` y `licenses/`.
