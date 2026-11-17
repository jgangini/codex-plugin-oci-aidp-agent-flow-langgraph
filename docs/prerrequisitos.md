# Prerrequisitos y credenciales

Prepara el entorno, la identidad OCI y el destino antes de comenzar el desarrollo orientado a AIDP. Después usa el [prompt inicial de bootstrap](guia-de-uso.md#0-prepara-oci-y-comprueba-el-acceso) para comprobarlos. Sólo puedes omitir OCI si eliges exclusivamente la demostración local simulada; retoma estos requisitos antes de usar servicios OCI o desplegar.

## 1. Entorno local

Para comenzar instala Codex, habilita el plugin y prepara las skills oficiales indicadas a continuación. En el [tutorial](guia-de-uso.md) pides a Codex que compruebe y prepare el entorno mediante bootstrap: Git, `uv`, Python 3.11 o superior y las dependencias del proyecto. Si algún requisito no puede instalarse dentro del acceso disponible, Codex debe indicar la intervención necesaria. Los comandos de la referencia técnica usan PowerShell. En Linux/macOS cambia `Scripts/python.exe` por `bin/python` y `Scripts/aidp-agent-flow.exe` por `bin/aidp-agent-flow`.

El entorno del CLI es independiente del entorno del agente. Fija sus versiones; no reemplaces un ejecutable compartido mientras otra campaña lo utiliza. La plantilla usa por defecto el perfil `aidp-managed-1.2.4`; el perfil histórico de LangGraph 1.0.1 se selecciona explícitamente. Comprueba el runtime observado de tu AIDP antes de aceptar compatibilidad: el perfil no constituye certificación de Oracle.

### Skills oficiales de LangChain

El plugin distribuye cuatro skills propias de AIDP. Las instrucciones generales del framework proceden de [LangChain Skills](https://github.com/langchain-ai/langchain-skills) y se instalan por separado. Instalar skills no instala librerías Python ni configura modelos.

Puedes pedirlo en lenguaje natural, sin ejecutar comandos:

```text
Instala en Codex, desde el repositorio oficial langchain-ai/langchain-skills,
las skills langchain-dependencies, langchain-fundamentals,
langgraph-fundamentals, langgraph-persistence y langgraph-human-in-the-loop.
Reutiliza las que ya estén instaladas desde esa fuente y evita duplicados.
Comprueba cuáles estarán disponibles al iniciar el siguiente chat.
```

Para una instalación manual, la [guía oficial](https://github.com/langchain-ai/langchain-skills#installation) documenta el instalador de skills de Codex y la alternativa con `npx skills`. Usa la vía admitida por tu entorno; no ejecutes el script `install.sh` como si fuera un instalador de Codex.

El bootstrap aplica la [comprobación de skills](../plugins/langchain-skills-codex/skills/aidp-agent-bootstrap/references/framework-skills.md): lee el inventario de la sesión y carga sólo lo pertinente. Fundamentos de LangGraph se utiliza al crear el grafo; dependencias al preparar el entorno; fundamentos de LangChain cuando se usan sus agentes o herramientas; persistencia e intervención humana sólo cuando el caso las requiere. Si falta alguna necesaria, lo comunica y prepara su instalación dentro de la autorización de setup. Puede requerirse un chat nuevo para que Codex la descubra.

Esta comprobación la ejecuta Codex siguiendo la skill de bootstrap; **no es un detector añadido a `doctor`**. La revisión de las skills, el entorno Python y el runtime AIDP son comprobaciones distintas. Conserva la revisión conocida de las skills durante una campaña y verifica APIs y dependencias frente al destino real: las instrucciones oficiales pueden evolucionar antes que el runtime gestionado.

## 2. Carpeta `.oci` del proyecto

Necesaria para este flujo de autenticación con clave de API cuando ejecutes llamadas reales:

```text
mi-agente/
  .oci/
    config
    key.pem
  aidp-agent.toml
  agent/
  tests/
```

`key.pem` contiene la **clave privada** de firma de OCI. No es un token de Apify ni una contraseña del portal. Registra la clave pública correspondiente en tu usuario OCI; no cargues la privada en esa pantalla. Puedes conservar otro nombre de archivo, siempre que `key_file` apunte a él.

Crea localmente `.oci/config` con este formato y reemplaza los marcadores:

```ini
[DEFAULT]
user=<OCID_DE_TU_USUARIO>
fingerprint=<HUELLA_DE_LA_CLAVE_PUBLICA_REGISTRADA>
tenancy=<OCID_DE_TU_TENANCY>
region=<REGION_OCI>
key_file=C:/ruta/absoluta/mi-agente/.oci/key.pem
```

Usa una ruta absoluta real para `key_file`, también si mueves el proyecto. Para Linux/macOS, por ejemplo `/ruta/mi-agente/.oci/key.pem`. El SDK resuelve la clave a partir de ese campo; colocar un archivo junto a `config` no corrige una ruta equivocada. Si la clave está cifrada, verifica un mecanismo de contraseña compatible con tu entorno; no publiques la contraseña ni supongas que el plugin tiene un diálogo interactivo para pedirla.

Una vez que el bootstrap cree o adopte el proyecto, comprueba estas referencias en `aidp-agent.toml`:

```toml
[oci]
config_file = ".oci/config"
profile = "DEFAULT"
```

La carpeta del proyecto es una convención de este flujo. OCI también admite su configuración por usuario en `~/.oci/config`; puedes apuntar al archivo existente en lugar de duplicar claves. Consulta la [documentación oficial del archivo OCI](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm).

Protege ambos archivos con permisos del usuario de desarrollo. Conserva en `.gitignore`:

```gitignore
.oci/
*.pem
*.key
.aidp-local/
.venv/
```

Verifica antes de un commit: `git check-ignore .oci/config .oci/key.pem`. No pegues claves en prompts, preguntas del corpus, trazas ni variables del agente.

## 3. Identidad y recursos de destino

La firma correcta no concede permisos. Necesitas acceso autorizado al compartimento, modelos y recursos AIDP del proyecto. Para el modelo local configura en `aidp-agent.toml`:

```toml
[model]
region = "<REGION_DEL_MODELO>"
model_id = "<OCID_DEL_MODELO_COMPATIBLE>"
compartment_id = "<OCID_DEL_COMPARTIMENTO>"
max_tokens = 512
max_calls = 3
```

El catálogo y la compatibilidad dependen de la región y el modelo. Usa `models list` y un caso representativo; no elijas únicamente por un ranking. No todos los parámetros de razonamiento son admitidos por todos los adaptadores.

Para el flujo nativo configura `[native]`: `endpoint`, `platform_id`, `workspace_key`, `remote_root`, `display_name`, `compute_key` y, al adoptar un agente, `agent_key`. Comprueba valores reales con la API/CLI del entorno. La región del modelo puede ser distinta de la región del endpoint AIDP; no las intercambies.

## 4. Credential Store es otra capa

La `.oci` local permite al desarrollador firmar llamadas. En AIDP, el agente debe obtener su identidad o secretos mediante el mecanismo nativo autorizado, por ejemplo Credential Store; **no se empaqueta `.oci/key.pem` con el agente**.

La skill `aidp-runtime-credentials` inspecciona y prepara entradas según el contrato del destino. Conserva las credenciales compartidas de otros proyectos. Un token de una herramienta externa, como Apify, es distinto de la identidad OCI y se configura por separado. [Guía de credenciales](../plugins/langchain-skills-codex/skills/aidp-runtime-credentials/SKILL.md).
