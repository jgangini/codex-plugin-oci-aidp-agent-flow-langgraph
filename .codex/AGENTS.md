# Guía local del repositorio

- Distribución pública de AIDP Agent Flow LangGraph. El motor Python y sus skills viven en `plugins/langchain-skills-codex`; la introducción en español vive en `docs/`.
- Conserva la identidad `langchain-skills-codex`, los avisos MIT y la separación entre las cuatro skills AIDP y las skills oficiales instaladas por separado. No cambies una versión instalada mientras una campaña la usa.
- Valida con `scripts/validate.py` desde el entorno de desarrollo indicado en `docs/desarrollo.md`. Preflight y postflight: `scripts/arch-preflight.ps1` y `scripts/arch-postflight.ps1`. Sentrux usa su gate CLI; no hay reglas locales ni grafo Graphify.
- Mantén los ejemplos genéricos y ejecutables sin red. Las pruebas locales no autorizan ni certifican TEST, producción o compatibilidad de todos los destinos Oracle.
- Nunca publiques `.oci`, claves, recibos privados, identidades de clientes o enlaces internos. Las credenciales se configuran en cada proyecto del usuario, fuera de este repositorio.
- Los cambios funcionales necesitan regresión en la suite existente. Mantén una única guía de uso en español y actualiza los ejemplos cuando cambie el contrato CLI.
