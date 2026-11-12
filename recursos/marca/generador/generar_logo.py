# Generador del logo de ProxLaunch en SVG limpio (geometría a mano + texto convertido a trazos).
import sys, pathlib
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

AQUI = pathlib.Path(__file__).parent
# Requiere Montserrat[wght].ttf (OFL) junto a este script; se descarga de github.com/google/fonts (ofl/montserrat)
FUENTE = AQUI / "Montserrat-var.ttf"
SALIDA = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else AQUI.parent
SALIDA.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- paletas
COLOR = {
    "claro": dict(  # para fondos claros (logo original)
        p=("#46B9D6", "#2A5F82"),            # P: turquesa arriba -> azul pizarra abajo
        srv=("#4FB5D0", "#F07A36"),          # servidores: turquesa -> naranja
        srv_rell=("#FFFFFF", "#E3F3F9"),
        cuerpo=("#FFFFFF", "#CFEAF4"),
        borde=("#3EA9C8", "#F26B2C"),        # contorno del cohete
        punta=("#F7942E", "#E23A3A"),
        aleta=("#2F8DB4", "#5CC6DF"),
        ventana=("#3FA6C5", "#F07A36"),
        fuego=("#F7A13A", "#3EA9C8"),
        prox="#2B3C4B", launch=("#2F8FB2", "#3FB0CC"),
    ),
    "oscuro": dict(  # para fondos oscuros: misma idea con más luz
        p=("#6FD0E8", "#3A86B0"),
        srv=("#6CC9E0", "#F58A45"),
        srv_rell=("#2A3A4A", "#22303D"),
        cuerpo=("#FFFFFF", "#CFEAF4"),
        borde=("#5CC3DE", "#F57A3A"),
        punta=("#F9A040", "#E8494A"),
        aleta=("#4BB3D6", "#8AD9EC"),
        ventana=("#4FB5D3", "#F07A36"),
        fuego=("#F9A040", "#5CC3DE"),
        prox="#E8EEF2", launch=("#5CC3DE", "#7FD3E8"),
    ),
    "icono": dict(  # sobre el fondo azul marino del icono: monocromo claro
        p=("#8FCDEB", "#3C7FC0"),            # P en escala de azul medio: queda atrás
        srv=("#E9F7FC", "#7CCCE6"),
        srv_rell=("#2A4E86", "#21407A"),
        cuerpo=("#FFFFFF", "#D6EEF7"),
        borde=("#BFE7F4", "#7FD3EA"),
        punta=("#FFB25A", "#FF6A3D"),        # nariz cálida, a juego con la flama
        aleta=("#BFE7F4", "#5CB8DA"),
        ventana=("#1F3F7A", "#1F3F7A"),
        fuego=("#FFD36B", "#FF7A2F"),        # flama cálida: amarillo -> naranja
        prox="#FFFFFF", launch=("#7FD3EA", "#9FE0F2"),
    ),
}


def grad(id_, c, x1=0, y1=1, x2=1, y2=0):
    return (f'<linearGradient id="{id_}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">'
            f'<stop offset="0" stop-color="{c[0]}"/><stop offset="1" stop-color="{c[1]}"/></linearGradient>')


# ---------------------------------------------------------------- geometría (lienzo 512x512)
# "P": trazo grueso con hueco interior (evenodd)
P = ("M118 472V58H292C362 58 404 100 404 150C404 200 362 242 292 242H176V472Z"
     "M176 114H288C327 114 346 130 346 150C346 170 327 186 288 186H176Z")

# Cohete en coordenadas locales (apunta hacia arriba, origen en su centro)
COHETE_CUERPO = "M0 -170C46 -128 54 -50 44 52L-44 52C-54 -50 -46 -128 0 -170Z"
COHETE_PUNTA = "M0 -170C26 -146 38 -118 43 -92L-43 -92C-38 -118 -26 -146 0 -170Z"
COHETE_ALETA_I = "M-46 -44C-104 -34 -132 20 -128 84C-108 50 -80 34 -46 34Z"
COHETE_ALETA_D = "M46 4C84 24 94 70 86 120C76 96 62 86 44 80Z"
COHETE_TOBERA = "M-30 52H30L24 80H-24Z"
FUEGO = "M0 92C22 120 20 150 0 196C-20 150 -22 120 0 92Z"
# Estelas de velocidad (en coordenadas locales, por detrás del cohete)
ESTELAS = ["M-40 112Q-50 170 -70 236Q-44 172 -28 114Z", "M-7 206Q-3 250 0 300Q3 250 7 206Z", "M40 112Q50 170 70 236Q44 172 28 114Z"]

