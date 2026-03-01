# 🌑 Black Hole Screensaver

Simulazione fisica di un buco nero con lensing gravitazionale,
disco di accrescimento con profilo di Novikov-Thorne, effetto
Doppler relativistico e redshift gravitazionale.

---

## Installazione rapida

```bash
chmod +x install.sh
./install.sh
```

---

## Test immediato

```bash
pip install moderngl pygame numpy
python3 blackhole_screensaver.py
```

---

## Parametri fisici

| Parametro | Valori | Effetto |
|---|---|---|
| `--spin` | 0.0 – 0.998 | Spin a* del buco nero (0=Schwarzschild, 0.998≈massimo) |
| `--inclination` | 0.0 – 1.5 | Inclinazione camera in rad (0=di profilo, π/2=dall'alto) |

```bash
# Vista spettacolare di profilo, buco nero lentamente rotante
python3 blackhole_screensaver.py --inclination 0.15 --spin 0.5

# Vista dall'alto, spin massimo (ergosfera visibile)
python3 blackhole_screensaver.py --inclination 1.2 --spin 0.998
```

---

## Fisica implementata

### 1. Metrica di Schwarzschild
Lo spaziotempo è descritto dall'elemento di linea di Schwarzschild
in unità geometrizzate (G = c = M = 1):

    ds² = -(1 - 2/r)dt² + (1 - 2/r)⁻¹dr² + r²dΩ²

Il raggio di Schwarzschild è r_s = 2M = 2 (in unità di M).

### 2. Integrazione geodetiche — Runge-Kutta 4°
Le geodetiche nulle (percorsi dei fotoni) sono integrate numericamente
con RK4 usando l'equazione di Binet relativistica:

    d²u/dφ² = -u + (3/2)·r_s·u²

dove u = 1/r è l'inverso del raggio e φ è l'angolo azimutale.
Il secondo termine è la correzione GR assente nella fisica newtoniana.

### 3. Disco di accrescimento — Profilo Novikov-Thorne
La temperatura segue:

    T(r) ∝ r^(-3/4) · (1 - √(r_ISCO/r))^(1/4)

con r_ISCO = 6M (Innermost Stable Circular Orbit per Schwarzschild).

### 4. Redshift gravitazionale
La temperatura osservata lontano dal buco nero è ridotta:

    T_obs = T_emit · √(1 - r_s/r)

All'orizzonte (r = r_s), il redshift è infinito: nessuna luce sfugge.

### 5. Effetto Doppler relativistico
Il materiale del disco ruota alla velocità kepleriana GR:

    v_K = √(M/r) / √(1 - r_s/r)

Il lato del disco in avvicinamento appare più luminoso e caldo:

    D = 1 / (γ · (1 - β·cos φ))

Il flusso scala come D³.

### 6. Photon Ring
I raggi con parametro d'impatto b ≈ b_c = 3√3·M ≈ 5.196M
sfiorano la fotosfera a r_ph = 3M e vengono deflesssi di grandi angoli,
producendo un anello brillante attorno all'ombra del buco nero.
Questo è l'analogo simulato dell'anello osservato da EHT su M87*.

---

## Requisiti

- Ubuntu 20.04+ con driver OpenGL 3.3+
- Python 3.8+
- GPU qualsiasi (anche integrata Intel con Mesa)
