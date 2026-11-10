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
src/ui/decks_page.py         -> DecksPage (lista de mazos + mazo abierto), DeckListCard y NewDeckDialog
src/ui/import_deck_dialog.py -> ImportDeckDialog: crear un mazo desde una lista con secciones
src/ui/got_it_dialog.py      -> GotItDialog: registrar copias compradas de una carta que falta
src/ui/add_to_deck_dialog.py -> AddToDeckDialog: añadir cartas de la colección a un mazo (o a uno nuevo)
src/ui/deck_visual.py        -> DeckVisualView / CardTile: vista visual del mazo con miniaturas
src/ui/flow_layout.py        -> FlowLayout: coloca widgets en filas que se ajustan al ancho
src/ui/life_page.py          -> LifePage (contador de vidas), PlayerPanel (un jugador), PlayerSetupDialog
src/ui/collection_filters.py -> CollectionFilters: filtros por campo de la colección
services/collection_service.py -> colecciones con nombre (fachada); database/collection_manager.py (SQL)
src/ui/dice.py               -> DiceDialog / DieWidget: dados d4-d20 dibujados y animados
services/life_service.py     -> lógica del contador (sin Qt): Game/Player, LifeCounter (cambios + deshacer),
                                guardado en cache/life_game.json
src/ui/charts.py             -> BarChart (curva de maná) y HorizontalBars (colores, tipos) con QPainter
services/deck_service.py     -> FORMATS, agrupación por tipo, validate_deck() -> [DeckIssue], fachada de mazos
database/deck_manager.py     -> tablas decks/deck_cards (create_deck_tables) y CRUD de mazos y cartas
models/deck.py               -> Deck, DeckCard (id, section, card) y SECTIONS/SECTION_LABELS
src/ui/widgets.py            -> styled_panel(), set_status(label, text, state), printing_text(card, currency),
                                mana_pixmap(coste, altura) (símbolos de maná con QSvgRenderer; None -> usar texto),
                                QuantitySpinBox (ignora la rueda sin foco)
src/ui/background.py         -> BackgroundRunner: run(fn, on_success, on_error) en un QThreadPool (4 hilos); callbacks en el hilo GUI
src/ui/styles.qss            -> tema oscuro (paleta documentada en la cabecera); @ASSETS@ lo sustituye main.py por la ruta absoluta
services/card_service.py     -> fachada UI <-> api/database: search_card, get_printings, save_card, get_collection,
                                remove_cards, set_quantity, change_card_printing
services/image_service.py    -> load_card_image(url, w, h) -> QImage (caché en cache/images/<sha1(url)>.jpg); to_pixmap()
services/list_service.py     -> listas de cartas: parse_card_list, read_list_file (.txt/.csv), resolve_entries,
                                add_found_cards, export_collection (.csv con precios o .txt reimportable)
services/symbol_service.py   -> símbolos de maná en SVG: ensure_symbols() (descarga única a cache/symbols/,
                                8 hilos desde el CDN), symbols_ready, split_mana_cost, symbol_path
