# Cómo construir y usar un corpus de pruebas

Un corpus es una colección versionada de casos que representan las tareas del agente. Cada caso debe permitir decidir si se obtuvo el resultado esperado. Una lista de preguntas sin criterios no permite medir progreso.

## Separar tres niveles

| Nivel | Qué se ejecuta | Qué demuestra |
| --- | --- | --- |
| Fixture local | Grafo/nodo real con modelo y servicios grabados | Routing, transformaciones y contratos especificados |
| Modelo real local | Mismo agente, modelo OCI real y adaptadores seleccionados | Interpretación y respuesta en ese caso/configuración |
| AIDP TEST | Paquete servido por el runtime nativo | Integración, identidad, herramientas, revisión y comportamiento observado |

Los fixtures incluidos son un ejemplo didáctico para `respond`. En ellos la respuesta está prefijada: **no demuestran que el modelo razone ni que un agente de soporte completo funcione**. El corpus real incluido es una comprobación pequeña de evidencia suministrada, no una batería de aceptación de negocio.

## Formato ejecutable local

Archivo JSON con una lista de casos. Ejemplo adaptado a la plantilla:

```json
[
  {
    "id": "soporte-grafo",
    "input": {"question": "Evidencia: el pedido 1001 está enviado. ¿Cuál es su estado?"},
    "model_responses": ["El pedido 1001 está enviado."],
    "expected_nodes": ["respond"],
    "require_model_call": true,
    "trace_boundaries": true,
    "assertions": [{"path": "answer", "equals": "El pedido 1001 está enviado."}]
  }
]
```

| Campo | Uso |
| --- | --- |
| `id` | Identificador estable; máximo 128 caracteres para la campaña |
| `input` | Estado inicial que recibe el agente; no contiene respuestas de referencia |
| `model_responses` | Lista de respuestas grabadas para fixtures, consumidas en orden |
| `assertions` | Una operación por aserción: `equals`, `contains` o `not_empty`, sobre una ruta del estado |
| `expected_nodes` | Nombres del grafo cuya ejecución se quiere comprobar |
| `node` | Ejecuta solo el nodo indicado; no se combina con selectores de recorrido |
| `start_after`, `stop_before` | Seleccionan un recorrido parcial; necesitan un grafo con checkpointer y estado de entrada válido |
| `service_records` | Interacciones grabadas con MCP, RAG o tablas según el contrato del adaptador |
| `clock_at` | Reloj ISO con zona para pruebas de negocio; no cambia permisos ni vencimientos reales |
| `trace_boundaries` | Hashes y tamaños acotados de los estados, sin copiar sus valores completos |

Las aserciones y respuestas grabadas son configuración del evaluador, no información que deba recibir el modelo real. Agotar los fixtures es un fallo de preparación; no se resuelve ajustando el prompt del agente.

Para servicios grabados, consulta [el contrato de servicios](../plugins/langchain-skills-codex/skills/aidp-agent-flow-langgraph/references/local-development.md). No inventes un esquema MCP genérico para todos los conectores. Comprueba herramienta, argumentos, orden, resultados y efectos permitidos con el adaptador del proyecto.

## Seleccionar una prueba útil

Con `$Flow` y `$Proyecto` definidos en el tutorial:

```powershell
& $Flow --project $Proyecto --json test --cases tests/corpus-fixtures.json --plan
& $Flow --project $Proyecto --json test --cases tests/corpus-fixtures.json --case soporte-nodo --hypothesis 'Aislar la respuesta del nodo sin repetir todo el grafo.'
```

En un grafo propio, un caso parcial podría indicar `start_after: "clasificar"` y `stop_before: "redactar"`. Esos nombres deben existir en tu grafo: no existen en la plantilla mínima. Aporta el estado que produciría el nodo previo y aserciones sobre lo que debe hacer el tramo. Una parada por otra rama no satisface la frontera esperada.

