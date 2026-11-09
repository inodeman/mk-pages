# Publicador de la última hora en la Box

`publish_hora.py` y `run_hora.sh` solo escriben dos archivos cifrados. No hacen `git commit`, `git push` ni `git reset`. El navegador, cada 5 minutos, solo vuelve a leer esos archivos. Si nadie los sube a `main`, la página sigue en Sin datos.

## Qué hay que enganchar

Este repo ya se publica solo: los commits `estado …` y la marca `PUB_TS` de `index.html` los escribe el publicador que ya corre en la Box (en el código de las máquinas figura como `scorpion_pages.py`; ese programa no está en este repo). Ese trabajo, cada vez que va a cifrar y subir el panel, tiene que hacer antes:

```sh
WRITE_DIR=/workspace/mk_pages_repo \
  MK_PANEL_KEY="$LA_CLAVE_QUE_YA_USA_EL_PANEL" \
  /workspace/mk_pages_repo/panel/box_publisher/run_hora.sh
```

Ese `WRITE_DIR` es el checkout que el operador confirmó. No está activado: falta este PR limpio y que el operador encienda el cron.

`MK_PANEL_KEY` es la clave AES de 32 bytes en hex que el navegador guarda al entrar. No va en este paquete ni en la línea de comandos.

El publicador existente debe incluir en el mismo commit que ya empuja:

- `data/hora_mac.enc.json`
- `data/hora_box.enc.json`

Si su lista de archivos es fija, hay que añadir esos dos nombres. Si hace `git add` de `data/`, entran solos. No hace falta un segundo push.

## Reloj

Un ejemplo de cron, distinto de los otros trabajos, cada 5 minutos:

```cron
*/5 * * * * WRITE_DIR=/workspace/mk_pages_repo /workspace/mk_pages_repo/panel/box_publisher/run_hora.sh
```

Ese cron solo deja los `.enc.json` en el checkout. Siguen sin verse en GitHub Pages hasta que el publicador de siempre los suba. Lo mismo vale para un timer de systemd: `ExecStart` es esa línea, sin `git`.

La clave puede estar en el entorno del servicio. No se documenta aquí el valor.

## Qué no hacer

- No leer el CSV de la Mac además del de la Box: son las mismas peleas Mac (0–7 y 40–47).
- No leer `status.txt` ni `retain90`.
- No hacer `git reset --hard` si un pull se detiene. El fallo ya visto en la Mac (`pages pull stopped; the checkout was not hard-reset`) se deja como está; no se borra el checkout.
- No instalar este timer en la Mac. El CSV único está en la Box: `/workspace/mk2/brains/Scorpion1/proj/runs/scorpion/fights.csv`.

## Comprobación

Hacen falta dos ejecuciones reales, con `generated_at` distinto, y que el publicador existente las suba. Recargar el navegador o esperar su lector de 5 minutos no cuenta si el archivo en Pages no cambió. Esta entrega no ejecutó ese ciclo.