services/bracket_service.py  -> Commander Brackets: listas de Scryfall (is:gamechanger, otag:mass-land-denial,
                                otag:extra-turn) en cache/brackets.json (semanal) y estimate_bracket()
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
prices_updated_at, foil, collection_id`.

Tabla `collections`: `id, name, kind ('normal' | 'wishlist'), created_at`. La primera es
"Main collection" (la migración mete ahí todas las cartas antiguas).

Tabla `price_history`: `scryfall_id, date, price_eur, price_eur_foil, price_usd, price_usd_foil`
(clave `scryfall_id + date`: una fila por edición y día; el mismo día se sobrescribe).

- **Foil** (10 nov 2026, pedido por el autor): `cards.foil` (0/1, migración: las filas antiguas
  quedan no foil). `Card.price()` usa el precio foil en copias foil y el normal en las demás (si falta
  uno, el otro). `get_price_changes()` devuelve `{(scryfall_id, is_foil): (fecha, precio)}`; usar
  `previous_price(changes, card)`.
- `Card.finishes` (de Scryfall, solo en memoria): `can_be_foil` / `only_foil` controlan la casilla
  Foil (desactivada si no hay foil; marcada y bloqueada si solo existe en foil).
- Cualquier `Card` que llega de Scryfall y se guarda (`add_card`, `change_printing`) guarda también
  sus precios (`_store_prices`).

- **Una fila = colección + edición concreta (printing) + acabado (foil o no)**, identificada por
  `collection_id + scryfall_id + foil` (índice único parcial `idx_cards_collection_printing`, creado en
  `collection_manager.ensure_collections`). Los índices anteriores (`idx_cards_scryfall_id`,
  `idx_cards_printing_finish`) se borran al arrancar y **no deben recrearse**: fallarían en cuanto la
  misma edición esté en dos colecciones.
- Misma colección, edición y acabado -> se suman cantidades. Si no, fila nueva. Una `Card` sin
  `collection_id` va a la primera colección (`_collection_of`).
  `set_foil()` (casilla Foil de la tabla) y `change_printing()` conservan/fusionan por acabado.
- Listas: `*F*`/`*E*` = foil al importar; al exportar se escribe `*F*`; CSV con columna "Foil".
- Los mazos no distinguen foil: "tener" una carta se cuenta por nombre (foil o no).
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
- **Límite de Scryfall:** todas las peticiones a la API pasan por `_request()` en `scryfall_api.py`,
  que espera su turno entre hilos: 0,5 s entre búsquedas (`/cards/search`, `/cards/named`,
  `/cards/collection`, `/cards/random`: máx. 2/s) y 0,1 s para el resto. Un 429 espera
  `Retry-After` y reintenta una vez. No añadir `time.sleep` manuales. (Las imágenes van al CDN
  `cards.scryfall.io`, que no tiene este límite.)
- SQLite con `PRAGMA foreign_keys = ON` en cada conexión (borrar un mazo borra sus cartas).
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

## Deck builder — bases acordadas (10 nov 2026)

Decisiones del autor:
- **Formatos:** Commander + formatos de 60 cartas (Standard, Pioneer, Modern, Legacy, Vintage, Pauper).
- **Relación con la colección:** los mazos son **independientes**; se puede añadir cualquier carta.
  El mazo indica qué cartas tienes, cuáles faltan y cuánto cuesta comprarlas. La colección no cambia.
- **Añadir cartas:** las tres vías — buscar en Scryfall, "Add to deck…" desde la colección, e
  importar/exportar listas (reutilizando `list_service`).
- **Extras v1:** validación del formato, curva de maná y colores, precio del mazo y de lo que falta,
  vista visual agrupada por tipos con miniaturas.

### Modelo de datos (propuesto)
- `decks`: `id, name, format, notes, created_at, updated_at`.
- `deck_cards`: `id, deck_id, scryfall_id, quantity, section` + datos de la carta guardados igual
  que en `cards` (name, set, type_line, mana_cost, rarity, image_url, precios) **más** `cmc`,
  `colors`, `color_identity`, `legalities` (JSON) y `oracle_text`. Índice único
  `(deck_id, scryfall_id, section)`. `ON DELETE CASCADE` desde `decks`.
- `section`: `commander` | `main` | `sideboard` | `maybeboard`.
- `Card` gana `cmc`, `colors`, `color_identity`, `legalities`, `oracle_text`
  (de Scryfall; la colección no los necesita guardar por ahora).
- **"La tengo"** se decide **por nombre** (cualquier edición de la colección cuenta), sumando copias.
  Si el mazo pide 4 y tienes 2, faltan 2 (la carta cuenta como "parcialmente en la colección").

### Apartado "Not in collection" (pedido por el autor)
- Es una **vista calculada, no una sección guardada**: cada carta sigue en su sección real
  (commander/main/sideboard/maybeboard) y aparece además aquí si faltan copias.
- Se recalcula al abrir el mazo y cada vez que cambia la colección (al añadir la carta a la
  colección, desaparece sola del apartado).
- Opción dentro de la pestaña del mazo (interruptor **"Show only cards I don't own"**) que filtra la
  vista y muestra solo las cartas que faltan, con cuántas copias faltan y su precio.
- Cabecera del apartado: "Missing: N cards · €X". Se puede exportar como lista de compra (.txt/.csv).
- Maybeboard no cuenta para el total de lo que falta.

### Botón "Got it" en las cartas que faltan (pedido por el autor)
- Cada carta del apartado tiene un botón **"Got it…"** para registrar las copias que vas comprando.
- Abre un pequeño diálogo: "How many copies of Sol Ring did you get?" con un contador (por defecto
  = las que faltan, mínimo 1; se permite poner más) y la **edición** que se añade (por defecto la
  del mazo; se puede cambiar, con precios, reutilizando el selector de ediciones).
- Al confirmar, esas copias **se añaden a la colección** (`add_card`, se suman si ya tienes esa
  edición) y el apartado se recalcula: faltaban 2 Sol Ring, compras 1 -> queda "falta 1";
  compras 2 -> desaparece del apartado.
- Mensaje de confirmación: "Added 1 × Sol Ring to your collection. 1 still missing."
- Extra: "Got all" en la cabecera del apartado para marcar todas las que faltan de golpe
  (con confirmación).

### Reglas de validación
| Regla | Commander | 60 cartas |
|---|---|---|
| Tamaño | exactamente 100 (comandante incluido) | main ≥ 60, sideboard ≤ 15 |
| Copias | 1 de cada (singleton) | máx. 4 por nombre (main + side) |
| Excepciones | tierras básicas y cartas con "A deck can have any number of cards named…" (vía `oracle_text`) | ídem |
| Legalidad | `legalities["commander"]` debe ser `legal` | `legalities[formato]` = `legal` (o `restricted` = máx. 1 en Vintage) |
| Color | toda carta dentro de la identidad de color del comandante | — |
| Comandante | 1 (o 2 con *Partner*/*Background*: se avisa, no se bloquea) | — |
- La validación **avisa, no bloquea**: se puede guardar un mazo incompleto o ilegal (se está construyendo).
- Maybeboard no cuenta para nada.

### Interfaz
- Sidebar: Search, Import cards, Collection, **Decks**.
- Página Decks: columna izquierda con la lista de mazos (nombre, formato, nº cartas, ✓/⚠) y botones
  New / Rename / Delete; a la derecha el mazo abierto:
  - Cabecera: nombre, formato, contador ("87/100"), valor total y "Missing: N cards · €X".
  - Buscador para añadir cartas (con ediciones y precios, como Search) y "Import list…/Export…".
  - Vista **por tipos** (Commander, Creatures, Planeswalkers, Instants, Sorceries, Artifacts,
    Enchantments, Battles, Lands) en modo lista o modo visual con miniaturas.
  - Cada carta: cantidad editable, sección, marca ✓ tengo / ✗ falta, precio.
  - Panel lateral: avisos de validación, curva de maná (barras 0..7+), colores y tipos.
- Gráficos dibujados con `QPainter` en un widget propio (sin dependencias nuevas), con los colores del tema.
- Colección: "Add to deck…" en el menú contextual y en la barra de acciones.

### Fases de implementación
1. **Base:** tablas + migración, `deck_service`, página Decks con crear/renombrar/borrar mazos,
   añadir por búsqueda, cantidades/secciones, vista lista por tipos, validación.
2. **Análisis:** curva de maná, colores, tipos, valor del mazo, tengo/falta, apartado
   "Not in collection" con el interruptor "Show only cards I don't own", coste de lo que falta y
   botón "Got it…" para pasar a la colección las copias compradas.
3. **Integración:** "Add to deck…" desde la colección, importar/exportar listas del mazo,
   vista visual con miniaturas.

### Fase 1 hecha (10 nov 2026 — commit b3c2103)
- Tablas `decks` y `deck_cards` (con `ON DELETE CASCADE` e índice único deck+printing+sección).
  `Card` y `_card_from_json` ganan `cmc`, `colors`, `color_identity`, `legalities`, `oracle_text`.
- Página **Decks** (sidebar, debajo de Collection): lista de mazos con "Formato · 53/100 ✓/⚠",
  New deck (nombre + formato) / Rename / Delete (con confirmación).
- Mazo abierto: cambiar formato, contador, insignia "✓ Legal"/"⚠ N problems", valor del mazo;
  buscador "Add a card…" con edición (con precios), cantidad y sección (sugiere Commander si el
  mazo de Commander no tiene comandante y la carta puede serlo).
- Cartas agrupadas: Commander, Creatures, Planeswalkers, Battles, Instants, Sorceries, Artifacts,
  Enchantments, Lands, Other, Sideboard, Maybeboard; ordenadas por coste. Cantidad editable,
  menú contextual (Move to…, Change edition…, Remove), Supr, doble clic = cambiar edición,
  vista previa de la carta seleccionada y lista "FORMAT CHECKS".
- Validación probada con cartas reales: tamaño, singleton/4 copias, básicas y Relentless Rats
  ilimitadas, Seven Dwarves máx. 7, prohibidas/no legales, identidad de color, parejas de
  comandantes (Partner/Background/Friends forever), banquillo ≤ 15.
- **Tierras básicas** (`is_basic_land()` en card_service): `get_printings()` solo carga la primera
  página de ediciones (las ~175 más recientes, 1 petición, ~0,5 s en vez de ~3,5 s con las ~930 de
  Swamp) y se preselecciona la más reciente, en el buscador del mazo y en Search. El diálogo
  "Change edition…" usa `get_all_printings()` (todas).
- **Ilustración del comandante en la lista de mazos** (pedido por el autor): cada fila es un
  `DeckListCard` (QWidget con `setItemWidget`) que pinta el `art_crop` del primer comandante en el
  62 % derecho, recortado y con degradado a transparente hacia la izquierda (`CompositionMode_DestinationIn`).
  URL: `art_crop_url()` en image_service (`/normal/` -> `/art_crop/`, sin tocar la BD). Imágenes en
  `self._deck_art` (memoria) + caché en disco. Mazos sin comandante: sin imagen.
- **Selección con los colores del comandante** (pedido por el autor): el resaltado del mazo
  seleccionado lo pinta `DeckListCard` (el `::item:selected` del .qss es transparente): degradado
  con la identidad de color de los comandantes en orden WUBRG + barra de 3 px a la izquierda.
  `MANA_COLORS`: W `#F4E4B0`, U `#3B82F6`, B `#A78BFA` (violeta: negro/gris no se vería sobre el
  fondo oscuro), R `#F87171`, G `#4ADE80`; incoloro `#94A3B8`; mazo vacío, el azul del tema.
