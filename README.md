# OCI AIDP Agent Flow LangGraph para Codex

Plugin **0.4.8** para crear, auditar y mejorar agentes LangGraph destinados a Oracle AI Data Platform (AIDP). Incluye skills para Codex y un CLI Python para preparar proyectos, probar nodos y recorridos, registrar evidencia y operar el ciclo nativo autorizado.

**La forma de trabajo es:** definir el resultado esperado → desarrollar y probar localmente → aceptar la revisión en AIDP TEST → publicar esa revisión → registrar y comprobar el acceso en Agent Hub.

Este repositorio sigue la distribución de [AIDP Migration Workbench](https://github.com/jgangini/codex-plugin-oci-aidp-migration-workbench): marketplace en `.agents/plugins/`, paquete en `plugins/`, documentación y scripts de validación. La identidad interna se conserva como `langchain-skills-codex`; el nombre visible es **AIDP Agent Flow LangGraph**.

## Empieza aquí

| Quiero… | Documento |
| --- | --- |
| Instalar y ejecutar mi primera prueba | [Guía paso a paso](docs/guia-de-uso.md) |
| Preparar `.oci/config` y `.oci/key.pem` | [Credenciales y prerrequisitos](docs/prerrequisitos.md) |
| Diseñar preguntas, corpus y criterios | [Corpus y pruebas](docs/corpus-y-pruebas.md) |
| Pedir a Codex que cree o mejore un agente | [Prompts para copiar](docs/prompts.md) |
| Entender los cambios y límites de 0.4.8 | [Notas de versión](docs/releases/v0.4.8.md) |
| Mantener o contribuir al plugin | [Desarrollo del plugin](docs/desarrollo.md) |

## Instalación en Codex

Con una versión de Codex que incluya `plugin marketplace`:

```powershell
codex plugin marketplace add jgangini/codex-plugin-oci-aidp-agent-flow-langgraph
```

Para fijar la versión publicada:

```powershell
codex plugin marketplace add jgangini/codex-plugin-oci-aidp-agent-flow-langgraph@v0.4.8
```

En Codex abre la lista de plugins, instala **AIDP Agent Flow LangGraph** y comienza un chat nuevo para cargar sus skills. Si ya usas una instalación local del mismo plugin, elige una sola procedencia para evitar instrucciones duplicadas. No cambies el motor de una campaña activa sin revisar su adopción.

Para actualizar un marketplace no fijado a un tag:

```powershell
codex plugin marketplace upgrade oci-aidp-agent-flow-langgraph
```

Instalar las skills no instala automáticamente el CLI, no crea recursos OCI y no cambia agentes existentes. El [tutorial](docs/guia-de-uso.md) explica la instalación separada del motor.

## Qué necesitas

- Codex con plugins, Git, `uv` y Python 3.11 o superior.
- Para pruebas simuladas locales: **no necesitas cuenta OCI ni claves**.
- Para modelos reales y operaciones AIDP: una identidad OCI autorizada, recursos de destino y la carpeta privada del proyecto **`.oci/` con `config` y `key.pem`**. La clave pública correspondiente debe estar registrada en OCI.
- Para TEST nativo: workspace, AI Compute compatible y permisos para el agente seleccionado. El plugin no crea toda esa infraestructura al instalarse.

Nunca subas `.oci`, claves ni recibos privados a GitHub. Este repositorio contiene ejemplos ficticios, no credenciales.

## Skills, en orden de trabajo

| Skill | Para qué sirve |
| --- | --- |
| `aidp-agent-bootstrap` | Preparar o reparar entorno, identidad y configuración |
| `aidp-agent-flow-langgraph` | Diseñar, implementar y ajustar el agente |
| `aidp-langgraph-test` | AIDP Agent Flow Test: aislar fallos y probar nodos, recorridos y comportamiento |
| `aidp-runtime-credentials` | Inspeccionar y preparar Credential Store dentro del alcance autorizado |
| Cinco skills upstream de LangChain/LangGraph | Dependencias, fundamentos, intervención humana y persistencia |

## Qué demuestra una prueba

Un fixture aprobado demuestra las propiedades comprobadas con datos grabados. Una prueba con un modelo real demuestra ese caso con esa configuración. Una respuesta HTTP exitosa no demuestra que el agente resuelva la necesidad del usuario. La aceptación nativa TEST y la verificación de Agent Hub son etapas distintas.

El informe por nodos conserva criterios, evidencia, revisión y exclusiones. El porcentaje corresponde a los criterios declarados y vigentes; no estima por sí solo cuánto falta de todo el producto.

## Licencia y atribución

[MIT](LICENSE), con los avisos de LangChain, Inc. y Joel Gangini conservados. Es una adaptación independiente: no es un plugin oficial ni una certificación de Oracle o LangChain. [Procedencia y marcas](docs/procedencia.md).