ROTACION = 42          # grados (apunta arriba a la derecha)
CENTRO = (282, 222)
ESCALA = 1.3    # posición del cohete sobre la P y los servidores


def servidores():
    """Tres placas apiladas en perspectiva oblicua (de abajo hacia arriba)."""
    piezas = []
    for i, y in enumerate((392, 330, 268)):
        # cara superior + cara frontal + cara lateral derecha, como un solo contorno
        contorno = (f"M262 {y}L318 {y-40}H462Q478 {y-40} 478 {y-24}V{y-10}"
                    f"L432 {y+30}H272Q262 {y+30} 262 {y+20}Z")
        piezas.append((contorno, y))
    return piezas


def simbolo(pal, pref, con_hueco=True):
    """Devuelve (defs, cuerpo) del símbolo con prefijo de ids pref."""
    c = COLOR[pal]
    tr = f"translate({CENTRO[0]} {CENTRO[1]}) rotate({ROTACION}) scale({ESCALA})"
    defs = [
        grad(f"{pref}p", c["p"], 0, 0, 0, 1),
        grad(f"{pref}s", c["srv"], 0, 1, 1, 0),
        grad(f"{pref}sr", c["srv_rell"], 0, 0, 0, 1),
        grad(f"{pref}cu", c["cuerpo"], 0, 0, 1, 1),
        grad(f"{pref}b", c["borde"], 0, 1, 0, 0),
        grad(f"{pref}pu", c["punta"], 0, 1, 0, 0),
        grad(f"{pref}a", c["aleta"], 0, 1, 1, 0),
        grad(f"{pref}v", c["ventana"], 0, 1, 1, 0),
        grad(f"{pref}f", c["fuego"], 0, 0, 0, 1),
    ]
    # máscara: separación (hueco) alrededor del cohete sobre la P y los servidores
    silueta = (f'<g transform="{tr}" fill="#000" stroke="#000" stroke-width="30" stroke-linejoin="round">'
               f'<path d="{COHETE_CUERPO}"/><path d="{COHETE_ALETA_I}"/><path d="{COHETE_ALETA_D}"/>'
               f'<path d="{COHETE_TOBERA}"/><path d="{FUEGO}" stroke-width="22"/>'
               + "".join(f'<path d="{e}" stroke-width="18"/>' for e in ESTELAS) + '</g>')
    if con_hueco:
        defs.append(f'<mask id="{pref}m" maskUnits="userSpaceOnUse" x="0" y="0" width="512" height="512">'
                    f'<rect width="512" height="512" fill="#fff"/>{silueta}</mask>')
    fondo = []
    fondo.append(f'<path d="{P}" fill="url(#{pref}p)" fill-rule="evenodd"/>')
    for contorno, y in servidores():
        fondo.append(f'<path d="{contorno}" fill="url(#{pref}sr)" stroke="url(#{pref}s)" '
                     f'stroke-width="15" stroke-linejoin="round"/>')
        # ranura y dos luces en la cara frontal
        fondo.append(f'<path d="M290 {y+8}H400" stroke="url(#{pref}s)" stroke-width="7" stroke-linecap="round"/>')
        fondo.append(f'<circle cx="420" cy="{y+8}" r="5.5" fill="url(#{pref}s)"/>'
                     f'<circle cx="440" cy="{y-8}" r="5.5" fill="url(#{pref}s)"/>')
    mascara = f' mask="url(#{pref}m)"' if con_hueco else ""
    cuerpo = [f'<g{mascara}>' + "".join(fondo) + "</g>"]
    cohete = [
        f'<g transform="{tr}" stroke-linecap="round" stroke-linejoin="round">',
        "".join(f'<path d="{e}" fill="url(#{pref}f)"/>' for e in ESTELAS),
        f'<path d="{FUEGO}" fill="url(#{pref}f)"/>',
        f'<path d="{COHETE_ALETA_I}" fill="url(#{pref}a)"/>',
        f'<path d="{COHETE_ALETA_D}" fill="url(#{pref}a)"/>',
        f'<path d="{COHETE_TOBERA}" fill="url(#{pref}a)"/>',
        f'<path d="{COHETE_CUERPO}" fill="url(#{pref}cu)" stroke="url(#{pref}b)" stroke-width="12"/>',
        f'<path d="{COHETE_PUNTA}" fill="url(#{pref}pu)"/>',
        f'<path d="M-40 28H40" stroke="url(#{pref}b)" stroke-width="10"/>',
        f'<circle cx="0" cy="-38" r="23" fill="url(#{pref}v)" stroke="#fff" stroke-width="7"/>',
        "</g>",
    ]
    cuerpo += cohete
    return "".join(defs), "".join(cuerpo)


# ---------------------------------------------------------------- texto PROXLAUNCH como trazos
_fuente = None