- **Mazos sin comandante** (60 cartas, pedido por el autor): usan los **colores del mazo**
  (`deck_colors()`: main + sideboard) para la selección y para una franja de color en el hueco de la
  ilustración (`_paint_color_band`). Cuenta los colores que hay que pagar con maná (`_mana_colors`):
  el maná phyrexiano `{G/P}` **no** cuenta (Mutagenic Growth no hace verde un Izzet; detectado con el
  mazo real "Izzet Prowess"), los híbridos cuentan ambos colores y las cartas sin coste usan `colors`.
- **Importar/exportar mazos completos** (adelantado de la fase 3, pedido por el autor):
  - "Import deck…" (DecksPage) abre `ImportDeckDialog` (src/ui/import_deck_dialog.py): pegar o
    cargar .txt/.csv, "Check list", y crea un mazo **nuevo** con `create_deck_from_list()`.
  - `parse_deck_list()` (list_service) entiende cabeceras Commander/Deck/Main/Sideboard/Companion
    (-> sideboard)/Maybeboard/Considering, también como `SIDEBOARD:` o `// Commander`; `Tokens` se
    salta; "About" + "Name X" (Arena) da el nombre; `*CMDR*` marca el comandante; `*F*`/`*E*` se
    ignoran. Sin cabeceras, todo va al main. `parse_card_list()` (colección) usa el mismo lector y
    pone todo en main.
  - CSV: columna opcional "Section"/"Board"/"Category".
  - `suggest_deck_format()`: Commander si hay comandante o 98-101 cartas; si no, lo elige el usuario.
  - Commander sin comandante en la lista: el diálogo ofrece elegirlo entre las cartas que pueden
    serlo (si solo hay una, preseleccionada). Nombre por defecto: el de la lista, el del archivo,
    el del comandante o "Imported deck".
  - "Export…" en la cabecera del mazo: .txt con `About/Name`, Commander, Deck, Sideboard, Maybeboard
    y ediciones exactas (`deck_as_text()`); reimportarlo da un mazo idéntico (probado).