Los tests directos de nodos omiten el checkpointer; para probar continuidad, reanudación o estado compartido hacen falta recorridos e integración. Este enfoque sigue los [patrones oficiales de pruebas de LangGraph](https://docs.langchain.com/oss/python/langgraph/test).

## Matriz funcional antes de ejecutar

Mantén una sola matriz de requisitos y vincúlala con `node-progress.json`:

| Familia | Ejemplo genérico | Criterio de aceptación |
| --- | --- | --- |
| Normal | Estado de un pedido accesible | Estado correcto sustentado por el dato |
| Ambigua | «¿Cómo va lo mío?» | Pregunta el identificador necesario; no inventa |
| Dato ausente | Pedido inexistente | Indica ausencia concreta y cómo continuar |
| Routing | Devolución frente a seguimiento | Usa la herramienta o rama pertinente |
| Fallo externo | Fuente no disponible | Informa la limitación y conserva la evidencia existente |
| Seguridad | Pedido de otro usuario | Rechaza el acceso sin revelar datos |
| Continuidad | «¿Y cuándo llega?» | Mantiene la entidad correcta y no mezcla sesiones |
| Efectos | Solicitud de cambio | No afirma haber cambiado nada sin resultado verificable |
| Recuperación | Timeout tras envío | Reconcilia el intento; evita duplicar la operación |

Incluye pruebas específicas de dominio, contradicciones, periodos, citas, MCP/RAG y tablas cuando formen parte del agente. No impongas capacidades que el producto no necesita.

## Ciclo de corrección

1. Clasifica el fallo: preparación, lógica/prompt, datos, contrato externo o aceptación.
2. Conserva la entrada y revisión que fallaron; formula una hipótesis.
3. Ejecuta el nodo o tramo mínimo y un contraejemplo cercano.
4. Verifica el consumidor del resultado y la integración afectada.
5. Ejecuta la medición congelada pertinente y revisa regresiones.
6. Pasa a TEST nativo cuando corresponda; no publiques por contar muchos PASS locales.

Separa casos de ajuste y casos de medición. No cambies respuestas esperadas para aprobar una regresión. Para comportamiento estocástico usa varias ejecuciones justificadas y declaradas en la política, conservando también los fallos.

Cada resultado debe conservar revisión, modo, entrada, resultado observado, criterio, evidencia y limitación. Las rúbricas semánticas necesitan revisión o evaluadores calibrados: `contains` no garantiza calidad, fidelidad ni ausencia de alucinaciones.

## Interpretar el avance

```powershell
& $Flow --project $Proyecto --json progress report
& $Flow --project $Proyecto --json campaign status
```

La tabla `.aidp-local/progress/table.md` calcula avance sobre criterios activos, con sus pesos. Expone exclusiones e historial; una exclusión no equivale a aprobación. Una evidencia de otra revisión puede quedar histórica y requerir revalidación. Cerrar nodos no sustituye la aceptación integrada del agente.

Para diagnosticar o comparar recibos usa `experiment diagnose --receipt <ruta-relativa>` y `experiment compare --baseline <ruta-relativa> --candidate <ruta-relativa>`. Obtén esas rutas de los resultados reales, no de nombres supuestos. El motor comprueba comparabilidad; un cambio de entorno o motor puede invalidarla.

## Corpus nativo y medición real

`native invoke` recibe un archivo por pregunta con `id` y `question`, como [native-case.json](../examples/native-case.json). No recibe directamente el array del corpus local. Programa cada caso con su hipótesis, límites y evaluación funcional; conserva la identidad estable según el contrato nativo.

Una ejecución bloqueada, no realizada o inconclusa sigue pendiente. Nunca cuentes un timeout como cero coste ni como aprobación. Consulta el estado antes de repetir. [Evaluación de agentes: tareas, trazas y resultados](https://www.anthropic.com/research/demystifying-evals-for-ai-agents).
