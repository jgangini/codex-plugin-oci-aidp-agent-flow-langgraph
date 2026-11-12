# Guía de uso: de una idea a un agente validado

El ejemplo siguiente comprueba la instalación y el ejecutor con un agente mínimo. No construye automáticamente un agente de negocio terminado. Para implementar tu caso usa los [prompts](prompts.md) y define el [corpus](corpus-y-pruebas.md).

Consulta el [flujo de desarrollo](flujo-de-desarrollo.md) para entender las decisiones y los retornos de este recorrido. El paquete se distribuye bajo [licencia MIT](../LICENSE).

## 1. Instalar un motor versionado

Tras instalar las skills en Codex, clona el repositorio para instalar su CLI. Ejemplo PowerShell desde tu carpeta de desarrollo:

```powershell
git clone https://github.com/jgangini/codex-plugin-oci-aidp-agent-flow-langgraph.git
cd codex-plugin-oci-aidp-agent-flow-langgraph
git checkout v0.4.45
$Repo = (Get-Location).Path
$Motor = Join-Path $HOME '.codex/runtimes/aidp-agent-flow/0.4.31'
uv venv $Motor --python 3.11
uv pip install --python "$Motor/Scripts/python.exe" "$Repo/plugins/langchain-skills-codex"
$Flow = Join-Path $Motor 'Scripts/aidp-agent-flow.exe'
& $Flow --version
& $Flow --help
```

Si esa ruta ya contiene un motor, comprueba su versión antes de instalar. Para una actualización crea otra ruta versionada y conserva la anterior. No ejecutes este bloque encima del motor usado por una campaña activa. En esta guía `$Flow` siempre identifica el ejecutable elegido, sin depender de otro comando en PATH.

## 2. Crear el proyecto y ejecutar el ejemplo sin OCI

Continúa en la misma sesión PowerShell:

```powershell
$Proyecto = Join-Path (Split-Path $Repo -Parent) 'mi-agente-soporte'
& $Flow --json project init --path $Proyecto --name 'Asistente de soporte'
& $Flow --project $Proyecto --json doctor
Copy-Item "$Repo/examples/corpus-fixtures.json" "$Proyecto/tests/corpus-fixtures.json"
& $Flow --project $Proyecto --json test --cases tests/corpus-fixtures.json --plan
& $Flow --project $Proyecto --json test --cases tests/corpus-fixtures.json --hypothesis 'Comprobar el ejecutor con respuestas grabadas y el nodo respond.'
```

Resultado esperado: tres casos aprobados y recibos bajo `.aidp-local/`. `--plan` comprueba preparación y capacidad; no invoca el agente ni reserva llamadas. La ejecución siguiente usa respuestas grabadas, no el modelo real. El código del proyecto debe respetar los adaptadores inyectados: este modo no es un sandbox de red para código arbitrario.

`project init` crea el entorno con `uv`, una plantilla modular, una campaña limitada a fixtures y un mapa inicial de criterios. `--no-sync` permite crear solo los archivos. La plantilla no conecta automáticamente MCP, tablas o RAG.

```text
mi-agente-soporte/
  .oci/                   # Solo al habilitar OCI; privada
  .venv/                  # Entorno del agente
  aidp-agent.toml          # Factory, modelo y destino nativo
  pyproject.toml
  uv.lock
  agent/                  # Paquete nativo; no incluye pruebas o claves
    agent.py
    requirements.txt
    runtime.json
    core/
  tests/                  # Corpus y definición inicial de campaña
  test-campaign.json      # Política activa
  node-progress.json      # Mapa de nodos y criterios
  .aidp-local/            # Resultados privados, operaciones y progreso
```

## 3. Diseñar e iterar con Codex

Abre `$Proyecto` en Codex e invoca `aidp-agent-flow-langgraph` junto con `aidp-langgraph-test`. Describe el objetivo, usuarios, datos, herramientas, permisos y resultados esperados. Codex debe implementar la lógica y los adaptadores; una plantilla que importa correctamente todavía no cumple el objetivo.

Para un fallo, selecciona un caso y una hipótesis concreta. El siguiente comando de prueba es **solo para una iteración posterior con un candidato cambiado**: si ya aprobaste el mismo caso en el paso 2, consulta su recibo en lugar de repetirlo.

```powershell
& $Flow --project $Proyecto --json test --cases tests/corpus-fixtures.json --case soporte-grafo --hypothesis 'Verificar la entrega de la respuesta grabada.'
& $Flow --project $Proyecto --json campaign status
& $Flow --project $Proyecto --json progress report
& $Flow --project $Proyecto --json package check
```