- Los precios de las cartas del mazo son los del momento de añadirlas (aún no se actualizan con
  "Update prices"; pendiente para la fase 2).

### Hecho (símbolos de maná, 10 nov 2026 — commit eeac1ae)
- Pedido por el autor: costes con los símbolos oficiales en vez de "2 W U R".
- `/symbology` de Scryfall (84 símbolos: híbridos, phyrexianos, {2/W}, {X}, {S}, {15}...) ->
  `cache/symbols/symbols.json` (símbolo -> archivo) + un .svg por símbolo. Se descargan al arrancar
  si faltan (`MainWindow`, en segundo plano) y después `_on_symbols_ready()` redibuja.
- `mana_pixmap()` compone los símbolos en fila (con "//" entre caras), a la resolución real de
  la pantalla, con caché en memoria. Mientras no estén descargados se muestra el texto.
- Se usa en la columna Mana del mazo (`MANA_ICON_SIZE` 17, QLabel transparente a clics) y en la
  pastilla de coste de Search (`SEARCH_MANA_ICON_SIZE` 20). El texto queda en el tooltip.

### Hecho (orden del mazo y brackets, 10 nov 2026 — commit eeac1ae)
- Pedido por el autor. **Orden** dentro de cada grupo por tipo: "Sort by" con Mana value ↑/↓,
  Price ↑/↓ (sin precio al final) y Name (`DECK_SORTS`); se guarda en QSettings (`deck_sort`).
  DecksPage recibe `settings` desde MainWindow.
