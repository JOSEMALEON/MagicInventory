# Magic Inventory — contexto para Claude

Aplicación de escritorio para gestionar una colección de cartas de **Magic: The Gathering**.
Proyecto personal de aprendizaje de José Manuel León (Python, APIs, GUI, bases de datos, IA).
Repositorio: https://github.com/JOSEMALEON/MagicInventory (rama `main`).

## Cómo ejecutar

```bash
pip install PySide6 requests
python main.py
```

- Python 3.13 en Windows. `python` no está en el PATH de las shells de Claude: usar
  `C:/Users/josem/AppData/Local/Programs/Python/Python313/python.exe`.
- La base de datos `magic_inventory.db` (SQLite) se crea/actualiza sola al arrancar.
- No hay tests automáticos todavía.

## Arquitectura (por capas)

```
main.py                      -> crea QApplication, carga estilos, abre MainWindow maximizada
src/config.py                -> rutas absolutas (BASE_DIR, DB_PATH, STYLES_PATH), red (REQUEST_TIMEOUT, HTTP_HEADERS), COLORS
src/ui/main_window.py        -> toda la interfaz (QWidget): topbar con buscador, sidebar, panel de carta, tabla de colección
src/ui/styles.qss            -> hoja de estilos Qt (tema azul oscuro)
services/card_service.py     -> fachada entre la UI y api/database (search_card, save_card, get_collection)
services/image_service.py    -> descarga una imagen y devuelve un QPixmap escalado
api/scryfall_api.py          -> búsqueda fuzzy en https://api.scryfall.com/cards/named -> Card
database/database_manager.py -> SQLite: create_database (con migración), add_card, get_all_cards
models/card.py               -> clase Card
ai/recommender.py, assets/   -> vacíos (reservados para la parte de IA)
```

Flujo: buscar -> `search_card()` -> Scryfall -> `Card` -> imagen + datos en el panel ->
"Add to Collection" -> `add_card()` -> se refresca la tabla.

**Regla:** la UI solo habla con `services/`; nunca llama directamente a `api/` ni a `database/`
(excepción actual: `create_database()` en el `__init__` de MainWindow).

## Modelo de datos

Tabla `cards`: `id, name, set_name, type_line, mana_cost, rarity, image_url, quantity,
scryfall_id, set_code, collector_number`.

- **Una fila = una edición concreta (printing)**, identificada por `scryfall_id`
  (índice único parcial `idx_cards_scryfall_id`, solo para filas con id).
- Misma edición -> se suman cantidades. Otra edición de la misma carta -> fila nueva.
- Filas antiguas (anteriores a la migración) tienen `scryfall_id = NULL`. Si se vuelve a añadir
  la misma carta y edición (`name` + `set_name`), `_find_existing_card()` "adopta" esa fila y le
  rellena el id en vez de duplicarla.
- `Card.printing_label` -> texto tipo "Commander Masters (CMM #410)".

## Convenciones

- Código, comentarios, docstrings y textos de la UI en **inglés**; la conversación con el autor en **español**.
- Conexiones SQLite con `with _connect() as conn, conn:` (cierra la conexión y hace commit/rollback).
- Toda petición HTTP lleva `headers=HTTP_HEADERS` y `timeout=REQUEST_TIMEOUT` (Scryfall exige
  User-Agent y Accept, y pide no superar ~10 peticiones/segundo).
- Errores de red de Scryfall -> `ScryfallError`; carta no encontrada -> `None`.
- Nunca rutas relativas: usar las de `src/config.py`.
- Las imports son desde la raíz del proyecto (`from src.config import ...`, `from models.card import ...`).

## Historial de trabajo con Claude

### Hecho (punto 1, nov 2026 — pendiente de commit)
- Identificación de cartas por `scryfall_id` + `set_code` + `collector_number`, con migración
  automática de bases de datos antiguas.
- La colección se carga al abrir la app.
- Rutas absolutas en `config.py` (BD y estilos funcionan se lance desde donde se lance).
- Timeouts y cabeceras en todas las peticiones; mensaje claro si no hay conexión.
- Cartas de doble cara: se usa la imagen y el coste de `card_faces`.
- Bug corregido: tras una búsqueda fallida, "Add to Collection" añadía la carta anterior.
- Bug corregido: al refrescar la tabla podían quedar imágenes de otra carta (`clearContents()`).

### Hecho (selector de edición, 10 nov 2026 — pendiente de commit)
- Tras buscar, `get_printings()` -> `get_card_printings()` recorre `prints_search_uri`
  (paginado, 0,1 s entre páginas) y rellena el `QComboBox` "Edition". Al cambiar la edición se
  actualizan imagen, datos y `current_card`. Si falla la lista, se ofrece solo la edición por defecto.
- `Card.prints_search_uri` existe solo en memoria (no se guarda en la BD).

## Pendiente (en este orden)

1. **Rendimiento de imágenes:** caché en disco (p. ej. `cache/images/<scryfall_id>.jpg`) y
   descarga en segundo plano (QThreadPool/QRunnable o QNetworkAccessManager) para no congelar la UI.
   Ahora cada refresco vuelve a descargar todas las imágenes en el hilo principal.
   La lista de ediciones también se pide en el hilo principal (cartas como Forest tienen ~960
   ediciones / 6 páginas y tardan unos segundos): moverla también a segundo plano.
2. **Navegación:** los botones "Search" y "Collection" de la sidebar no hacen nada; conectarlos
   a vistas separadas (QStackedWidget).
3. **Gestión de la colección:** borrar cartas y editar cantidades desde la tabla.
4. **Limpieza:**
   - `requirements.txt` está en UTF-16 y es un `pip freeze` del entorno completo (PyAutoGUI,
     pynput, keyboard... que no se usan). Dejar solo `PySide6` y `requests`, en UTF-8.
   - Añadir `.gitignore` (`__pycache__/`, `*.db`, `cache/`, `.venv/`).
   - `COLORS` de `config.py` no se usa (los colores están repetidos en `styles.qss`).
   - La regla `QLabel` del `.qss` pone en negrita/16 px todas las etiquetas.

## Roadmap del README (a largo plazo)
Filtros avanzados de la colección (nombre, edición, cantidad, tipo, rareza), contador de vidas
(multijugador, Commander), asistente de IA para interacciones entre cartas, deck builder,
estadísticas, exportar a CSV/JSON, seguimiento de precios.
