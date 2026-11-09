# Última hora (Mac y Box)

Una página, `hora.html`. El panel anterior sigue en `index.html` y no se modifica.
La página nueva enlaza a `index.html`. Tras un merge a `main`, Pages sirve
`https://inodeman.github.io/mk-pages/hora.html`. Hasta ese merge esa ruta no está publicada.

## Qué muestra

Solo peleas nativas de los últimos 60 minutos: `[as_of - 60 min, as_of]`.
Mac y Box van en la misma página, en tablas distintas.

- Actores Mac: 0–7. Los ids 20–36 se ignoran, no se renumeran.
- Actores Box: 2–12. Un evento con `machine: mac` no entra en la Box.
- Filas: etapas 1 a 10, resumen 1–10, y Goro aparte.
- Columnas: evaluación (pruebas) y entrenamiento. No se promedian entre sí.
- Cada porcentaje medido muestra victorias, derrotas y terminadas.
- Sin peleas terminadas, sin archivo, sin época o con dato viejo: **Sin datos**, no 0 %.
- Un 0 % solo aparece si hay terminadas y cero victorias.
- Interrumpidas, cortes, inválidas y crashes no son derrotas.
- En el CSV activo la etapa 11 queda **SIN VALIDAR** (`p2_ch=6`). No es un porcentaje de Goro y no entra al resumen 1–10.
- Las cifras quedan etiquetadas como detector. La página no certifica validación visual.
- La hora de pantalla es UTC−7 fijo (America/Ciudad_Juarez), también en junio.

## Archivos cifrados

El navegador, ya desbloqueado con la misma contraseña de siempre, lee:

- `data/hora_mac.enc.json`
- `data/hora_box.enc.json`

Mismo sobre AES-GCM que el resto del panel (`v`, `iv`, `ct`). No van en claro.
Este cambio no trae esos archivos: sin publicación de cada máquina, la página dice Sin datos.

## Fuente única

El publicador lee solo `panel/hora_sources.json`.

- CSV activo: `/workspace/mk2/brains/Scorpion1/proj/runs/scorpion/fights.csv`
- Actores 2–12 → ejecución Box
- Actores 40–47 → ejecución Mac, nativo = id − 40
- `/Users/inodeman/mk2/scorpion/runs/standalone/fights.csv` sigue recibiendo actores 0–7, pero es la otra vista de las mismas peleas Mac. Queda `enabled: false` para no sumarla.
- No se lee `status.txt` ni su `retain90`.
- La ventana es `max(2026-11-08T16:55:00-07:00, ahora − 60 min)`. El id de la época sigue siendo `mac_rejoin_epoch_20261108_165350`.
- La columna `time` es el reloj del learner de la Box. El esquema no trae un fin aparte.
- Etapa 11 se muestra como SIN VALIDAR (`p2_ch=6`). No entra al porcentaje de Goro ni al resumen 1–10.
- Un actor esperado sin filas en la ventana queda en «sin reporte», no en 0 %.

## Paquete de eventos

`schema` de salida: `mk.panel.hora.v1`. Entrada de un JSON suelto, si no se usa el CSV:

```json
{
  "machine": "mac",
  "as_of": "2099-03-01T12:00:00-07:00",
  "brain_epoch_start": "2099-03-01T00:00:00-07:00",
  "brain_sha256": "64 hex o null",
  "detector": "ram",
  "source": {
    "connected": true,
    "path_label": "runs/standalone/fights.csv",
    "last_fight_at": null,
    "error": null
  },
  "events": []
}
```

Box usa `machine: "box"` y `runs/scorpion/fights.csv`.

Cada evento:

| Campo | Uso |
| --- | --- |
| `event_id` | Dedup exacto. Si falta, la pelea se cuenta y no se puede deduplicar. |
| `machine` | `mac` o `box`. Si no coincide con el archivo, no entra. |
| `actor_id` | Mac 0–7, Box 2–12. |
| `role` | `eval` / `prueba` o `train` / `entrenamiento`. Otro rol no entra a ningún %. |
| `clock` | ISO-8601 con zona. Sin zona se rechaza. |
| `stage` | 1–10, o 11 solo como candidato a Goro. |
| `status` | `finished`, `interrupted` / `cutoff`, `invalid` / `crash`. |
| `won` | 1 o 0 solo si `status` es `finished`. Si `rw` viene y no coincide con `won`, es inválida. |
| `rival`, `rival_validated`, `guard`, `p2_ch` | Identidad de Goro. `p2_ch=6` no es Goro. |
| `brain_sha256` | Si no es el SHA del sobre, la pelea es de otro cerebro y no entra. |

Peleas con reloj anterior a `brain_epoch_start` no entran. Sin época, no hay porcentaje:
no se atribuyen peleas del cerebro viejo al nuevo.

No enviar el agregado de experimento (`batches` + `execution_machine`) ni eventos de laboratorio (`model` + `rw` sin `machine`). El ingest los rechaza.

## Publicar cada 5 minutos

En la Box, un trabajo aparte cada 300 segundos. No hace falta copiar el CSV de la Mac.

```sh
MK_PANEL_KEY='…' python3 panel/publish_hora.py \
  --sources panel/hora_sources.json \
  --write-dir /ruta/checkout
```

Eso cifra `data/hora_mac.enc.json` y `data/hora_box.enc.json` a partir del mismo CSV.
La clave es la que guarda el navegador tras entrar. Va en el entorno, nunca como argumento.
El comando no lee el otro CSV, no lee `status.txt`, no hace `git reset --hard` y no empuja.

`generated_at` y `seq` salen del reloj de esa ejecución. `as_of` lo pone quien leyó el CSV y define la ventana.
Si `as_of` o `generated_at` tienen más de 10 minutos, la página marca dato viejo y esconde los porcentajes.

Si el checkout de la Mac está sucio y un pull se niega a resetear, no hay que resetearlo.
Publicar desde un worktree limpio de `origin/main` y dejar el checkout local como está.
El merge a `main` lo hace quien revisa. Este repo no despliega solo.

## Lector del navegador

Con la sesión abierta, `hora.html` llama `setInterval(load, 300000)` y pide los `.enc.json`
con `cache: 'no-store'` y `?t=` del bloque de 5 minutos. Eso no publica nada.
Hace falta que el publicador de Pages que ya sube este repo incluya los dos archivos nuevos.
Los pasos están en `panel/box_publisher/SCHEDULER.md`.

La sesión cuenta publicaciones frescas con `generated_at`+`seq` distinto.
Hace falta ver **dos** subidas reales para dar el ciclo por comprobado.
Volver a leer el mismo archivo, aunque pasen 5 minutos, no suma.
Esta VM no vio esas dos publicaciones: los `.enc.json` no se escribieron en `data/` ni se subieron.