- **Commander Brackets** (reglas WotC, oct. 2025; lista de Game Changers actualizada el
  9 feb. 2026, 53 cartas; tutores sin restricción desde oct. 2025):
  B1-2 sin Game Changers, B3 hasta 3, B4-5 sin límite; destrucción masiva de tierras solo B4+;
  turnos extra restringidos en B1 y sin encadenar en B2-3.
  - Listas desde búsquedas de Scryfall (siempre al día, sin mantenerlas a mano):
    `is:gamechanger` (53), `otag:mass-land-denial` (111), `otag:extra-turn` (59) ->
    `cache/brackets.json`, renovado cada 7 días al arrancar.
  - `estimate_bracket()` da el bracket **mínimo** que permite el contenido (commander + main):
    Game Changers 1-3 -> 3, >3 -> 4; destrucción de tierras -> 4; turnos extra -> al menos 2.
    B1 vs B2 (intención temática) y B4 vs B5 (cEDH) no se pueden deducir: se muestran "1–2"/"4–5".
    No se comprueban combos de dos cartas ni la velocidad del mazo (se indica).
  - Insignia "Bracket 3 · Upgraded" junto al valor (verde 1-2, celeste 2, ámbar 3, rojo 4-5) y
    motivos en el panel lateral ("BRACKET"). Solo en mazos de Commander.
  - Ojo: Kinnan y otros 9 salieron de la lista en oct. 2025; no fiarse de listas de memoria.
- **Vista previa al abrir un mazo** (pedido por el autor): `_show_default_preview()` muestra el
  comandante (Commander) o la primera carta del árbol según el orden elegido (otros formatos), **sin
  seleccionar la fila** (para que Supr no la borre por accidente). También al añadir la primera carta
  o un comandante. `_clear_preview()` incrementa `_preview_id` para descartar imágenes que aún se
  estén descargando de otro mazo (antes una imagen tardía de otro mazo podía colarse).

