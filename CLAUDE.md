# Magic Inventory — contexto para Claude

Aplicación de escritorio para gestionar una colección de cartas de **Magic: The Gathering**.
Proyecto personal de aprendizaje de José Manuel León (Python, APIs, GUI, bases de datos, IA).
Repositorio: https://github.com/JOSEMALEON/MagicInventory (rama `main`).

## Cómo ejecutar

```bash
pip install -r requirements.txt   # solo PySide6 y requests
python main.py
```

- Python 3.13 en Windows. `python` no está en el PATH de las shells de Claude: usar
  `C:/Users/josem/AppData/Local/Programs/Python/Python313/python.exe`.
- La base de datos `magic_inventory.db` (SQLite) se crea/actualiza sola al arrancar.
- No hay tests automáticos todavía.

## Arquitectura (por capas)

```
main.py                      -> crea QApplication, carga estilos, abre MainWindow maximizada
src/config.py                -> rutas absolutas (BASE_DIR, DB_PATH, STYLES_PATH, ASSETS_DIR, IMAGE_CACHE_DIR), red, RARITY_COLORS
src/ui/main_window.py        -> ventana: topbar, sidebar, páginas Search (panel de carta) y Collection (tabla + gestión)
src/ui/edition_dialog.py     -> EditionDialog: elegir otra edición para una carta de la colección (con vista previa)
src/ui/import_page.py        -> ImportPage: pegar/cargar una lista, comprobarla en Scryfall y añadir las cartas
src/ui/widgets.py            -> styled_panel(), set_status(label, text, state), printing_text(card, currency),
                                QuantitySpinBox (ignora la rueda sin foco)
src/ui/background.py         -> BackgroundRunner: run(fn, on_success, on_error) en un QThreadPool (4 hilos); callbacks en el hilo GUI
src/ui/styles.qss            -> tema oscuro (paleta documentada en la cabecera); @ASSETS@ lo sustituye main.py por la ruta absoluta
services/card_service.py     -> fachada UI <-> api/database: search_card, get_printings, save_card, get_collection,
                                remove_cards, set_quantity, change_card_printing
services/image_service.py    -> load_card_image(url, w, h) -> QImage (caché en cache/images/<sha1(url)>.jpg); to_pixmap()
services/list_service.py     -> listas de cartas: parse_card_list, read_list_file (.txt/.csv), resolve_entries,
                                add_found_cards, export_collection (.csv con precios o .txt reimportable)
services/price_service.py    -> refresh_prices() (completa filas antiguas + precios de toda la colección),
                                prices_need_update, last_price_update, get_price_changes, format_money
api/scryfall_api.py          -> búsqueda fuzzy (/cards/named), ediciones (prints_search_uri, o /cards/search
                                q=!"nombre" para cartas de la BD), get_cards_by_identifiers (/cards/collection,
                                lotes de 75), get_set_codes (/sets: nombre de edición -> código)
database/database_manager.py -> SQLite: create_database (con migración), add_card, get_all_cards,
                                delete_cards, update_quantity, change_printing (fusiona si la edición ya existe),
                                save_prices, get_previous_prices
models/card.py               -> clase Card (card.id = id de fila en la BD; price(currency), value(currency))
assets/icons/                -> SVG de la interfaz (flechas de combo/spinbox)
ai/recommender.py            -> vacío (reservado para la parte de IA)
```

Flujo: buscar -> `search_card()` -> Scryfall -> `Card` -> imagen + datos en el panel ->
"Add to Collection" -> `add_card()` -> se refresca la tabla.

**Regla:** la UI solo habla con `services/`; nunca llama directamente a `api/` ni a `database/`
(excepción actual: `create_database()` en el `__init__` de MainWindow).

## Modelo de datos

Tabla `cards`: `id, name, set_name, type_line, mana_cost, rarity, image_url, quantity,
scryfall_id, set_code, collector_number, price_eur, price_eur_foil, price_usd, price_usd_foil,
prices_updated_at`.

Tabla `price_history`: `scryfall_id, date, price_eur, price_eur_foil, price_usd, price_usd_foil`
(clave `scryfall_id + date`: una fila por edición y día; el mismo día se sobrescribe).

- Precios de **una copia no foil**; si la edición solo existe en foil se usa el foil (`Card.price()`).
  Todavía no se distingue si las copias del usuario son foil.
- Cualquier `Card` que llega de Scryfall y se guarda (`add_card`, `change_printing`) guarda también
  sus precios (`_store_prices`).

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
- Nada de red ni disco lento en el hilo GUI: usar `self.background.run(...)`. En el hilo de trabajo
  no se tocan widgets ni `QPixmap` (solo `QImage`). Las respuestas llevan un contador
  (`_search_id`, `_image_id`, `_collection_id`) y se descartan si ya hay una petición más nueva.
