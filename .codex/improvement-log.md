# Mejoras verificadas

| Fecha | Hallazgo | Ajuste | Evidencia |
| --- | --- | --- | --- |
| 2026-11-05 | El paquete local no tenía una introducción pública completa en español y algunas referencias eran internas. | Distribución marketplace, guía progresiva, corpus genérico y referencias públicas; el motor se conserva. | Ejemplos y validación reproducible en `docs/desarrollo.md`. |
| 2026-11-05 | Las pruebas del motor requieren una carpeta temporal escribible al ejecutar desde la distribución anidada. | El validador prepara `plugins/validation-work`, excluida de Git, y ejecuta la suite existente. | `scripts/validate.py`. |