### Fase 2 hecha (10 nov 2026 — commit 32a6d58)
- **Precios de mazos al día**: `refresh_prices()` pide en el mismo lote las ediciones de la
  colección y de los mazos (`deck_manager.get_deck_scryfall_ids/update_deck_prices`);
  `deck_cards.prices_updated_at` (migración). Al arrancar se actualiza si la colección **o** los
  mazos tienen precios de > 20 h (`deck_prices_need_update`).
- **Tengo/falta** (por nombre, cualquier edición; maybeboard no cuenta): `deck_service.collection_counts`,
  `needed_counts`, `missing_cards() -> [MissingCard(name, entry, needed, owned)]`.
  - Columna **Own**: ✓ / "1/3" / ✗. Barra "Missing: N cards · €X" (o "✓ You own every card").
  - Grupo calculado **"Not in collection"** al final del árbol (cada fila: "× faltan", coste de lo que
    falta y botón **"Got it…"**). Interruptor **"Show only cards I don't own"** deja solo ese grupo.
  - `GotItDialog` (src/ui/got_it_dialog.py): copias (por defecto las que faltan) + edición (por
    defecto la del mazo, con precios) -> `deck_service.add_to_collection()`. También en el menú
    contextual. **"Got all"** con confirmación (ediciones del mazo). Tras añadir se llama a
    `on_collection_changed` (MainWindow.show_collection).
  - **"Export shopping list…"**: .txt (`2 Sol Ring (CMM) 410`) o .csv con precio y total
    (`list_service.export_shopping_list`).
  - Cambiar una cantidad actualiza al momento cabecera/barra/Own/stats; el grupo "Not in collection"
    se redibuja 600 ms después del último cambio (`_redraw_timer`) para no quitar el foco del contador.
- **Stats** (botones List / Stats): resumen (coste medio sin tierras, tierras, otras cartas, valor,
  lo que falta), curva de maná 0..7+ (`BarChart`), colores y tipos (`HorizontalBars`) en
  src/ui/charts.py, dibujados con QPainter. `deck_service.deck_stats()` (commander + main).

### Fase 3 hecha (10 nov 2026 — commit 5032645). Deck builder completo.
- **"Add to deck…"** en la colección (botón + menú contextual, una o varias cartas):
  `AddToDeckDialog` (src/ui/add_to_deck_dialog.py): mazo existente o "＋ New deck…" (nombre + formato;
  con una sola carta se propone su nombre), sección (sugiere Commander si es una carta que puede serlo
  y el mazo no tiene comandante) y copias de cada carta. Recuerda el último mazo (`last_deck_id` en
  QSettings). `deck_service.add_collection_cards_to_deck()` pide los datos a Scryfall en un lote
  (la colección no guarda cmc/colores/legalidades) y conserva la edición de la colección.
- **Vista visual** (List | Visual | Stats): `DeckVisualView` (src/ui/deck_visual.py), mismos grupos,
  orden e interruptor que la lista; `CardTile` con "×N", "Missing N" (atenuada) y borde de selección;
  clic = vista previa, doble clic = cambiar edición, clic derecho = mismo menú (`_open_card_menu`).
  `FlowLayout` (src/ui/flow_layout.py) reparte las miniaturas según el ancho.
  `move_selected/remove_selected_cards/change_edition` aceptan `entries` (si no, la selección de la lista).
- `_fill_tree()` redibuja la lista (`_fill_list`) y, si está visible, la vista visual.
- Tests con menús: un `QMenu.exec` real bloquea en modo offscreen; sustituir `decks_page.QMenu` por
  una subclase que registre las acciones.

## Contador de vidas

### Fase 1 hecha (10 nov 2026 — commit f6bb60a)
- Decisiones del autor: por ahora app de escritorio en pantalla vertical normal (sin paneles girados
  ni modo mesa; eso, para la futura versión móvil). Prioridad: que sea funcional, hasta 6 jugadores.
- Página **Life counter** (sidebar, la última). Barra: jugadores 2-6, vida inicial 20/30/40,
  New game (con confirmación; conserva nombres, colores y Partner), Who starts? (al azar), Undo (Ctrl+Z).
  Disposición: 2 -> 2 columnas, 3 -> 3, 4 -> 2×2, 5 y 6 -> 3×2.