- Las imports son desde la raíz del proyecto (`from src.config import ...`, `from models.card import ...`).

## Historial de trabajo con Claude

### Hecho (punto 1, nov 2026 — commit 5ddbd0b)
- Identificación de cartas por `scryfall_id` + `set_code` + `collector_number`, con migración
  automática de bases de datos antiguas.
- La colección se carga al abrir la app.
- Rutas absolutas en `config.py` (BD y estilos funcionan se lance desde donde se lance).
- Timeouts y cabeceras en todas las peticiones; mensaje claro si no hay conexión.
- Cartas de doble cara: se usa la imagen y el coste de `card_faces`.
- Bug corregido: tras una búsqueda fallida, "Add to Collection" añadía la carta anterior.
- Bug corregido: al refrescar la tabla podían quedar imágenes de otra carta (`clearContents()`).

### Hecho (selector de edición, 10 nov 2026 — commit 5ddbd0b)
- Tras buscar, `get_printings()` -> `get_card_printings()` recorre `prints_search_uri`
  (paginado, 0,1 s entre páginas) y rellena el `QComboBox` "Edition". Al cambiar la edición se
  actualizan imagen, datos y `current_card`. Si falla la lista, se ofrece solo la edición por defecto.
- `Card.prints_search_uri` existe solo en memoria (no se guarda en la BD).
- `.gitignore` añadido; `.pyc` y `magic_inventory.db` ya no están en git (commit 15d6920).

### Hecho (rendimiento, 10 nov 2026 — commit c55ace3)
- Caché de imágenes en disco (clave = sha1 de la URL, que incluye la versión de Scryfall;
  escritura atómica con fichero temporal + `os.replace`).
- Búsqueda, lista de ediciones e imágenes (panel y tabla) en segundo plano con `BackgroundRunner`.
  Refrescar la tabla con la caché llena tarda ~0,05 s.

### Hecho (navegación, 10 nov 2026 — commit e943db6)
- `QStackedWidget` con dos páginas: `search_page` (panel de carta) y `collection_page` (tabla +
  resumen "N printings · M cards"). `show_page(page)` cambia de página y marca el botón de la
  sidebar (`QButtonGroup` exclusivo, estilo `#navButton:checked` en el .qss).
- Buscar desde la barra superior lleva siempre a la página Search.
- El `__init__` de MainWindow se dividió en `_build_top_bar/_sidebar/_search_page/_collection_page`.

### Hecho (rediseño visual, 10 nov 2026 — commit 7591f4f)
- Tema oscuro moderno elegido por el autor: fondo `#111318`, paneles `#1B1E26`, acento en **degradados
  de azul** (`#2563EB -> #38BDF8`). El autor pidió que el morado `#8B5CF6` se use solo en momentos
  puntuales donde mejore el diseño (ahora: degradado del logo ◆ y rareza special/bonus).
  Sin reglas globales de fondo: cada panel tiene `objectName` (`#topBar`, `#sidebar`,
  `#cardPanel`...) y se crea con `styled_panel()` (activa `WA_StyledBackground`).
- Panel de carta: imagen 320x446 con esquinas redondeadas (`_round_corners` en image_service),
  nombre, tipo, coste (`format_mana_cost`: "{2}{U}" -> "2 U"), insignia de rareza coloreada
  (`RARITY_COLORS`), edición, y `status_label` con estados info/success/error (propiedad `state`).
  `_show_empty_card()` deja el panel vacío y desactiva "Add to Collection".
- Eliminados `COLORS` y las reglas globales `QLabel`/`QFrame` del .qss.
- Capturas sin ventana para revisar la UI: `QT_QPA_PLATFORM=offscreen` + `QT_QPA_FONTDIR=C:/Windows/Fonts`
  (sin la segunda, el texto sale como cuadrados).

### Hecho (gestión de la colección, 10 nov 2026 — commit 7591f4f)
- Tabla con selección múltiple (Ctrl/Mayús), contador "N selected", columnas
  imagen/nombre/edición/rareza (coloreada)/cantidad. Cada fila guarda `card.id` en `Qt.UserRole`
  (columna nombre); `selected_cards()` devuelve las Cards seleccionadas.
- Cantidad: `QuantitySpinBox` en cada fila; guarda al cambiar sin redibujar la tabla.
- Borrar: botón "Delete", tecla Supr (solo con la tabla enfocada) y menú contextual; siempre con
  confirmación (`QMessageBox.question`).
