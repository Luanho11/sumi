# Guía de XARA: cómo montarlo y cómo funciona

Esta guía es para usar XARA sin conocimientos técnicos. Sigue los pasos en orden. Si algo no sale como se describe, anota en qué paso ocurrió y qué mensaje apareció.

---

## 1. Qué hace XARA, en pocas palabras

XARA une las computadoras de tu casa para que trabajen juntas cuando eso ayuda, y **mide solo si de verdad ayuda**.

- Instalas lo mismo en cada computadora.
- La primera que enciendes hace de **coordinador**. Funciona como el "jefe de cocina": reparte el trabajo y lleva la cuenta.
- Las demás se unen solas. No hace falta escribir direcciones ni configurar nada.
- Desde el navegador de la computadora coordinadora ves un **panel** con todos los equipos y unos botones para lanzar pruebas.
- Cada prueba **guarda sus datos sola**: tiempos, uso de procesador y memoria cada 2 segundos, red, resultados y un veredicto. No tienes que anotar nada a mano.

## 2. Qué necesitas

| Qué | Dónde | Para qué |
|---|---|---|
| Las dos computadoras encendidas y en el mismo router | — | Que puedan verse |
| Python (gratis) | En las dos | Es el programa que ejecuta XARA |
| La carpeta `prototipo` de XARA | En las dos | El propio XARA |
| llama.cpp para Windows (gratis) | En las dos | Solo para las pruebas de IA (P3, P3b y P4) |
| Un modelo de IA (archivo `.gguf`) | Solo en la PC coordinadora | Solo para las pruebas de IA. XARA lo copia solo a la otra cuando hace falta |
| Nada más para la prueba de fotos (P5) | — | XARA instala solo el complemento que procesa fotos y crea las fotos de prueba |

**Recomendación:** que la **PC de escritorio** sea el coordinador, porque está conectada por cable.

## 3. Instalación (una sola vez)

### Paso 1. Instalar Python en las dos computadoras

1. Entra en **python.org/downloads/windows**.
2. Busca la versión más reciente de **Python 3.13** y descarga **"Windows installer (64-bit)"**.
3. Abre el archivo descargado.
4. **Importante:** en la primera pantalla marca la casilla **"Add python.exe to PATH"**.
5. Pulsa **Install Now** y espera a que termine. Al final pulsa **Close**.

### Paso 2. Copiar XARA en las dos computadoras

1. Copia el archivo `XARA.zip` en cada computadora (descárgalo en las dos o pásalo con un pendrive).
2. Haz **clic derecho** sobre `XARA.zip` → **Extraer todo** → **Extraer**. Usa siempre la carpeta extraída: los archivos no funcionan si los abres desde dentro del zip.
3. Entra en la carpeta `prototipo`. Dentro verás estos archivos, entre otros: `iniciar_xara.bat`, `abrir_cortafuegos.bat`, `instalar_ia.bat`, `xara.py`, `panel.html` y las carpetas `motores` y `modelos`.

### Paso 3. Dar permiso de red (en las dos computadoras)

Windows bloquea por defecto las conexiones que llegan de otras computadoras. Este paso las permite solo dentro de tu red de casa.

1. Haz **clic derecho** en `abrir_cortafuegos.bat` y elige **"Ejecutar como administrador"**. Acepta el aviso.
2. Comprueba que tu red es **privada**: abre **Configuración → Red e Internet**, entra en tu conexión (Wi-Fi o Ethernet) y elige **"Red privada"**.

> Si más adelante Windows muestra una ventana preguntando si permites que **Python** use la red, marca **Redes privadas** y pulsa **Permitir**.
>
> Si al abrir un `.bat` aparece **"Windows protegió su PC"**, pulsa **Más información → Ejecutar de todas formas**. Sale porque los archivos vienen de Internet.

### Paso 4 (solo para las pruebas de IA). Instalar llama.cpp y los modelos

Puedes saltarte este paso y volver a él después: las pruebas P1 y P2 funcionan sin él. Necesitas Internet.

1. En **cada computadora**, instala el paquete gratuito de Microsoft que necesita llama.cpp: descarga **https://aka.ms/vs/17/release/vc_redist.x64.exe**, ábrelo, marca "Acepto" y pulsa **Instalar**. Si dice que ya está instalado, ciérralo.
2. En **cada computadora**, haz doble clic en **`instalar_ia.bat`**.
3. XARA descarga **llama.cpp** (el programa que ejecuta la IA) y lo deja en la carpeta `motores`.
4. Después pregunta si ese equipo será el **coordinador**:
   - En la **PC** responde `s`. Te ofrecerá tres modelos de IA; escribe `s` para cada uno que quieras:
     - **Modelo pequeño** (1 GB), para la prueba P4.
     - **Modelo grande** (5,4 GB), para la prueba P3. Tarda bastante en bajar.
     - **Modelo de 14B** (7,9 GB), para la prueba P3b. Es el que más tarda en bajar.
   - Si ya tenías los dos primeros, solo te ofrecerá el de 14B.
   - En la **laptop** responde `n`. No necesita modelos: XARA se los copia cuando hacen falta.
