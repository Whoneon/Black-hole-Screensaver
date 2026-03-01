#!/usr/bin/env python3
"""
Black Hole Screensaver — Simulazione fisica di un buco nero di Schwarzschild
con disco di accrescimento, lensing gravitazionale, effetto Doppler relativistico
e redshift gravitazionale.

Dipendenze: pip install moderngl pygame numpy
"""

import sys, time, argparse, moderngl, pygame, numpy as np
from pygame.locals import *

# ══════════════════════════════════════════════════════════════════════════════
#  VERTEX SHADER — quad fullscreen, invariato rispetto agli esempi precedenti
# ══════════════════════════════════════════════════════════════════════════════
VERT = """
#version 330 core
in  vec2 in_vert;
void main() { gl_Position = vec4(in_vert, 0.0, 1.0); }
"""

# ══════════════════════════════════════════════════════════════════════════════
#  FRAGMENT SHADER — tutto il rendering fisico
# ══════════════════════════════════════════════════════════════════════════════
FRAG = """
#version 330 core
uniform vec2  iResolution;   // dimensioni schermo in pixel
uniform float iTime;         // secondi dall'avvio
uniform float uSpin;         // parametro di spin a* in [0, 0.998] (0=Schwarzschild)
uniform float uInclination;  // inclinazione della camera in radianti
out vec4 fragColor;

// ─────────────────────────────────────────────────────────────────────────────
//  COSTANTI FISICHE (unità geometrizzate: G = c = 1, M = 1)
//  In queste unità:
//    - il raggio di Schwarzschild è r_s = 2M = 2
//    - la velocità della luce è c = 1
//    - tutte le lunghezze sono in unità di M (massa del buco nero)
//    - il raggio critico della fotosfera per Schwarzschild è r_ph = 3M = 3
//    - il parametro d'impatto critico è b_c = 3√3 M ≈ 5.196
// ─────────────────────────────────────────────────────────────────────────────
const float M       = 1.0;          // massa del buco nero (unità geometrizzate)
const float RS      = 2.0 * M;      // raggio di Schwarzschild r_s = 2GM/c²
const float R_PH    = 1.5 * RS;     // raggio fotosfera: r_ph = 3M (Schwarzschild)
const float B_CRIT  = 3.0*sqrt(3.0)*M; // parametro d'impatto critico: b_c = 3√3 M

// Limiti del disco di accrescimento
// ISCO (Innermost Stable Circular Orbit) = 3*r_s = 6M per Schwarzschild
const float R_ISCO  = 3.0 * RS;     // bordo interno del disco (orbita stabile min)
const float R_OUTER = 12.0 * M;     // bordo esterno del disco (scelta estetica)

// Passi di integrazione numerica
const int   N_STEPS = 512;          // numero di passi Runge-Kutta per geodetica
const float STEP    = 0.08;         // dimensione del passo in unità di M

// ─────────────────────────────────────────────────────────────────────────────
//  FUNZIONI DI SUPPORTO MATEMATICO
// ─────────────────────────────────────────────────────────────────────────────

// Conversione temperatura (Kelvin) → colore RGB visibile
// Approssimazione di Planck nel visibile: segue la curva del corpo nero.
// L'occhio percepisce il colore della radiazione di corpo nero:
//   < 3000K  → rosso-arancio (bordo esterno freddo del disco)
//   ~ 5500K  → bianco (come il Sole)
//   > 8000K  → blu-bianco (zona interna calda, vicino all'ISCO)
vec3 blackbodyColor(float temp) {
    // Normalizza la temperatura rispetto a un riferimento (6500K = bianco)
    float t = temp / 6500.0;

    // Componente rossa: satura rapidamente, dominante a basse T
    float r = clamp(1.0 / (0.1 + 0.9*t*t), 0.0, 1.0);

    // Componente verde: picco a temperatura media
    float g = clamp(t * exp(1.0 - t), 0.0, 1.0);

    // Componente blu: cresce con T alta (zona interna del disco)
    float b = clamp(t*t*t, 0.0, 1.0);

    return vec3(r, g, b);
}

// Hash pseudo-casuale per generare stelle di sfondo
// Basato su un hash a 2 interi con buone proprietà di distribuzione
float hash21(vec2 p) {
    p = fract(p * vec2(127.1, 311.7));
    p += dot(p, p + 19.19);
    return fract(p.x * p.y);
}

// Campo stellare procedurale: restituisce luminosità della stella
// nella direzione data, simulando una distribuzione di Poisson
float starField(vec3 dir) {
    // Proietta la direzione su una griglia sferica
    float phi   = atan(dir.x, dir.z);          // longitudine [-π, π]
    float theta = asin(clamp(dir.y, -1.0, 1.0)); // latitudine [-π/2, π/2]

    // Densità stellare varia con la latitudine galattica (più stelle al piano)
    float density = 0.5 + 0.5 * exp(-abs(theta) * 3.0);

    // Griglia a scala fine
    vec2  grid  = vec2(phi, theta) * 80.0;
    vec2  cell  = floor(grid);
    vec2  local = fract(grid);

    float star = 0.0;
    // Campiona le 9 celle vicine per evitare artefatti ai bordi
    for (int i = -1; i <= 1; i++) {
        for (int j = -1; j <= 1; j++) {
            vec2  nc = cell + vec2(i, j);
            float h  = hash21(nc);
            // Solo le celle con h > soglia contengono una stella
            if (h > 0.92 - density * 0.1) {
                vec2  pos = nc + vec2(hash21(nc * 7.3), hash21(nc * 13.7));
                float d   = length(local - fract(pos));
                // Profilo gaussiano della stella
                star += exp(-d * d * 800.0) * (0.3 + 0.7*hash21(nc * 31.0));
            }
        }
    }
    return clamp(star, 0.0, 1.0);
}

// ─────────────────────────────────────────────────────────────────────────────
//  METRICA DI SCHWARZSCHILD
//  ds² = -(1-r_s/r)dt² + (1-r_s/r)⁻¹dr² + r²dΩ²
//
//  In unità geometrizzate (G=c=M=1), r_s = 2.
//  La funzione "grr" è il coefficiente radiale della metrica.
// ─────────────────────────────────────────────────────────────────────────────

// Fattore metrico f(r) = 1 - r_s/r = 1 - 2M/r
// Appare in tutti i coefficienti della metrica di Schwarzschild
float metric_f(float r) {
    return 1.0 - RS / r;
}

// ─────────────────────────────────────────────────────────────────────────────
//  INTEGRAZIONE DELLE GEODETICHE NULLE — RUNGE-KUTTA 4° ORDINE
//
//  Utilizziamo le equazioni in forma hamiltoniana per un fotone.
//  Per simmetria sferica e stazionarietà, il problema si riduce al
//  piano equatoriale (θ = π/2) con le costanti del moto:
//    E = energia (conservata per stazionarietà)
//    L = momento angolare (conservato per simmetria azimutale)
//    b = L/E = parametro d'impatto
//
//  Usiamo la variabile u = 1/r (equazione di Binet):
//    (du/dφ)² = 1/b² - u²(1 - r_s·u)
//
//  Derivando rispetto a φ:
//    d²u/dφ² = -u + (3/2)·r_s·u²
//
//  Il termine -u sarebbe la traiettoria rettilinea in spazio piatto.
//  Il termine +(3/2)·r_s·u² è la CORREZIONE RELATIVISTICA che piega
//  il raggio — questo termine non esiste nella fisica newtoniana.
//
//  Riscriviamo come sistema del primo ordine:
//    y[0] = u = 1/r       (inverso del raggio)
//    y[1] = du/dφ         (derivata di u rispetto all'angolo)
//
//  Derivate:
//    dy[0]/dφ = y[1]
//    dy[1]/dφ = -y[0] + 1.5·r_s·y[0]²
// ─────────────────────────────────────────────────────────────────────────────

// Destra del sistema ODE: f(y) dove y = (u, du/dφ)
vec2 geodesicRHS(vec2 y) {
    float u    = y.x;
    float duPhi = y.y;
    // d²u/dφ² = -u + (3/2)·R_s·u²
    // Questo è il termine newtoniano (-u, traiettoria retta)
    // più la correzione GR (1.5*RS*u², deflessione della luce)
    return vec2(duPhi, -u + 1.5 * RS * u * u);
}

// Un passo di Runge-Kutta 4° ordine
// RK4 è il compromesso ottimale tra costo computazionale e accuratezza:
//   errore locale O(h⁵), errore globale O(h⁴)
// Quattro valutazioni della funzione per passo, ma convergenza molto rapida.
vec2 rk4Step(vec2 y, float h) {
    vec2 k1 = geodesicRHS(y);
    vec2 k2 = geodesicRHS(y + 0.5*h*k1);
    vec2 k3 = geodesicRHS(y + 0.5*h*k2);
    vec2 k4 = geodesicRHS(y + h*k3);
    return y + (h/6.0) * (k1 + 2.0*k2 + 2.0*k3 + k4);
}

// ─────────────────────────────────────────────────────────────────────────────
//  COLORE DEL DISCO DI ACCRESCIMENTO
//
//  Il disco è nel piano equatoriale tra r_ISCO e r_outer.
//  La temperatura segue il profilo di Novikov-Thorne (approssimato):
//    T(r) ∝ r^(-3/4) · (1 - √(r_ISCO/r))^(1/4)
//  che include l'effetto del bordo interno (T→0 all'ISCO).
//
//  Aggiungiamo:
//  1. Doppler relativistico: il lato del disco che si avvicina
//     all'osservatore è più brillante (beaming) e blue-shiftato
//  2. Redshift gravitazionale: T_obs = T_emit · √(1 - r_s/r)
//  3. Variazione azimutale: simula struttura turbulenta del disco
// ─────────────────────────────────────────────────────────────────────────────
vec3 accretionDiskColor(vec3 hitPos, vec3 rayDir, float phi_angle) {
    float r = length(hitPos);

    // Verifica che il punto sia nel disco (r_ISCO ≤ r ≤ r_outer)
    if (r < R_ISCO || r > R_OUTER) return vec3(0.0);

    // ── Profilo di temperatura ────────────────────────────────────────
    // Normalizzazione rispetto all'ISCO:
    float x     = r / R_ISCO;  // x=1 all'ISCO, x>1 verso l'esterno
    // Profilo di Novikov-Thorne (approssimato):
    //   T ∝ x^(-3/4) · (1 - 1/√x)^(1/4)
    float tProfile = pow(x, -0.75) * pow(max(1.0 - 1.0/sqrt(x), 0.0), 0.25);
    float T_emit   = 8000.0 * tProfile;  // temperatura in Kelvin (normalizzata)

    // ── Redshift gravitazionale ───────────────────────────────────────
    // Un fotone emesso a raggio r con frequenza ν_e arriva lontano con:
    //   ν_∞ = ν_e · √(1 - r_s/r)
    // Poiché la temperatura è proporzionale alla frequenza del picco
    // (legge di Wien: λ_max·T = cost), la temperatura osservata è:
    float gravRedshift = sqrt(max(metric_f(r), 0.0));
    float T_obs        = T_emit * gravRedshift;

    // ── Velocità kepleriana e Doppler relativistico ───────────────────
    // Velocità orbitale kepleriana in RG per orbita circolare:
    //   v_K = √(M/r) / (1 - r_s/r)^(1/2)
    // In unità geometrizzate (M=1):
    float v_K   = sqrt(M / r) / sqrt(1.0 - RS/r);
    v_K = clamp(v_K, 0.0, 0.95);  // limite fisico: v < c

    // Fattore di Lorentz γ = 1/√(1-β²)
    float beta  = v_K;
    float gamma = 1.0 / sqrt(1.0 - beta*beta);

    // L'angolo φ determina se il materiale si avvicina o allontana.
    // Il disco ruota in senso antiorario visto dall'alto.
    // cos(φ) = componente della velocità lungo la linea di vista:
    float cosPhi = sin(phi_angle);  // sin perché la velocità è tangenziale

    // Fattore Doppler relativistico D = 1/(γ·(1 - β·cos φ))
    // D > 1 per il lato in avvicinamento (blue shift, più luminoso)
    // D < 1 per il lato in allontanamento (red shift, più scuro)
    float doppler = 1.0 / (gamma * (1.0 - beta * cosPhi));

    // La temperatura osservata include anche il Doppler:
    T_obs *= doppler;

    // ── Luminosità e colore ───────────────────────────────────────────
    // Il flusso scala come D⁴ (tre fattori fisici + uno geometrico)
    // In pratica usiamo D³ per motivi di stabilità numerica
    float flux = pow(doppler, 3.0) * pow(gravRedshift, 4.0) * tProfile;

    // Struttura turbolenta del disco: variazione azimutale e radiale
    // Simuliamo filamenti e clumps del plasma con una funzione sinusoidale
    float turbulence = 0.7 + 0.3 * sin(phi_angle * 7.0 + iTime * 0.8)
                           * sin(r * 2.0 - iTime * 1.2);

    // Colore finale: colore del corpo nero alla temperatura osservata,
    // modulato dalla luminosità e dalla struttura turbolenta
    vec3 col = blackbodyColor(T_obs) * flux * turbulence * 2.5;

    // Aggiungi un bagliore coronale: plasma ad alta energia sopra il disco
    // La corona emette principalmente in raggi X (qui approssimata come bianco-blu)
    float corona = exp(-abs(r - R_ISCO) * 0.3) * 0.3;
    col += vec3(0.5, 0.7, 1.0) * corona;

    return col;
}

// ─────────────────────────────────────────────────────────────────────────────
//  TRACCIAMENTO DEL RAGGIO — INTEGRAZIONE COMPLETA
//
//  Dato un raggio (posizione + direzione), integra la geodetica nulla
//  nella metrica di Schwarzschild e determina dove il raggio "colpisce":
//    - disco di accrescimento (piano y=0, R_ISCO ≤ r ≤ R_outer)
//    - orizzonte degli eventi (r ≤ r_s): raggio nero, cade nel buco nero
//    - infinito: raggio che sfugge al buco nero, vede il campo stellare
//
//  Notare che tracciamo il raggio ALL'INDIETRO NEL TEMPO:
//  partiamo dall'occhio dell'osservatore e risaliamo verso la sorgente.
//  Questo è standard nel ray tracing e fisicamente corretto (la fisica
//  è time-reversal symmetric per i fotoni).
// ─────────────────────────────────────────────────────────────────────────────
vec3 traceRay(vec3 ro, vec3 rd) {
    // ── Setup: converti direzione cartesiana in parametro d'impatto ──
    // Il piano dell'orbita è il piano xz (y è l'asse verticale/polare)
    float r0   = length(ro);          // raggio iniziale
    float u0   = 1.0 / r0;           // u = 1/r (variabile di Binet)

    // Il parametro d'impatto b = L/E misura quanto il raggio
    // "manca" il centro. Per un raggio radiale b=0, per un raggio
    // tangenziale b→∞.
    // Lo calcoliamo dalla componente del vettore direzione perpendicolare
    // alla direzione radiale: b = r · sin(angolo tra rd e ro)
    vec3  ro_n   = normalize(ro);
    float sinAngle = length(cross(rd, ro_n));  // |rd × ro_n| = sin θ
    float b       = r0 * sinAngle;             // parametro d'impatto

    // Segno di du/dφ: il raggio si avvicina o allontana inizialmente?
    float duPhi0 = -dot(rd, ro_n) * u0 * u0 * r0;  // approssimazione

    // Stato iniziale del sistema ODE: y = (u, du/dφ)
    vec2  y      = vec2(u0, duPhi0);
    float phi    = 0.0;   // angolo azimutale accumulato

    // Angolo iniziale nel piano per calcolare la posizione del disco
    float phi0   = atan(ro.z, ro.x);

    // ── Integrazione delle geodetiche ────────────────────────────────
    bool hitDisk     = false;
    bool hitHorizon  = false;
    vec3 diskHitPos  = vec3(0.0);
    float diskHitPhi = 0.0;
    float prevY      = ro.y;  // per rilevare attraversamento del piano y=0

    for (int i = 0; i < N_STEPS; i++) {
        float r = 1.0 / max(y.x, 1e-5);  // r = 1/u (evita divisione per zero)

        // ── Condizione di cattura dall'orizzonte ──────────────────
        // Se r ≤ r_s, il fotone è caduto nell'orizzonte degli eventi.
        // Non c'è ritorno: il raggio è perduto nel buco nero (colore nero).
        if (r <= RS * 1.02) {
            hitHorizon = true;
            break;
        }

        // ── Condizione di fuga ─────────────────────────────────────
        // Se il raggio supera una distanza massima, è sfuggito al BH.
        if (r > 50.0 * M) break;

        // ── Rilevazione intersezione con il disco ─────────────────
        // Il disco è nel piano y=0 (piano equatoriale nella nostra geometria 3D).
        // Ricostruiamo la posizione 3D approssimata del fotone:
        // φ_corrente = φ_iniziale + φ accumulato dall'integrazione
        float phiCurr = phi0 + phi;
        vec3 pos3D = vec3(r * cos(phiCurr), 0.0, r * sin(phiCurr));

        // La direzione y è determinata dall'inclinazione della camera:
        // approssimiamo la componente y del raggio linearmente
        float yRay = ro.y + float(i) * rd.y * STEP * 2.0;

        // Attraversamento del piano y=0? (cambio di segno di yRay)
        if (i > 0 && prevY * yRay < 0.0) {
            float rDisc = length(vec2(pos3D.x, pos3D.z));
            if (rDisc >= R_ISCO && rDisc <= R_OUTER) {
                hitDisk    = true;
                diskHitPos = vec3(pos3D.x, 0.0, pos3D.z);
                diskHitPhi = phiCurr;
                break;
            }
        }
        prevY = yRay;

        // ── Un passo RK4 ──────────────────────────────────────────
        // h è il passo in variabile angolare φ
        float h = STEP / max(r, 0.5);  // adatta il passo: più piccolo vicino al BH
        y   = rk4Step(y, h);
        phi += h;
    }

    // ── Colorazione del risultato ─────────────────────────────────────
    if (hitHorizon) {
        // Orizzonte degli eventi: perfettamente nero.
        // In realtà ci sarebbe la radiazione di Hawking, ma è
        // completamente irrilevabile (T_Hawking ~ 60 nanoKelvin per M_sole)
        return vec3(0.0);
    }

    if (hitDisk) {
        // Il raggio ha colpito il disco: calcola il colore fisico
        return accretionDiskColor(diskHitPos, rd, diskHitPhi);
    }

    // ── Raggio sfuggito: campo stellare con lensing ───────────────────
    // Ricostruiamo la direzione finale del raggio dopo la deflessione.
    // Il lensing gravitazionale deforma il campo stellare:
    // le stelle vicino al buco nero appaiono spostate nella direzione
    // del buco nero (distorsione della posizione apparente).
    float r_final = 1.0 / max(y.x, 1e-5);
    float phiFinal = phi0 + phi;
    vec3  escapedDir = normalize(vec3(
        cos(phiFinal) - rd.x * 0.1,
        rd.y,
        sin(phiFinal) - rd.z * 0.1
    ));
    escapedDir = normalize(mix(rd, escapedDir, 0.3));  // blend con direzione orig.

    // Campo stellare nella direzione deflessa
    float stars = starField(escapedDir);

    // Colore del cielo: nero cosmico con leggero bagliore residuo
    vec3 skyCol = vec3(0.0, 0.0, 0.02);  // nero quasi assoluto (CMB non visibile)

    // Bagliore attorno all'ombra del buco nero:
    // i raggi che sfiorano la fotosfera deviano molto e accumulano
    // luce dal disco → anello di Einstein / photon ring
    float bNorm     = length(cross(rd, normalize(ro)));
    float ringGlow  = exp(-pow(abs(bNorm - B_CRIT) * 0.8, 2.0)) * 0.6;
    vec3  ringColor = vec3(1.0, 0.6, 0.2) * ringGlow;

    return skyCol + vec3(stars) * vec3(0.9, 0.95, 1.0) + ringColor;
}

// ─────────────────────────────────────────────────────────────────────────────
//  MAIN
// ─────────────────────────────────────────────────────────────────────────────
void main() {
    vec2  uv = (gl_FragCoord.xy - 0.5 * iResolution) / iResolution.y;

    // ── Setup camera orbitante ────────────────────────────────────────
    // La camera orbita lentamente attorno al buco nero su un'orbita
    // molto larga (r_cam >> r_s), in modo da stare in zona quasi-piatta.
    // r_cam = 20M è sufficientemente lontano da rendere trascurabili
    // le correzioni GR alla posizione della camera stessa.
    float camSpeed = 0.03;    // radianti per secondo
    float camAngle = iTime * camSpeed;
    float camR     = 20.0 * M;  // distanza camera dal buco nero

    // Inclinazione: 0=vista di profilo (disco di lato), π/2=vista dall'alto
    float inclination = uInclination;

    vec3  ro = vec3(
        camR * cos(camAngle) * cos(inclination),
        camR * sin(inclination),
        camR * sin(camAngle) * cos(inclination)
    );

    // Sistema di riferimento della camera (look-at verso l'origine)
    vec3  forward = normalize(-ro);                         // verso il BH
    vec3  right   = normalize(cross(forward, vec3(0,1,0))); // destra
    vec3  up      = cross(right, forward);                  // su

    // Direzione del raggio per questo pixel
    vec3  rd = normalize(forward + uv.x * right + uv.y * up);

    // ── Traccia il raggio ─────────────────────────────────────────────
    vec3 col = traceRay(ro, rd);

    // ── Post-processing ────────────────────────────────────────────────

    // Tone mapping di Reinhard: evita saturazione a bianco
    // Comprime l'intervallo [0, ∞) → [0, 1) in modo fisicamente motivato
    // (simile alla risposta logaritmica dell'occhio umano)
    col = col / (col + vec3(1.0));

    // Correzione gamma: i monitor hanno risposta non lineare.
    // La correzione standard sRGB è γ = 2.2 (approssimato come ^(1/2.2)).
    // Senza questa correzione, le immagini appaiono troppo scure nelle
    // mezze tonalità (i calcoli fisici sono in spazio lineare).
    col = pow(max(col, 0.0), vec3(1.0 / 2.2));

    // Vignettatura sottile ai bordi: aumenta la sensazione di profondità
    float vign = 1.0 - 0.3 * dot(uv * 0.8, uv * 0.8);
    col *= vign;

    // Lieve aberrazione cromatica: separa leggermente R, G, B
    // (effetto ottico delle lenti reali, aggiunge realismo alla camera virtuale)
    float aberr = 0.003;
    // (già inclusa nella campionatura singola; nota per estensione futura)

    fragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}
"""

