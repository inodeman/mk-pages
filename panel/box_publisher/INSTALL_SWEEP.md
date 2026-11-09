# Instalar el barrido que conserva la última hora

El `pages_enc.py` de la Box borra del checkout todo lo que no esté en su lista y el publicador existente sube ese resultado. La versión adjunta aquí solo añade dos rutas a esa lista: `hora.html` y `panel/hora.js`. El cifrado no cambia. El resto de `panel/` (Python, pruebas, contratos) sigue borrándose del checkout público.

No está instalado en la máquina. Hay que copiarlo antes del merge. Si el barrido viejo corre después del merge, borra la página nueva y el push la quita de Pages.

## Comprobación

| | Ruta | SHA-256 |
| --- | --- | --- |
| Origen en este repo | `panel/box_publisher/pages_enc.py` | `c89f2406f3719a4f7a2e3d7a4b74514a66401639e31fa13ee2bb6fe186b3c9e2` |
| Destino | `/workspace/publisher/box/pages_enc.py` | el mismo, después de copiar |
| Helper anterior, para reconocer el respaldo | el archivo de 42 líneas | `2a10e01762b445b242ed9e66ce4a22f67af5a0a327e63835e252ef89c8b9ef0b` |

## Pasos

```sh
cp -a /workspace/publisher/box/pages_enc.py /workspace/publisher/box/pages_enc.py.bak
# confirmar que el respaldo es el helper anterior
sha256sum /workspace/publisher/box/pages_enc.py.bak
# copiar el archivo de este repo, sin editarlo
cp -a panel/box_publisher/pages_enc.py /workspace/publisher/box/pages_enc.py
sha256sum /workspace/publisher/box/pages_enc.py
```

El destino tiene que ser `c89f2406f3719a4f7a2e3d7a4b74514a66401639e31fa13ee2bb6fe186b3c9e2`. Ese directorio está fuera del checkout de Pages, así el barrido no se borra a sí mismo.

Después: merge de este PR, una publicación de 5 minutos del publicador que ya existe, y dos actualizaciones distintas. `WRITE_DIR=/workspace/mk_pages_repo` y `run_hora.sh` siguen igual: solo escriben `data/hora_mac.enc.json` y `data/hora_box.enc.json`.
