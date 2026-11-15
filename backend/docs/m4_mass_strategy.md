# M4 masivo · corrección selectiva y tiempos (iteración 1)

Basado en los bloques c1 y c2 de p-6 (4,944 unidades). Las cifras son medidas, no estimaciones, salvo donde se
indica. Nada de esto cambia el estado de revisión de ningún hallazgo.

## 1. Corrección selectiva: no volver a procesar lo que ya salió bien

El sistema ya permite corregir por unidad sin cambios de arquitectura:

- **La verificación está desacoplada de la extracción.** `fif-findings verify` vuelve a comprobar todos los candidatos
  guardados en segundos (c1+c2: 22 s, sin modelos). Las salidas en bruto (`raw.jsonl`) se conservan.
- **Exportar un subconjunto de unidades.** `fif-findings export --units-file <lista.json> --name <nombre>`.
- **Sustitución por unidad.** M5 marca como activa, para cada unidad, la corrida más reciente cuya salida se pudo leer
  (`ok` o `empty`) (`relations/build.py:active_runs`). Las corridas anteriores quedan como historial (`superseded_by_run`)
  y nunca cuentan como evidencia. Si la corrida nueva falla al leerse, sigue activa la anterior.

### Niveles de corrección, del más barato al más caro

| Nivel | Cuándo | Qué se vuelve a ejecutar | Coste |
|---|---|---|---|
| **T0 · reglas** | El error está en la verificación (tipo vs. `target_kinds`, longitud mínima, atribución por marcador de cita…) | Verificador nuevo (v-4) sobre **todos** los candidatos guardados | segundos, sin GPU |
| **T1 · reintento dirigido** | Fallos mecánicos de unidades concretas | Solo esas unidades, mismo prompt, `run_id` nuevo | minutos de GPU |
| **T2 · prompt nuevo acotado** | La muestra humana muestra un error sistemático de un tipo o sección | Primero un A/B con ~50 unidades y revisión; luego solo las unidades del estrato afectado | ≤ 1 h de GPU por estrato |
| T3 · todo | Solo si T2 muestra que el error afecta a la mayoría del corpus | Todo | ~2.6 h de GPU por bloque |

### Conjuntos T1 medidos en c1+c2

| Conjunto | Unidades | Corrección |
|---|---|---|
| A · respuesta cortada (JSON incompleto) | 107 | Reintentar con más `max_new_tokens` |
| B · sin hallazgo verificado y con alguna cita no encontrada | 184 | Reintentar (la salida tiene un componente aleatorio) o pasar a T2 si el patrón se repite |
| C · sin hallazgo verificado, todo fuera de la oración objetivo | 169 | T2: instrucción para ceñirse a la oración objetivo |

En total son ~460 unidades (9 % de c1+c2), unos 30 min de GPU frente a ~5 h para repetir los dos bloques. Las 2,894
unidades con algún hallazgo verificado no se tocan salvo en T2 o T3.

### Reglas

1. **Una corrección = una corrida nueva** con su `run_id`, prompt y lista de unidades registrados. Nunca se
   sobrescribe una corrida.
2. **No se reprocesa una unidad con un hallazgo revisado por humanos.** La revisión humana manda; la corrida nueva
   tendría que pasar de nuevo por revisión.
3. **Una corrida nueva sin ningún hallazgo válido para una unidad no sustituye automáticamente una anterior que sí lo
   tiene.** Esto incluye salidas vacías y salidas con todos los candidatos rechazados. Es la política
   `latest_parsed_no_empty_override` (config M5 rc-2). La sustitución retenida queda en la vista
   `m5_supersession_holds` (`pending_review`) para revisión humana. Al aplicarla había 5 unidades retenidas, todas de
   corridas piloto, y 4 hallazgos que antes figuraban como historial volvieron a estar activos.
4. **Versiones mezcladas a la vista:** cada hallazgo conserva su `run_id` y `prompt_version`, y el panel debe poder
   filtrar por versión.
5. **Medir antes de corregir:** la muestra estratificada (`reviews/queue/m4_mass_sample_c1c2.yaml`, 30 hallazgos,
   `kaggle/mass_sample.py`) define qué nivel hace falta. Sin revisión humana no se lanza ningún T2.

## 2. Dónde se va el tiempo

| Etapa | Medido | Peso |
|---|---|---|
| Kaggle: preparar entorno e instalar vLLM | ~85 s por sesión | bajo |
| Kaggle: cargar el modelo | 246 s por sesión | bajo |
| **Kaggle: generación** | **~9,000 s por bloque (103 lotes × 80–101 s)** | **~95 %** |
| Descargar los resultados | ~1 min por bloque | bajo |
| Importar y verificar (local) | 10–12 s por bloque | despreciable |
| M5 y M6 (local) | ver `data/findings/mass_run/m5m6_c1c2.log` | bajo |

**El cuello de botella es la generación por lotes síncronos.** Cada lote de 24 unidades espera a la salida más larga.
De mediana tarda 80 s sin respuestas cortadas y 101 s cuando alguna se corta (una salida de 1,536 tokens bloquea a las
otras 23). El rendimiento efectivo es de ~85 tokens/s, muy por debajo de lo que vLLM da en 2×T4 con *continuous
batching*.

### Cómo acelerar sin tocar la calidad científica

| Medida | Ganancia esperada | Riesgo | Estado |
|---|---|---|---|
| **Lotes más grandes** (`batch_size` 96–128; vLLM ya gestiona la concurrencia) | 2–4× en generación (estimado) | Las salidas pueden variar ligeramente con la composición del lote (fp16), igual que ahora. El disyuntor y la reanudación pasan a tener menos granularidad. | Probar en una corrida T1 (~460 unidades) y comparar con la misma muestra antes de usarlo en masa |
| Disyuntor por sub-lotes de 24 dentro del lote grande | mantiene la granularidad | ninguno | cambio pequeño en el runner |
| Más `max_new_tokens` solo para las unidades del conjunto A | recupera ~2 % de unidades | ninguno | T1 |
| Prompt sin cambios entre bloques | reproducibilidad | — | ya se aplica: c1–c5 con p-6 |

**Qué no acelerar:** el umbral NLI, el verificador (no cuesta nada), la cuantización del modelo (cambiaría las
salidas y obligaría a reevaluar) ni los bloques en curso. c3–c5 siguen con la configuración de c1/c2 para que todo el
lote masivo sea homogéneo.