def texto_trazos(texto, x, y_base, alto_mayus, espaciado=0.04):
    """Convierte texto a trazos SVG. Devuelve (path_d, ancho)."""
    global _fuente
    if _fuente is None:
        f = TTFont(FUENTE)
        _fuente = instantiateVariableFont(f, {"wght": 700})
    f = _fuente
    gs = f.getGlyphSet()
    cmap = f.getBestCmap()
    cap = f["OS/2"].sCapHeight
    esc = alto_mayus / cap
    cursor, partes = 0.0, []
    for ch in texto:
        g = cmap[ord(ch)]
        pen = SVGPathPen(gs)
        tp = TransformPen(pen, (esc, 0, 0, -esc, x + cursor, y_base))
        gs[g].draw(tp)
        partes.append(pen.getCommands())
        cursor += gs[g].width * esc + espaciado * alto_mayus * 10 / 10
    return partes, cursor - espaciado * alto_mayus


def palabra(pal, pref, x, y_base, alto):
    c = COLOR[pal]
    p1, a1 = texto_trazos("PROX", x, y_base, alto)
    p2, a2 = texto_trazos("LAUNCH", x + a1 + alto * 0.04, y_base, alto)
    defs = (f'<linearGradient id="{pref}l" gradientUnits="userSpaceOnUse" x1="{x + a1}" y1="0" '
            f'x2="{x + a1 + a2}" y2="0"><stop offset="0" stop-color="{c["launch"][0]}"/>'
            f'<stop offset="1" stop-color="{c["launch"][1]}"/></linearGradient>')
    cuerpo = (f'<path fill="{c["prox"]}" d="{"".join(p1)}"/>'
              f'<path fill="url(#{pref}l)" d="{"".join(p2)}"/>')
    return defs, cuerpo, a1 + alto * 0.04 + a2


# ---------------------------------------------------------------- archivos
def svg(ancho, alto, defs, cuerpo, titulo):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ancho:.0f} {alto:.0f}" '
            f'width="{ancho:.0f}" height="{alto:.0f}" role="img" aria-label="{titulo}">'
            f'<title>{titulo}</title><defs>{defs}</defs>{cuerpo}</svg>\n')


def escribir(nombre, contenido):
    (SALIDA / nombre).write_text(contenido, encoding="utf-8")


# 1) Símbolo solo (fondo transparente), para tema claro y oscuro
for pal in ("claro", "oscuro"):
    d, b = simbolo(pal, "s")
    escribir(f"proxlaunch-simbolo-{pal}.svg", svg(512, 512, d, b, "ProxLaunch"))

# 2) Logotipo completo (símbolo arriba, palabra abajo)
for pal in ("claro", "oscuro"):
    d1, b1 = simbolo(pal, "s")
    alto_letra = 92
    tmp = palabra(pal, "t", 0, 0, alto_letra)
    ancho_txt = tmp[2]
    ancho = ancho_txt + 40
    x_txt = 20
    esc_sim = 1.0
    x_sim = (ancho - 512 * esc_sim) / 2
    d2, b2, _ = palabra(pal, "t", x_txt, 512 + 20 + alto_letra, alto_letra)
    cuerpo = f'<g transform="translate({x_sim:.1f} 0)">{b1}</g>{b2}'
    escribir(f"proxlaunch-logotipo-{pal}.svg",
             svg(ancho, 512 + 20 + alto_letra + 30, d1 + d2, cuerpo, "ProxLaunch"))

# 3) Icono de app (cuadrado redondeado azul marino) con y sin texto
def icono(con_texto):
    d, b = simbolo("icono", "s")
    fondo = ('<linearGradient id="ifondo" x1="0" y1="1" x2="1" y2="0">'
             '<stop offset="0" stop-color="#1E1A5C"/><stop offset="1" stop-color="#1D5E92"/></linearGradient>')
    capa = '<rect x="16" y="16" width="480" height="480" rx="104" fill="url(#ifondo)"/>'
    if con_texto:
        dt, bt, at = palabra("icono", "t", 0, 0, 40)
        x = (512 - at) / 2
        dt, bt, _ = palabra("icono", "t", x, 440, 40)
        sim = f'<g transform="translate(88 40) scale(0.66)">{b}</g>'
        return svg(512, 512, fondo + d + dt, capa + sim + bt, "ProxLaunch")
    sim = f'<g transform="translate(64 60) scale(0.76)">{b}</g>'
    return svg(512, 512, fondo + d, capa + sim, "ProxLaunch")

escribir("proxlaunch-icono.svg", icono(True))
escribir("proxlaunch-icono-sin-texto.svg", icono(False))
print("generados en", SALIDA)