5. Cuando termine verás "listo". Pulsa una tecla para cerrar la ventana.

Si aparece "No se pudo terminar la instalación", vuelve a abrir `instalar_ia.bat`; lo que ya se descargó no se baja otra vez. Si sigue fallando, copia el mensaje y avísame.

## 4. Arrancar XARA (cada vez que lo uses)

> **Si ya tenías una versión anterior de XARA** (con llama.cpp y los modelos), no lo instales de nuevo. Extrae el nuevo `XARA.zip` en otra carpeta y copia solo **`xara.py`** y **`panel.html`** dentro de la carpeta `prototipo` de la **PC**, reemplazando los anteriores. La laptop se actualiza sola al conectarse.

1. En la **PC de escritorio**, haz doble clic en **`iniciar_xara.bat`**.
   - Se abre una ventana negra. La primera vez tarda un poco más, porque instala un complemento.
   - Al cabo de unos segundos verás: `XARA 0.4 listo. Panel: http://localhost:8765`.
   - **No cierres esa ventana** mientras uses XARA.
2. En la **laptop**, haz doble clic en **`iniciar_xara.bat`**.
   - Verás: `conectado al coordinador ... como <nombre de la PC>`.
3. En la PC, abre el navegador y entra en **http://localhost:8765**.

Si arrancas las dos a la vez, puede que ambas intenten ser coordinador. Arranca **primero la PC** y espera a que diga "listo".

## 5. Usar el panel

### Equipos conectados

Cada computadora aparece en una tarjeta:

- **Punto verde:** conectada. **Punto rojo:** dejó de responder.
- **CPU:** cuánto trabaja su procesador ahora.
- **RAM:** memoria usada del total.
- **Latencia:** lo que tarda un mensaje en ir y volver. Por cable suelen ser unos pocos milisegundos; por Wi-Fi, algo más.
- **En batería:** si la laptop está **desenchufada**, el resultado no vale, porque en batería el procesador va más lento. **Enchúfala antes de cada prueba.**

### Las seis pruebas

Pulsa **Iniciar** en una prueba y espera. En "Prueba en curso" verás qué está haciendo en cada momento. Solo se puede ejecutar una prueba a la vez.

| Prueba | Qué comprueba | Qué hace XARA solo | Duración aproximada |
|---|---|---|---|
| **P1 · Comunicación** | Que los equipos se pasan trabajo correctamente | Envía 20 tareas cortas, cuenta cuántas vuelven bien y mide la velocidad del procesador de cada equipo | Menos de 1 minuto |
| **P2 · Repartir tareas** | Si juntos terminan antes un lote de trabajo | Ejecuta el mismo lote en la PC sola, en la laptop sola y en las dos. Repite cada caso varias veces y calcula la mejora | Unos minutos |
| **P3 · IA repartida** | Si repartir un modelo entre los dos equipos lo hace ir más rápido | Mira la memoria libre de cada equipo y decide cómo repartir. Mide la PC sola y luego las dos juntas | De minutos a una hora, según el modelo |
| **P3b · IA que no cabe en un equipo** | Si juntando la memoria de los dos se puede usar un modelo que **no cabe** en la PC sola | Comprueba que el modelo no cabe en la PC pero sí entre las dos, lo reparte y mide su velocidad. No lo mide en la PC sola, porque ahí tendría que leerse del disco | De 20 a 40 minutos la primera vez |
| **P4 · IA por lotes** | Si dos equipos responden más preguntas por minuto que uno | Copia el modelo a la laptop si no lo tiene, arranca la IA en cada equipo y reparte 10 preguntas. Repite cada caso 3 veces | Unos 15 minutos |
| **P5 · Fotos por lotes** | Si dos equipos preparan antes un lote de fotos para una tienda en línea | La primera vez crea 120 fotos de prueba de 12 megapíxeles, como las de un celular. Cada equipo pide una foto a la PC, la achica a 2000 píxeles, le pone la marca de agua "XARA", saca una versión WebP y una miniatura, y devuelve las tres a la PC. Mide la PC sola, la laptop sola y las dos, 3 veces cada caso | Unos 10 a 15 minutos |

**Antes de cada prueba:** cierra los demás programas, enchufa la laptop y no uses las computadoras mientras dure.

### Cómo correr P3b

P3b es la prueba que demuestra que XARA **suma la memoria** de los equipos. Usa el modelo de 14B (7,4 GB en memoria), que no cabe en la memoria libre de la PC pero sí en la de las dos juntas. Para que entre, los dos equipos tienen que tener casi toda su memoria libre:

1. Si aún no tienes el modelo de 14B, abre `instalar_ia.bat` en la **PC** y responde `s` al modelo de 14B (Paso 4).
2. **Reinicia la laptop** y no abras nada en ella, salvo `iniciar_xara.bat`. Es la que menos memoria tiene.
3. En la **PC** cierra todo menos XARA y **una sola pestaña** del navegador con el panel.
4. Enchufa la laptop.
5. En el panel, en la tarjeta **P3b**, deja elegido el modelo `Qwen2.5-14B-Instruct-Q3_K_L.gguf` y pulsa **Iniciar**.
6. No uses las computadoras hasta que termine. La primera vez XARA envía unos 1,5 GB del modelo a la laptop por Wi-Fi.

Cuando termine, pulsa **ver** en la tabla de resultados. La línea **capacidad** dice si se logró y a qué velocidad:

- **"Lograda: el modelo de 7,4 GB no cabe en la PC... y corrió repartido a X palabras por segundo"**: la memoria de los dos equipos se usó junta. Una velocidad cercana a 1 palabra por segundo es lo esperado (es una estimación, todavía no medida).
- **"No cabe ni entre todos los equipos"**: falta memoria libre. Repite los pasos 2 y 3 y vuelve a probar.
- **"No lograda: el reparto falló"**: copia el informe y avísame.

El veredicto de P3b usa la misma regla que P3: **Favorable** si va a 1,5 palabras por segundo o más, **Técnicamente viable** si va entre 0,5 y 1,5, y **Desfavorable** si va a menos de 0,5.

### P5 con tus propias fotos

Por defecto P5 usa fotos de prueba que crea solo. Para probar con fotos reales (por ejemplo, las de un producto):

1. En la **PC**, copia las fotos (`.jpg` o `.png`) en la carpeta `fotos`, dentro de `prototipo`.
2. En el panel, en la tarjeta P5, elige **"Carpeta fotos"** y pulsa **Iniciar**.

Tus fotos originales no se modifican: las versiones nuevas se guardan aparte (ver la sección 6).

En el informe de P5, **por_foto_s** dice cuánto tardó cada equipo, en promedio, en **bajar** cada foto, **procesarla** y **subir** el resultado, y **red_pct** qué parte de ese tiempo se fue en la red. Si la laptop pasa más tiempo enviando fotos por Wi-Fi que procesándolas, repartir ayuda poco.

### Cómo leer el veredicto

| Veredicto | Qué significa |
|---|---|
| **Favorable** | Juntas rinden claramente mejor. La idea funciona en este caso. |
| **Técnicamente viable** | Funciona, pero la mejora es pequeña. |
| **Desfavorable** | Juntas no mejoran, o empeoran. Es un resultado válido y útil: dice dónde no vale la pena. |
| **No concluyente** | Los tiempos variaron demasiado entre repeticiones. Repite la prueba sin usar las computadoras. |
| **Inválido** | La prueba falló. Pulsa **ver** para saber por qué. |

En la tabla de resultados, **ver** muestra el informe completo de cada prueba.

## 6. Dónde quedan los datos

Todo se guarda en la carpeta `datos` de la **PC coordinadora**:

| Archivo o carpeta | Qué contiene |
|---|---|
| `datos/xara.db` | Base de datos con todo lo medido |
| `datos/informes/` | Un informe por prueba, con equipos, recursos, resultado y pasos |
| `datos/logs/` | Mensajes internos de llama.cpp, útiles si algo falla |
| `datos/fotos_prueba/` | Las 120 fotos de prueba de P5 (se crean una vez, unos 330 MB) |
| `datos/fotos_resultado/` | Una carpeta por cada P5 con las fotos ya preparadas, para que compruebes que salieron bien (unos 50 MB por prueba; puedes borrarlas) |

Desde el panel, en **"Descargar datos"**, puedes bajar cada tabla en un archivo que se abre con **Excel**:

- **Pruebas:** una fila por prueba, con su veredicto.
- **Resultados IA:** velocidades de la IA en cada caso (palabras por segundo).
- **Lotes:** duración de cada lote y reparto entre equipos.
- **Tareas:** cada tarea, el equipo que la hizo y su duración.
- **Métricas por segundo:** CPU, memoria, red y latencia de cada equipo, cada 2 segundos.
- **Equipos:** las características de cada computadora.

## 7. Cómo funciona por dentro (sin tecnicismos)