- Cada jugador (`PlayerPanel`): nombre editable, color de asiento (fondo teñido + barra superior),
  vida grande con −5/−1/+1/+5 y acumulador del último cambio ("−6", se oculta a los 2 s).
  - **Daño de comandante**: una casilla por rival (clic +1, clic derecho −1); resta vida (y quitarlo
    la devuelve); 21 de un mismo comandante elimina.
  - **Partner** (botón por jugador, pedido por el autor): en los paneles de **todos los demás** su
    casilla se divide en dos (A | B) que cuentan por separado; también desdobla su impuesto. Al
    desactivarlo, el daño y los lanzamientos de B se suman a A. Cambiar Partner reconstruye los paneles.
  - Contadores: veneno (10 elimina), experiencia, energía, rad, impuesto (lanzamientos × 2).
  - Marcadores: Monarch e Initiative (únicos: pasan de un jugador a otro), City's blessing.
  - Eliminado: aviso con el motivo y el panel atenuado (`QGraphicsOpacityEffect`); se puede deshacer.
- La partida se guarda tras cada cambio en `cache/life_game.json` y se recupera al abrir la app.
- **Animación de "Who starts?"** (pedida por el autor): primero se elige el jugador al azar
  (`choose_first_player`); luego una luz verde (`PlayerPanel.set_spotlight`) recorre los paneles en
  orden ~3 vueltas, cada paso más lento (de `SPIN_FIRST_STEP_MS` 45 ms a ~500 ms, curva cúbica), y se
  para en el elegido: su panel queda iluminado y la insignia "Starts" brilla (`set_starts_glow`,
  propiedad `glow`) durante `SPIN_HOLD_MS` (3 s). Dura ~4 s; el botón se desactiva mientras tanto.
  `_spin_id` cancela la animación si se reconstruyen los paneles (`rebuild()` lo incrementa).
- Ojo: al reconstruir paneles, `hide()` + `setParent(None)` antes de `deleteLater()` (si no, los
  viejos se siguen dibujando debajo hasta que Qt los borra).
### Fase 2 hecha (10 nov 2026 — commit 6a80d8d): mazos por jugador y dados
- **Mazo por jugador** (pedido por el autor): clic en el nombre -> `PlayerSetupDialog` (nombre +
  mazo). `Player.deck_id` (guardado en el JSON). `LifeCounter.set_player()` cambia nombre, mazo y
  Partner en **un solo** paso de deshacer (`_apply_partner` compartido con `set_partner`).
  - Un mazo con 2 comandantes activa Partner; con 1 lo desactiva; sin mazo no lo toca.
  - Panel: bajo el nombre, el mazo y su insignia de bracket ("B3", colores de `bracketBadge`);
    de fondo el `art_crop` del primer comandante en el 62 % superior, fundido hacia abajo
    (`PlayerPanel.paintEvent`, después del fondo del stylesheet).
  - `deck_service.deck_summary(deck_id)` -> `DeckSummary(deck, commanders, bracket)`; la página los
    cachea (`_summaries`) y los recarga al mostrarse (`reload_decks`, desde `MainWindow.show_page`).
  - **Aviso** arriba si los brackets de la mesa se separan 2 o más (`BRACKET_WARNING_GAP`).
  - El color de asiento se mantiene (identifica las casillas de daño de comandante).
- **Dados** (src/ui/dice.py): botón "🎲 Dice" -> `DiceDialog` no modal con d4/d6/d8/d10/d12/d20,
  cada uno con su forma (triángulo, cuadrado, rombo, cometa, pentágono, hexágono con cara triangular).
  Animación: 14 pasos de 35 ms a ~215 ms con números al azar y giro que se frena; al final el
  resultado con borde verde (solo el último dado tirado), texto "d20: 17 (max!)" e historial (30).
- Ideas pendientes: estadísticas por mazo, contador de turnos y temporizador, historial y gráfico
  de vidas, Planechase/Archenemy, atajos de teclado, ventana aparte.

