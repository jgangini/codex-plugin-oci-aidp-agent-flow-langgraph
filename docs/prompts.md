# Prompts para usar con Codex

Abre la carpeta del agente y selecciona el plugin **AIDP Agent Flow LangGraph**. Sustituye los marcadores antes de enviar. Estos prompts dan una dirección de trabajo; no son comandos del CLI ni autorizaciones implícitas para todos los recursos de OCI.

## Crear un agente

```text
Usa $aidp-agent-bootstrap, $aidp-agent-flow-langgraph y $aidp-langgraph-test
del plugin AIDP Agent Flow LangGraph 0.4.8.

Quiero crear un agente de [objetivo] para [usuarios]. Debe poder [tareas]
con estas fuentes y herramientas: [lista]. No debe [acciones fuera de alcance].

Trabaja en esta carpeta. Identifica el motor versionado y conserva su ruta
durante la campaña. Prepara el entorno local con uv. Para las llamadas reales,
la identidad está en .oci/config y la clave en .oci/key.pem; comprueba su
disponibilidad sin imprimir secretos ni incluirlos en el paquete del agente.

Define primero un recorrido mínimo útil y sus criterios. Si falta contexto
material para responder, el agente debe preguntar. Propón un corpus con casos
normales, ambiguos, negativos, fallos de herramientas y aislamiento, con resultados
esperados. Distingue fixtures de evaluación con modelo real.

Implementa y prueba por nodos/tramos, luego integra. Ante un fallo conserva la
evidencia, diagnostica la causa y prueba una hipótesis concreta. Actualiza el mapa
de nodos y criterios; no contabilices casos no ejecutados como aprobados.

Presupuesto y efectos autorizados: [importe, llamadas, servicios y operaciones].
Destino TEST: [proyecto/workspace/agente permitido]. Producción: [autorizada/no].
No solicites otra vez autorización para acciones ya cubiertas por este alcance.
No publiques hasta cerrar la aceptación TEST de la revisión candidata.
```

## Auditar y mejorar un agente existente

```text
Usa $aidp-agent-flow-langgraph y $aidp-langgraph-test 0.4.8 para mejorar este
agente existente. Conserva su identidad, datos, credenciales compartidas,
historial y comportamiento útil. No reinstales infraestructura como atajo.

Lee el plan vigente, el código, la configuración y los últimos recibos.
Identifica la revisión activa, motor, dependencias, nodos, tools y límites reales.
No supongas que un archivo largo es un defecto: identifica acoplamientos que
impiden probar o mantener el flujo. Admite un archivo o módulos según convenga.

Reproduce un recorrido correcto y el fallo prioritario. Clasifica el fallo antes
de cambiar prompts. Prueba el nodo/tramo afectado, un contraejemplo, su consumidor
y la integración. Reutiliza evidencia comparable y ejecuta solo los casos que
aporten información. Mantén una sola matriz de aceptación con progreso por criterio.

Si hay una campaña de otra versión, inspecciona campaign upgrade y adopta el nuevo
motor dentro de la autorización vigente preservando recibos, cuotas y reservas.
No reinicies el historial ni repitas efectos inciertos. No cambies el modelo sin
una comparación pertinente y compatible con la región/configuración real.

Entrega: causa demostrada, cambio, casos ejecutados, criterios cerrados, bloqueos
y siguiente prueba útil. Alcance autorizado: [local/OCI TEST/publicación y límites].
```

## Continuar una campaña que ya está en marcha

```text
Carga las skills actualizadas de AIDP Agent Flow LangGraph 0.4.8 y continúa desde
el último recibo verificable. No reinicies el corpus. Comprueba qué ejecutable usa
la campaña; la actualización de skills no cambia automáticamente su motor.

Si hay un intento en curso, espera o reconcilia su resultado antes de cambiar de
motor. Inspecciona la adopción con campaign upgrade y aplica la transición
verificada dentro del alcance ya autorizado, sin borrar evidencia ni liberar
consumo desconocido. Selecciona después un requisito pendiente y la prueba mínima
que permita tomar una decisión. Mantén visibles criterios activos, excluidos,
aprobados localmente y aceptados en TEST. Informa el resultado concreto de cada
iteración; no abras frentes nuevos sin resolver o justificar el bloqueo actual.
```

## Preparar un corpus cuando aún no tengo preguntas

```text
Usa $aidp-langgraph-test. A partir del objetivo y flujo de este agente, prepara
un corpus representativo. Para cada caso define intención, datos, permisos,
resultado esperado, herramientas/rama pertinentes y rúbrica de aceptación.

Separa fixtures de lógica, casos con modelo real y aceptación AIDP TEST.
Incluye los errores relevantes del dominio, continuidad y aislamiento. Mantén
respuestas de referencia fuera de input. No generes solo variantes superficiales.
Vincula los casos con los nodos y criterios existentes y conserva IDs estables.
Ejecuta primero la validación de preparación y la previsión de capacidad.
```

## Promover una revisión ya aceptada

```text
Usa AIDP Agent Flow LangGraph. Revisa que los criterios funcionales y la aceptación
integrada TEST correspondan al paquete candidato exacto, sin bloqueos pendientes.
Dentro del destino y publicación ya autorizados, publica esa revisión por CLI/API,
reconcilia su estado y comprueba la respuesta publicada. Registra o adopta el agente
correcto en AI Registry sin duplicarlo. Verifica la versión activa y entrega el
enlace comprobado de Agent Hub; aclara los permisos de acceso que necesita el usuario.
Usa Browser para la aceptación visual y conversación final, no para repetir
operaciones que ya tengan un contrato CLI/API comprobado.
```
