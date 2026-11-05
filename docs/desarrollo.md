# Mantener y validar el plugin

Los usuarios de agentes deben seguir la [guía de uso](guia-de-uso.md). Esta página es para mantener el repositorio del plugin.

## Estructura y cambios

- `.agents/plugins/marketplace.json`: catálogo instalable en Codex.
- `plugins/langchain-skills-codex/.codex-plugin/plugin.json`: identidad, versión, skills e iconos.
- `plugins/langchain-skills-codex/scripts/aidp_agent_flow/`: motor CLI y plantillas.
- `plugins/langchain-skills-codex/scripts/tests/`: suite de regresión existente.
- `docs/` y `examples/`: tutorial público y corpus sintético.

No desarrolles sobre el caché instalado ni sustituyas un motor que una campaña está ejecutando. Usa una rama, conserva los recibos y valida la adopción de la siguiente versión por cada proyecto. Una actualización de skills no actualiza librerías en AIDP.

El motor calcula su identidad con los bytes de sus archivos Python. `.gitattributes` conserva esos bytes para evitar que Git cambie su identidad solo por convertir saltos de línea al clonar. Las ediciones funcionales posteriores sí requieren una nueva revisión y adopción verificable.

## Un recorrido de validación

Desde la raíz del repositorio, con Python 3.11 y `uv` instalados:

```powershell
$Repo = (Get-Location).Path
uv sync --directory "$Repo/plugins/langchain-skills-codex" --dev --locked
$Python = Join-Path $Repo 'plugins/langchain-skills-codex/.venv/Scripts/python.exe'
& $Python "$Repo/scripts/validate.py"
```

El validador comprueba manifiestos, rutas de skills e iconos, hashes upstream, contratos del corpus y enlaces locales de la guía. Después prepara `plugins/validation-work` y ejecuta las pruebas existentes con el mismo Python. Son pruebas locales con servicios simulados; no habilitan llamadas a OCI ni publicaciones.

En Linux/macOS usa `.venv/bin/python`. Para una edición solo documental puedes ejecutar `scripts/validate.py --package-only`. También revisa `git diff --check`. Esta comprobación de enlaces valida archivos locales, no la disponibilidad de URLs externas ni anclas HTML.

Antes y después de cambios de código o estructura, usa Sentrux instalado por tu entorno de desarrollo:

```powershell
./scripts/arch-preflight.ps1
# Realizar el cambio y ejecutar scripts/validate.py.
./scripts/arch-postflight.ps1
```

Ambos scripts aceptan `-SentruxCommand 'ruta/al/ejecutable'`. No hay reglas Sentrux locales ni grafo Graphify. El baseline se guarda localmente y queda fuera de Git: conserva el resultado antes del cambio para poder compararlo después. No reinicies el baseline para ocultar una regresión.

Para construir el paquete Python:

```powershell
uv build --wheel --out-dir "$Repo/.validation/dist" "$Repo/plugins/langchain-skills-codex"
```

## Antes de publicar

Ejecuta además el ejemplo inicial de la guía en un proyecto nuevo. Comprueba qué revisión y entorno produjo los recibos. Revisa los archivos que Git enviará: nunca deben incluir `.oci`, claves, entornos, resultados privados, enlaces internos o datos de proyectos reales.

Actualiza versión de manifiesto y paquete de manera coherente cuando cambie el motor. Mantén licencia y hashes upstream, registra limitaciones en las notas de versión y publica un tag reproducible. Los controles locales no certifican un runtime Oracle ni reemplazan la aceptación de TEST y Agent Hub cuando cambia el comportamiento nativo.