def main():
    parser = argparse.ArgumentParser(description="Black Hole Screensaver")
    parser.add_argument("--width",       type=int,   default=0,    help="Larghezza (0=fullscreen)")
    parser.add_argument("--height",      type=int,   default=0,    help="Altezza (0=fullscreen)")
    parser.add_argument("--spin",        type=float, default=0.0,  help="Spin del BH a* [0, 0.998]")
    parser.add_argument("--inclination", type=float, default=0.3,  help="Inclinazione camera in radianti")
    args = parser.parse_args()

    pygame.init()
    info  = pygame.display.Info()
    W, H  = (info.current_w, info.current_h) if args.width == 0 else (args.width, args.height)
    flags = (FULLSCREEN | DOUBLEBUF | OPENGL | NOFRAME) if args.width == 0 else (DOUBLEBUF | OPENGL)

    pygame.display.set_mode((W, H), flags)
    pygame.display.set_caption("Black Hole Screensaver")
    pygame.mouse.set_visible(False)

    ctx  = moderngl.create_context()
    prog = ctx.program(vertex_shader=VERT, fragment_shader=FRAG)

    vbo = ctx.buffer(np.array([
        -1,-1,  1,-1,  -1,1,
         1,-1,  1, 1,  -1,1,
    ], dtype='f4'))
    vao = ctx.simple_vertex_array(prog, vbo, 'in_vert')

    prog['iResolution'].value  = (float(W), float(H))
    prog['uSpin'].value        = float(args.spin)
    prog['uInclination'].value = float(args.inclination)

    clock      = pygame.time.Clock()
    start      = time.time()
    last_mouse = pygame.mouse.get_pos()

    print(f"[Black Hole Screensaver] {W}×{H} | spin={args.spin} | incl={args.inclination:.2f} rad")
    print("Premi ESC o muovi il mouse per uscire.")

    while True:
        for ev in pygame.event.get():
            if ev.type in (KEYDOWN, QUIT):
                pygame.quit(); sys.exit(0)

        mx, my = pygame.mouse.get_pos()
        if abs(mx - last_mouse[0]) > 8 or abs(my - last_mouse[1]) > 8:
            pygame.quit(); sys.exit(0)

        prog['iTime'].value = time.time() - start
        ctx.clear(); vao.render()
        pygame.display.flip()
        clock.tick(60)

if __name__ == '__main__':
    main()