No repitas el caso idéntico si ya lo ejecutaste en el paso anterior. El motor lo detecta. Reutiliza el recibo o cambia el candidato para una hipótesis justificada; las repeticiones estadísticas requieren una política que las permita y `--repeat-reason`. No cambies IDs para ocultar repeticiones.

El mapa generado corresponde a los casos de la plantilla, no a cualquier corpus añadido. Ajusta `node-progress.json` al corpus aprobado siguiendo [el contrato de progreso](../plugins/langchain-skills-codex/skills/aidp-agent-flow-langgraph/references/node-progress.md). Un caso no mapeado no cierra mágicamente un requisito. La tabla queda en `.aidp-local/progress/table.md`.

## 4. Probar localmente con un modelo OCI real

Primero completa [`.oci` y la configuración](prerrequisitos.md). Luego:

```powershell
& $Flow --project $Proyecto --json models list --limit 100
& $Flow --project $Proyecto --json runtime check --require-profile
Copy-Item "$Repo/examples/corpus-real.json" "$Proyecto/tests/corpus-real.json"
```

La política creada por defecto tiene **cero presupuesto y cero llamadas pagadas**. Antes de `--real`, acuerda límites, el modelo y los costes máximos razonables para tu proyecto. Codex debe revisar y versionar el ajuste de `test-campaign.json`, conservar el historial y documentar la autorización; `campaign init` no sobrescribe campañas ni existe un comando inventado para ampliarlas. Revisa [la política de campañas](../plugins/langchain-skills-codex/skills/aidp-agent-flow-langgraph/references/campaigns.md). El CLI no sustituye los límites de facturación del proveedor.

Con esa preparación y autorización vigentes:

```powershell
& $Flow --project $Proyecto --json test --cases tests/corpus-real.json --case soporte-evidencia-real --real --plan
& $Flow --project $Proyecto --json test --cases tests/corpus-real.json --case soporte-evidencia-real --real --hypothesis 'El modelo responde a partir de la evidencia suministrada.'
```

`--real` llama al modelo configurado. No convierte automáticamente servicios grabados en MCP o consultas reales. Para conexiones reales necesitas adaptadores comprobados, identidades, permisos y pruebas de integración específicas.

## Evaluar calidad y consistencia

Las comprobaciones del corpus y la revisión semántica cumplen funciones distintas.
Para evaluar respuestas guardadas, prepara paquetes de pregunta, respuesta, fuentes,
rúbrica y hechos de referencia con vínculos a sus archivos y hashes. Calibra el juez
con ejemplos positivos y negativos revisados antes de usarlo para evaluar al agente.
Sigue los comandos y contratos de [evaluación semántica](../plugins/langchain-skills-codex/skills/aidp-langgraph-test/references/semantic-quality.md).

Una comparación entre ejecuciones necesita la misma pregunta, evidencia y revisión
identificada. La identidad declarada debe coincidir con el recibo original y sus
parámetros de modelo; un contexto copiado de otra ejecución se rechaza. Sin esos
datos la comparación no acredita consistencia. Los desacuerdos del juez se conservan
para revisar su criterio; no se convierten automáticamente en cambios del prompt.

## 5. Pasar a AIDP TEST

Completa `[native]`, prepara el acceso del agente mediante Credential Store y verifica compute y compatibilidad. Una carpeta local no demuestra que el destino remoto exista o sea propio.

La plantilla tiene una configuración nativa independiente: completa `agent/runtime.json` antes de subirla. Los campos de `[model]` en `aidp-agent.toml` **no se copian automáticamente**:

```json
{
  "credential_name": "<NOMBRE_DE_LA_CREDENCIAL_OCI_EN_AIDP>",
  "region": "<REGION_DEL_MODELO>",
  "model_id": "<OCID_DEL_MODELO_COMPATIBLE>",
  "compartment_id": "<OCID_DEL_COMPARTIMENTO>",
  "max_tokens": 512
}
```

La plantilla espera que esa credencial exponga `tenancy`, `user`, `fingerprint` y `private_key` mediante el acceso nativo de AIDP. El JSON contiene referencias y configuración, nunca la clave privada. Para otro tipo de credencial adapta y prueba el conector; no supongas que todos tienen ese contrato.

Antes de la primera invocación nativa, revisa también `test-campaign.json`: `native_call_ceiling` y `native_cost_ceiling_usd` arrancan en cero. Acuerda límites nativos dentro del total autorizado (`max_model_calls`, `budget_usd` y `max_attempts`); permitir `--real` local no habilita por sí solo estas invocaciones. Conserva el historial y no amplíes límites para ocultar consumo desconocido.

Después de superar los casos locales pertinentes, inspecciona y aplica las operaciones autorizadas:

```powershell
& $Flow --project $Proyecto --json native sync
& $Flow --project $Proyecto --json native sync --apply
& $Flow --project $Proyecto --json native ensure-agent --apply
& $Flow --project $Proyecto --json native inspect-layout
& $Flow --project $Proyecto --json native test-init --apply
& $Flow --project $Proyecto --json native status
```

Espera a que la operación registrada finalice y TEST esté ACTIVE. Consulta `status`; no vuelvas a enviar la operación para esperar. Crea después la sesión y ejecuta el caso nativo:

```powershell
& $Flow --project $Proyecto --json native session-create --apply
Copy-Item "$Repo/examples/native-case.json" "$Proyecto/tests/native-case.json"
& $Flow --project $Proyecto --json native invoke --surface TEST --question-file tests/native-case.json --expect '1001' --apply --hypothesis 'Comprobar la respuesta de la revisión servida en TEST.'
```

`--expect` solo verifica un fragmento. Revisa toda la respuesta, revisión, referencias y efectos contra la rúbrica. Registra la aceptación por criterio con `progress review-test`; consulta `--help` y el [contrato nativo](../plugins/langchain-skills-codex/skills/aidp-agent-flow-langgraph/references/native-cli.md) para sus parámetros y requisitos. Deben aprobarse los criterios del agente y de sus nodos, no solamente el transporte.

Para cambios posteriores se usa el refresco TEST documentado (`native test-refresh`), no otra creación inicial. Identifica la revisión servida y comprueba que PROD mantiene la anterior hasta aprobar y publicar la nueva.

## 6. Publicar, registrar y compartir

Solo con aceptación TEST vigente y autorización de publicación:

```powershell
& $Flow --project $Proyecto --json native publish
& $Flow --project $Proyecto --json native publish --apply
& $Flow --project $Proyecto --json native status
```

La publicación es asíncrona. Espera a que termine la operación registrada y que PROD aparezca ACTIVE con la revisión aceptada. No vuelvas a publicar para esperar. Solo entonces continúa con Registry:

```powershell
& $Flow --project $Proyecto --json registry inspect
Copy-Item "$Repo/examples/registry-metadata.json" "$Proyecto/tests/registry-metadata.json"
& $Flow --project $Proyecto --json registry register --metadata tests/registry-metadata.json
& $Flow --project $Proyecto --json registry register --metadata tests/registry-metadata.json --apply
& $Flow --project $Proyecto --json registry status
& $Flow --project $Proyecto --json registry hub-link
```

Adapta los metadatos antes de registrarlos. Publicar y registrar son pasos distintos. Si ya existe el registro correcto, sigue la adopción verificada del [contrato Registry](../plugins/langchain-skills-codex/skills/aidp-agent-flow-langgraph/references/registry.md), sin duplicarlo. `hub-link` requiere configurar `native.agent_hub_url` con el portal verificado. El enlace no concede acceso anónimo: cada usuario necesita autenticación y permisos. Comprueba finalmente la conversación en Agent Hub.

## 7. Si ya tienes un agente

Trabaja en una rama o copia aislada. Inventaría archivos de entrada, dependencias, factory, prompts, herramientas, identidad, datos y despliegues. Usa `project adopt` cuando falte el contrato local; no lo uses encima de una configuración existente. Ese comando no reconstruye la lógica del agente ni descarga automáticamente su código de AIDP.

Reproduce primero un recorrido que funcione; después aísla el fallo. No reinstales tablas, credenciales ni compute para corregir un prompt. Se admiten un `.py` o módulos/carpetas según las necesidades y el paquete soportado por el destino.

## Estado y reutilización de evidencia

`workflow status` reúne las observaciones locales; `workflow status --native`
añade el estado nativo y Registry mediante consultas. Puede actualizar informes
y recibos de conciliación locales, pero no publica ni inicia investigación.
`observation_complete` sólo acredita que las consultas requeridas terminaron;
hay que revisar cada sección para conocer bloqueos, operaciones pendientes y
resultados. Registry listo no acredita una conversación útil en Agent Hub.

Las nuevas pruebas por nodo pueden conservar su resultado después de un cambio
en otro criterio del plan si coinciden el criterio, contexto del nodo, requisitos,
política e historial de alcance, además de paquete, configuración, modelo, caso,
motor y entorno. El informe identifica la reutilización y el plan original.
No se reescriben recibos. Los recibos antiguos sin esa vinculación y la aceptación
integrada final siguen exigiendo coincidencia del plan completo. Cambiar código
o prompts sigue invalidando evidencia: no se presume aislamiento entre módulos.

Consulta el [recorrido de iteración eficiente](../plugins/langchain-skills-codex/skills/aidp-agent-flow-langgraph/references/efficient-iteration.md)
para pruebas parciales, reanudación y controles de calibración.