- Cambiar edición: botón, doble clic o menú contextual -> `EditionDialog`. Si la edición elegida ya
  está en la colección, `change_printing()` suma las cantidades y borra la fila original.
- Filtro instantáneo (oculta filas, no recarga) y orden: nombre, recientes (id), cantidad, edición, rareza.
- Miniaturas en memoria (`self._thumbnails`, url -> QPixmap): ordenar/filtrar no vuelve a decodificar.
- Página Search: `owned_label` -> "In your collection: X of this edition · Y in total".
- Probar sin tocar la colección real: copiar `magic_inventory.db` a un temporal y asignar
  `database.database_manager.DB_PATH` antes de crear la ventana.

### Hecho (limpieza, 10 nov 2026)
- `requirements.txt` reescrito en UTF-8 con solo `PySide6>=6.10` y `requests>=2.32`
  (antes era un `pip freeze` en UTF-16 con PyAutoGUI, pynput, keyboard...).

### Hecho (seguimiento de precios, roadmap, 10 nov 2026 — commit 3bf17f2)
- Precios EUR/USD (normal y foil) de Scryfall guardados por fila + historial diario (`price_history`).
- "Update prices" y actualización automática al abrir si los precios tienen > 20 h (`PRICES_MAX_AGE`).
  Usa `/cards/collection` (75 cartas por petición).
- La actualización también **completa las filas antiguas** sin `scryfall_id`: traduce `set_name` a
  código con `/sets` y busca `{"name", "set"}`; luego `change_printing()` les pone edición exacta y
  precios. Si la edición tiene varias versiones (p. ej. varios Swamp), Scryfall elige una.
- Colección: columnas Price (con ▲/▼ % si cambió ≥ 1 % desde el último precio de un día anterior;
  detalle y foil en el tooltip) y Value (precio × cantidad); cabecera con valor total, variación y
  fecha de actualización; orden por valor o precio.
- Moneda EUR/USD y orden de la tabla se recuerdan con `QSettings("MagicInventory", "MagicInventory")`.
- Search: pastilla de precio ("€4.66 · Foil €12.00") y precio en cada edición del desplegable (también
  en `EditionDialog`). Al llegar la lista de ediciones se usa su copia de la carta: `/cards/named`
  a veces devuelve la misma edición sin precio EUR.
- En los tests, redirigir `QSettings` a un .ini temporal para no tocar el registro del usuario.

### Hecho (importar/exportar listas, 10 nov 2026 — commit 3bf17f2)
- Sidebar: Search, **Import cards**, Collection. `show_page()` usa un dict página -> botón.
- Formato de lista: `4 Sol Ring`, `4x Sol Ring`, `1 Sol Ring (CMM) 410`. Se ignoran líneas vacías,
  comentarios (`#`, `//`), cabeceras ("Deck", "Sideboard:"...) y marcas `*F*`. Una línea sin cantidad
  o con cantidad fuera de 1-999 es un **error de sintaxis con su número de línea**.
- CSV de entrada: columna "Name" obligatoria; "Quantity", "Set Code", "Collector Number" opcionales
  (los alias se prueban por orden de preferencia: "Set Code" gana a "Set"). Se convierte a texto
  en el área de la lista para revisarlo.
- "Check list" busca en lote con `/cards/collection` (acepta minúsculas y la cara frontal de cartas
  dobles). Las no encontradas salen en rojo con su línea y una sugerencia fuzzy ("Did you mean…?",
  máximo 20 peticiones), y además en un `QMessageBox.warning`. Se pueden añadir solo las encontradas;
  editar la lista invalida el resultado.
- "Export…" en la colección: CSV (utf-8-sig para Excel, con precios y valores) o TXT
  (`3 Sol Ring (TMC) 59`), que se puede reimportar conservando la edición exacta (probado).
- Lista de prueba del autor (10 cartas, todas existen): Ancient Den, Bronze Guardian,
  Crystal Skull Isu Spyglass, Golbez Crystal Collector, Illustrious Wanderglyph, Iron Spider Stark
  Upgrade, The Cyber-Controller, Uthros Research Craft, Worldwalker Helm, Wurmcoil Engine.

## Pendiente

- Ideas de mejora: deshacer el último borrado; mostrar colores de rareza también en
  filas seleccionadas; guardar el filtro entre sesiones; marcar copias foil (precio foil).

## Roadmap del README (a largo plazo)
Filtros avanzados de la colección (ya hay filtro de texto; faltan filtros por campo), contador de vidas
(multijugador, Commander), asistente de IA para interacciones entre cartas, deck builder,
estadísticas, exportar a JSON. (Hechos: seguimiento de precios, exportar/importar CSV y TXT.)
