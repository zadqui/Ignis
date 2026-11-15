# Demostración reproducible · Flame in Freefall (iteración 1)

Funciona con el estado actual de los datos, aunque la extracción masiva de M4 no haya terminado: la demo usa una
**instantánea congelada** (`data/demo/demo.duckdb`), así que el procesamiento en segundo plano no cambia los datos
durante la presentación.

## Preparar (una vez, ~1 min)

```bash
uv sync --extra ml --extra app
uv run fif-relations build          # M5 (provisional) — primero: M6 lee m5_findings y relations
uv run fif-scenarios build          # M6 con los últimos hallazgos importados
uv run fif-app snapshot             # candidata → verificación completa → promoción (la anterior queda como demo.prev)
```

## Lanzar

```bash
uv run fif-app demo                 # comprobación de consistencia (16 reglas) → API :8000 + panel :8501
uv run fif-app demo --live          # alternativa: base de datos viva (cambia si la extracción sigue)
```

**Presentación pública** (proyector, enlace compartido): usar solo la exportación pública. `demo.duckdb` es privada
porque contiene texto completo y resúmenes con licencias restrictivas (ver `docs/compliance.md`).

```bash
uv run fif-app public-export        # copia filtrada + exploración de fugas + verificación completa
uv run fif-app demo --public        # API en modo público (rechaza cualquier base que no sea la exportación)
```

Si la comprobación de consistencia falla, la demo **no arranca**. El panel muestra siempre, arriba, las
limitaciones activas.

## Guion (≈ 8 min)

1. **Cobertura** (por investigación). Hay 24 investigaciones PSI, con documentos, nivel de texto, tablas
   experimentales (mapeo **borrador**), 1,997 ensayos, unidades de texto y cuántas se extrajeron. Mensaje: lo que
   no se ha procesado se ve como tal.
2. **Mapa de huecos → Artemis (ancla)**. El escenario es **provisional** (3 supuestos marcados) y las tolerancias
   son exploratorias.
   - O₂ 30–36 %: **ningún ensayo tabulado cae dentro**; 26 rangos de matrices de condiciones solo tocan el borde
     (`overlaps`, no es cobertura); 138 fuera; 1,833 sin registrar.
   - Presión 56–70 kPa: 0 dentro, 198 cerca, 8 que solo tocan.
   - Gravedad: **no evaluable** (ningún ensayo la registra; el tipo de investigación es solo contexto).
   - Diagnóstico separado: huecos de **sistema** (adquisición, procesamiento, extracción), **estructura de la
     fuente** (p. ej. PSI-142: su tabla es un índice de publicaciones) y **posibles huecos científicos** (solo
     dentro del corpus procesado y provisionales).
   - Cierre: el sistema **no** declara un hueco de conocimiento en O₂ ≥ 30 %, porque hay intersecciones y la mayor
     parte del texto falta por procesar. Es una afirmación acotada y honesta.
3. **Huecos declarados por los autores**: limitaciones y trabajo futuro extraídos (p. ej. pérdida de datos de
   imagen, imágenes corruptas, criterio de selección de despliegues). Son **extracciones automáticas, sin revisión**,
   no vacíos científicos confirmados (el panel lo indica sobre la tabla).
4. **Explorador → un hallazgo**: la cita exacta, el documento y la página; las comprobaciones de la verificación
   automática; la insignia «verificado automáticamente · sin revisión científica».
5. **Estudio + contraste** (p. ej. PSI-25). «Otros estudios dijeron…»: se muestran todas las relaciones no
   exploratorias (todas provisionales; `consistent` incluida) y como mucho 5 `related_topic` por hallazgo y 50 por
   estudio, solo independientes y de otras investigaciones. El resto se indica como oculto. Las relaciones
   científicas exigen la misma variable, direcciones y condiciones comparadas.
6. **Consistencia**: 16 reglas en verde (nada automático aparece como confirmado; gravedad nunca imputada;
   `unknown` ≠ fuera; los huecos científicos son provisionales…).
7. **Novedades**: corridas de extracción importadas (pilotos y, si ya se importaron, lotes masivos) y candidatos a
   hallazgo singular. La singularidad **no está calibrada** (depende de τ): una lista vacía no significa que no haya
   hallazgos singulares. Comprobar en `data/demo/demo.json` qué corridas incluye la instantánea antes de presentar.

## Qué decir sobre las limitaciones

- Los mapeos de M2 están en borrador; los escenarios son provisionales; las tolerancias son exploratorias.
- La extracción de texto está en curso (lotes de p-6 en Kaggle). La instantánea muestra lo importado hasta su hora
  (`data/demo/demo.json`).
- No hay hallazgos ni relaciones con revisión científica todavía. Hay una cola de 31 candidatos y un vocabulario
  de 37 conceptos pendientes de revisión humana.
- La similitud de texto aún no discrimina bien (τ = 0.80); los `related_topic` son solo candidatos.

## Actualizar la instantánea tras nuevos lotes

La extracción masiva se procesa con `kaggle/mass_driver.py` (reanudable desde `data/findings/mass_run/state.json`;
no repite descargas, importaciones ni verificaciones ya hechas y se detiene si queda poca RAM libre). Cuando todos
los bloques terminen:

```bash
uv run python kaggle/mass_finalize.py   # informe de calidad → M5 → M6 → comprobación → instantánea verificada
uv run fif-app demo
```

La importación, la verificación (modelo NLI) y M5 cargan modelos: requieren ≥ 1.5–2.5 GB de RAM libre. Si no hay
recursos, la demo sigue funcionando con la instantánea anterior, que nunca se sobrescribe sin verificar.