## Varias colecciones y filtros (10 nov 2026 — commit PENDING)

### Colecciones con nombre
- `database/collection_manager.py` (tabla, migración, `move_cards`, `delete_collection`) y
  `services/collection_service.py` (fachada para la UI).
- Collection: selector "All collections (N)" / cada colección (★ = wishlist) + "Manage ▾" (New,
  Rename, Use as wishlist, Delete — al borrar con cartas, `QInputDialog.getItem` pregunta a qué
  colección moverlas o si borrarlas; la última colección no se puede borrar). La vista elegida se
  recuerda (`shown_collection_id` en QSettings; 0 = todas).
- "All collections" muestra la columna `COL_COLLECTION`; el valor excluye las wishlists
  ("COLLECTION VALUE (WITHOUT WISHLISTS)"); una wishlist sola muestra "WISHLIST COST".
- "Move to…" (barra + menú contextual): mueve filas a otra colección fusionando; con una sola fila de
  varias copias pregunta cuántas (`QInputDialog.getInt`).
- "Add to:" en Search (`add_target_input`, recordado en `add_collection_id`) e Import cards
  (`ImportPage.set_collections`); "Got it…" elige colección (wishlists al final); "Got all" usa la
  primera colección que cuenta como "tengo".
- **Wishlist**: sus cartas no cuentan como "tengo" (`deck_service.collection_counts` usa
  `owned_collection_ids`); Search muestra "★ N on your wishlist" y en qué colecciones está la carta.
- `MainWindow.refresh_collections()` rellena todos los selectores; `show_collection()` la llama
  siempre (los contadores cambian al añadir/mover). `self.all_cards` = todas las colecciones;
  `self.collection_cards` = las de la vista elegida.
- Exportar: la colección mostrada; en "All collections" el CSV lleva columna "Collection".

### Filtros por campo (`src/ui/collection_filters.py`)
- Botón "Filters" (muestra "Filters (N)" con N filtros activos) despliega `CollectionFilters`:
  rareza y color en fichas (W U B R G, Colorless, Multicolor), tipo, edición (las de la vista),
  acabado, precio desde/hasta (en la moneda elegida; 0 = sin límite) y copias mínimas.
- Se combinan con el filtro de texto en `_apply_filter` (ocultan filas, no recargan).
- Color: de los símbolos del coste de maná (`card_colors`); sin coste de color = Colorless.

### Ideas pendientes de colecciones
- Wishlist con precio objetivo y aviso cuando baje; copiar (no solo mover) entre colecciones;
  elegir por mazo qué colecciones cuentan; guardar los filtros entre sesiones.

## Pendiente

- Roadmap: asistente de IA, exportar a JSON.
- **Contador de vidas — aparcado por decisión del autor (10 nov 2026).** Retomar más adelante con:
  1. Estadísticas por mazo: guardar cada partida terminada (jugadores, mazos, ganador y forma de
     victoria: vida, veneno, daño de comandante…) y mostrar victorias/derrotas en la página Decks.
  2. Contador de turnos con el jugador activo resaltado; temporizador o reloj de ajedrez opcional.
  3. Historial turno a turno y gráfico de vidas al final de la partida (reutilizar `charts.py`).
  4. Planechase y Archenemy con las cartas reales de Scryfall (`type:plane`, `type:scheme`).
  5. Atajos de teclado (1-6 elegir jugador, ↑/↓ vida) y ventana aparte / segundo monitor.
  6. Versión móvil: paneles girados hacia cada jugador (modo mesa); por ahora no, es app de escritorio.
- Ideas de mejora: deshacer el último borrado; mostrar colores de rareza también en
  filas seleccionadas; guardar el filtro entre sesiones.

## Roadmap del README (a largo plazo)
Filtros avanzados de la colección (ya hay filtro de texto; faltan filtros por campo), contador de vidas
(multijugador, Commander), asistente de IA para interacciones entre cartas, deck builder,
estadísticas, exportar a JSON. (Hechos: seguimiento de precios, exportar/importar CSV y TXT.)