1. **Se encuentran solos.** Al arrancar, XARA "pregunta en voz alta" en la red si hay un coordinador. Si nadie responde, prueba la última dirección de coordinador que usó; si tampoco responde, ese equipo se convierte en coordinador. Si alguien responde, se une a él. Es la misma idea que usa **exo**.
2. **Se actualizan solos.** Al unirse, cada equipo compara su `xara.py` con el de la PC coordinadora. Si es distinto, copia el de la PC y se reinicia. Así basta con actualizar XARA en la PC.
3. **Cada equipo se presenta.** Cuenta su procesador, su memoria, sus discos y si tiene llama.cpp. Después envía un "latido" cada 2 segundos con su uso de CPU, memoria y red. Así el coordinador sabe en todo momento cuánto puede dar cada uno.
4. **El trabajo se reparte "a demanda".** El coordinador no impone cuánto hace cada uno. Cada equipo **pide** trabajo cuando termina lo anterior, así que el más rápido hace más sin configurar nada. Es como funcionan **BOINC**, **HTCondor** y **Flamenco**.
5. **Si un equipo se cae, nada se pierde.** Si una tarea no vuelve a tiempo, se entrega a otro equipo.
6. **Para la IA, decide la técnica según la memoria.**
   - Si el modelo cabe en un equipo, lo usa ahí.
   - Si no cabe en ninguno pero sí entre los dos, lo **parte por capas**: cada equipo guarda un tramo, en proporción a su memoria libre. Es la idea de **exo** y la técnica de **llama.cpp**.
   - Si no cabe ni entre los dos, lo avisa.
7. **Atraviesa los repetidores.** Si en casa hay un repetidor que arma su propia red, la PC no puede llegar a la laptop, pero la laptop sí puede llegar a la PC. En P3, XARA lo detecta y hace que la laptop abra la conexión hacia la PC. El paso aparece en "Prueba en curso".
8. **Lleva los archivos a quien los necesita.** Si la laptop no tiene el modelo, XARA se lo copia desde la PC. En P3 también le copia llama.cpp si tiene otra versión, porque los dos equipos deben usar la misma. Es la idea de **Incredibuild**: el ayudante no necesita tenerlo todo instalado.
9. **Con las fotos, el trabajo viaja por la red.** Las fotos están en la PC: para que la laptop ayude, cada foto tiene que ir por Wi-Fi y volver ya procesada. P5 mide ese costo por separado, porque es lo que decide si repartir vale la pena. Es el mismo reparto "a demanda" del punto 4: cada equipo pide la siguiente foto al terminar la anterior.
10. **Mide y compara siempre contra un solo equipo.** Cada prueba incluye la referencia de cada equipo trabajando solo, repite las mediciones y descarta la primera, que es de "calentamiento". Con eso calcula el veredicto.

## 8. Problemas frecuentes

| Qué pasa | Qué hacer |
|---|---|
| "No se encontró Python" | Repite el Paso 1 y marca "Add python.exe to PATH". Después cierra y vuelve a abrir el `.bat`. |
| La laptop no aparece en el panel | Revisa el Paso 3 en **las dos** computadoras. Si sigue sin aparecer, cierra XARA en la laptop y conéctala con la dirección de la PC, que aparece en su ventana de XARA después de "en la red:". En la carpeta `prototipo`, escribe `cmd` en la barra de dirección, pulsa Enter y escribe `py -3 xara.py equipo --coord IP_DE_LA_PC:8765`. XARA recuerda esa dirección: las siguientes veces basta con `iniciar_xara.bat`. Suele pasar cuando las direcciones de las dos computadoras empiezan distinto (por ejemplo 192.168.18.x y 192.168.68.x), porque hay dos routers en casa. |
| Falta `VCRUNTIME140.dll` | Instala el paquete de Microsoft del Paso 4 (punto 1) en esa computadora y vuelve a abrir XARA. |
| Las dos computadoras dicen ser coordinador | Cierra las dos ventanas. Arranca primero la PC, espera a que diga "listo" y luego la laptop. |
| P3b dice que el modelo no cabe ni entre todos los equipos | Reinicia la laptop, cierra los programas de la PC y repite la prueba (ver "Cómo correr P3b"). |
| P3, P3b o P4 dicen que falta llama.cpp | Ejecuta `instalar_ia.bat` **en cada equipo** (Paso 4). |
| Windows avisa de que el programa "podría ser peligroso" | Es el aviso habitual con programas descargados de Internet. Pulsa **Más información → Ejecutar de todas formas**. `instalar_ia.bat` descarga llama.cpp solo de su página oficial en GitHub. |
| P5 dice que no pudo instalar Pillow | Ese equipo necesita Internet la primera vez para bajar el complemento de fotos. Conéctalo y repite la prueba. |
| La prueba tarda mucho con un modelo grande | Es normal en P3: el modelo se envía por la red la primera vez. Las siguientes van más rápido, porque cada equipo guarda una copia. |

## 9. Seguridad

XARA está pensado para **tu red de casa**. No tiene contraseña, y llama.cpp avisa de que su modo de reparto no es seguro en redes abiertas. **No lo uses en redes públicas** (cafeterías, universidades, oficinas compartidas).
