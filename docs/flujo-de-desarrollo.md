# Flujo de desarrollo de un agente

El plugin combina instrucciones para Codex y un motor CLI. El desarrollador define
el resultado esperado y autoriza las operaciones; Codex implementa y diagnostica;
el motor ejecuta comprobaciones y conserva evidencia. Este es un recorrido de
trabajo supervisado, no una automatización que garantice por sí sola calidad.

## Arquitectura del recorrido

![Codex dirige el motor CLI, que guarda recibos locales y valida la revisión en AIDP TEST. La aceptación habilita la publicación autorizada en PROD, el registro en AI Registry y la comprobación en Agent Hub.](assets/aidp-agent-flow-architecture.png)

El motor guarda los recibos como archivos en el proyecto local. AIDP TEST sirve la
revisión candidata. La flecha discontinua entre TEST y PROD señala el paso a producción. Para
publicar se requiere la aceptación vigente de esa revisión y la autorización del operador.
Después se registra la revisión en AI Registry y se comprueba con una
conversación en Agent Hub.

[Fuente editable de la arquitectura](diagrams/arquitectura-aidp.json) ·
[Abrir la figura a tamaño completo](assets/aidp-agent-flow-architecture.png)

## Flujo de trabajo

[Diagrama interactivo](diagrams/flujo-desarrollo.html) ·
[Fuente editable del diagrama](diagrams/flujo-desarrollo.json) ·
[Tutorial con prompts](guia-de-uso.md)

## Preparación antes del recorrido

Instala el plugin AIDP y las [skills oficiales de LangChain](prerrequisitos.md#skills-oficiales-de-langchain) por separado. El bootstrap comprueba cuáles están disponibles en la sesión y carga las necesarias para el caso. Las skills oficiales orientan sobre el framework; el plugin mantiene el ciclo de desarrollo, evaluación e integración con AIDP. Si falta una skill requerida, se resuelve ese requisito antes de implementar la parte que depende de ella.

Para el recorrido hasta AIDP, prepara también `.oci/config` y la clave privada referenciada, registra su clave pública en OCI y verifica el acceso al destino mediante el [paso 0 del tutorial](guia-de-uso.md#0-prepara-oci-y-comprueba-el-acceso). Esta preparación precede al desarrollo; sólo se omite para una demostración exclusivamente local simulada.

El diagrama comienza después de esta preparación. Tener las skills disponibles no acredita compatibilidad del runtime, resultados de calidad ni autorización para publicar.

## Qué se comprueba en cada etapa

| Etapa | Trabajo y evidencia | Condición para avanzar |
| --- | --- | --- |
| Definición | Preguntas representativas, resultados esperados y restricciones reales | Criterios revisados y casos discriminantes |
| Implementación | Factory portable, módulos y adaptadores de modelo/servicios | Contratos coherentes y paquete verificable |
| Prueba local | Fixture, nodo con modelo o recorrido parcial según el fallo | Comprobaciones afectadas aprobadas, sin efectos inciertos por conciliar |
| Calidad | Fuentes, atribución, alcance y hechos omitidos; juez calibrado cuando se utilice | Evaluación trazable; desacuerdos y límites explícitos |
| TEST | Estructura exacta, revisión servida, herramientas e integración nativa | Evidencia vigente del candidato y requisitos declarados |
| Publicación | Endpoint asíncrono y lectura de su estado terminal | Revisión aceptada publicada con autorización |
| Registry | Registro activo de la identidad y versión esperadas | Binding comprobado y acceso disponible |
| Agent Hub | Conversación real del caso de negocio | Respuesta útil y presentación/streaming cuando corresponda |

Si una operación queda pendiente, se consulta y concilia su identidad existente
antes de repetirla. Una respuesta de transporte correcta no sustituye la aceptación
del caso. La mera disponibilidad de un enlace tampoco demuestra acceso al agente.

## Iteración y conservación de resultados

Corregir un prompt exige rastrear su entrada, contrato y consumidor. Un problema
de recuperación o de validación se corrige en esa frontera. Se prueba primero el
fallo aislado, después la integración afectada. Un cambio de código invalida los
recibos cuya identidad deja de coincidir; no obliga a rehacer el proyecto.

Para modificaciones ajenas de criterios del plan, los recibos nuevos por nodo
pueden conservar crédito si coinciden sus dependencias verificadas. Los recibos
históricos se conservan íntegros. La aceptación integrada mantiene su comprobación
del plan completo. No hay una caché general que deduzca equivalencia de cualquier
cambio de código.

Las comparaciones de consistencia usan la misma pregunta, fuentes y revisión
identificada. Sus resultados describen hechos compartidos y omitidos; no fijan un
porcentaje universal que convierta una respuesta en correcta. Calibrar un juez con
un conjunto finito tampoco certifica su precisión general.

## Fuentes de los diagramas

Las etapas resumen el tutorial y los contratos del motor. El HTML del flujo y el
JSON de arquitectura vinculan sus fuentes a revisiones del repositorio. Ambos
JSON son editables con Archify.
El diagrama no representa una única orden que implemente, pruebe y publique sin
intervención. La licencia del plugin es [MIT](../LICENSE); los componentes de
terceros conservan sus avisos y licencias propios.
