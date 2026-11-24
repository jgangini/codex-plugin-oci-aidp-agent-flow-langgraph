<p align="center">
  <img src="docs/assets/aidp-agent-flow-cover.png" width="224" alt="Panda rojo con un mapa de nodos conectados y una señal de aprobación">
</p>

<h3 align="center">AIDP Agent Flow LangGraph</h3>

<p align="center">Crea y prueba agentes LangGraph en Codex, desde una demo local hasta una revisión aceptada en Oracle AI Data Platform.</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/Licencia-MIT-165D63?style=flat-square" alt="Licencia MIT"></a>
  <a href="https://github.com/jgangini/codex-plugin-oci-aidp-agent-flow-langgraph/tree/v0.4.46"><img src="https://img.shields.io/badge/Plugin-0.4.46-C74634?style=flat-square" alt="Versión del plugin 0.4.46"></a>
  <a href="docs/referencia-cli.md#1-instalar-un-motor-versionado"><img src="https://img.shields.io/badge/CLI-0.4.31-303640?style=flat-square" alt="Motor CLI 0.4.31"></a>
</p>

<p align="center"><strong>Tecnologías</strong></p>

<p align="center">
  <a href="docs/prerrequisitos.md"><img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&amp;logo=python&amp;logoColor=white" alt="Python 3.11 o superior"></a>
  <a href="docs/flujo-de-desarrollo.md"><img src="https://img.shields.io/badge/LangGraph-Flujos-176D67?style=flat-square" alt="LangGraph para los flujos del agente"></a>
  <a href="docs/guia-de-uso.md#0-prepara-oci-y-comprueba-el-acceso"><img src="https://img.shields.io/badge/Oracle-AIDP-C74634?style=flat-square" alt="Oracle AI Data Platform para la ejecución nativa"></a>
</p>

<p align="center">
  <a href="#instalación-en-codex">Instalación</a> ·
  <a href="docs/guia-de-uso.md#1-crea-tu-primer-agente-en-local">Primera demo</a> ·
  <a href="docs/flujo-de-desarrollo.md">Arquitectura</a> ·
  <a href="docs/corpus-y-pruebas.md">Pruebas</a>
</p>

## Qué puedes hacer

- **Probar una idea.** Describe el comportamiento esperado y valida un recorrido con datos ficticios, sin cuenta OCI.
- **Evaluar un agente existente.** Aísla un nodo o una ruta, registra evidencia comparable y revisa el resultado por criterio.
- **Llevarlo a AIDP.** Prepara el acceso, acepta una revisión en TEST y, con autorización, publica esa revisión y comprueba una conversación en Agent Hub.

Tú defines el objetivo, los accesos y las decisiones de negocio. Codex prepara el proyecto, implementa el flujo y usa el motor CLI para comprobarlo.

## Instalación en Codex

Con un cliente que admita marketplaces:

```powershell
codex plugin marketplace add jgangini/codex-plugin-oci-aidp-agent-flow-langgraph
codex plugin add langchain-skills-codex@oci-aidp-agent-flow-langgraph
```

Para instalar desde la etiqueta publicada del plugin, añade `@v0.4.46` al nombre del repositorio en el primer comando. El nombre visible es **AIDP Agent Flow LangGraph**. Instala por separado las [skills oficiales de LangChain](docs/prerrequisitos.md#skills-oficiales-de-langchain), abre la carpeta de tu agente y empieza un chat nuevo.

## Documentación

| Quiero… | Guía |
| --- | --- |
| Crear y comprobar mi primer agente | [Guía de uso](docs/guia-de-uso.md) |
| Entender las etapas, responsabilidades y límites | [Arquitectura y flujo de desarrollo](docs/flujo-de-desarrollo.md) |
| Diseñar preguntas y comprobar resultados | [Corpus y pruebas](docs/corpus-y-pruebas.md) |
| Preparar acceso de OCI o consultar los comandos | [Prerrequisitos](docs/prerrequisitos.md) · [Referencia CLI](docs/referencia-cli.md) |
| Mantener y validar el paquete | [Desarrollo del plugin](docs/desarrollo.md) |
