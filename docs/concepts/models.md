# Mathematical Models

Stochastic Warfare uses 11 mathematical and stochastic models to drive simulation behavior. Each model is grounded in established operations research, signal processing, or military science literature.

---

## 1. Markov Chains

### What It Models

State transitions where the next state depends only on the current state (memoryless property). Used for **weather evolution** and **morale state transitions**.

### Key Formula

$$P(\text{next state}) = \text{transition\_matrix}[\text{current state}]$$

The transition matrix `T` is a row-stochastic matrix where `T[i][j]` gives the probability of transitioning from state `i` to state `j`.

### Weather Example

Weather has 4 states: CLEAR, OVERCAST, RAIN, FOG. Each tick, the weather engine samples from the current row of the transition matrix:

```
         CLEAR  OVERCAST  RAIN   FOG
CLEAR    [0.85   0.10    0.03   0.02]
OVERCAST [0.15   0.70    0.12   0.03]
RAIN     [0.05   0.20    0.70   0.05]
FOG      [0.10   0.15    0.05   0.70]
```

If current weather is CLEAR, there's an 85% chance it stays clear, 10% chance of overcast, etc.

### Morale (Continuous-Time)

Morale uses a **continuous-time Markov chain** with 5 states: CONFIDENT, STEADY, SHAKEN, BROKEN, ROUTED. Transition rates (not probabilities) define how quickly units move between states based on combat stress, casualties, leadership, and cohesion.

### Where Used

- `environment/weather.py` -- weather state evolution
- `morale/state.py` -- unit morale transitions

### Key Parameters

- `transition_matrix` -- state transition probabilities (weather)
- `rate_matrix` -- continuous-time transition rates (morale)
- Morale modifiers: casualty rate, leadership quality, cohesion, suppression

---

## 2. Monte Carlo Methods

### What It Models

Statistical estimation of outcomes through repeated random sampling. Used for **engagement validation** and **campaign outcome distributions**.

### Key Formula

Run `N` independent simulations, collect metric `X` from each:

$$\bar{X} = \frac{1}{N}\sum_{i=1}^{N} X_i, \quad \text{CI}_{95\%} = \bar{X} \pm 1.96 \frac{s}{\sqrt{N}}$$

### Example

To validate the 73 Easting scenario, run 100 iterations with different seeds. Collect the exchange ratio (blue kills / red kills) from each. Compare the mean and 95% confidence interval against the historical outcome (~0.1 loss ratio for blue).

### Where Used

- `validation/monte_carlo.py` -- `MonteCarloHarness` for batch runs
- `validation/campaign_validation.py` -- campaign-level MC validation

### Key Parameters

- `num_iterations` -- number of independent runs (default: 100)
- `base_seed` -- starting seed (each iteration uses `base_seed + i`)
- `max_ticks` -- per-run tick limit

---

## 3. Kalman Filter

### What It Models

Optimal estimation of enemy position and velocity from noisy sensor measurements. Tracks a 4-state vector `[x, y, vx, vy]` (position + velocity in 2D).

### Key Formulas

**Predict step** (between measurements):

$$\hat{x}_{k|k-1} = F \hat{x}_{k-1|k-1}, \quad P_{k|k-1} = F P_{k-1|k-1} F^T + Q$$

**Update step** (when a measurement arrives):

$$K = P_{k|k-1} H^T (H P_{k|k-1} H^T + R)^{-1}$$
$$\hat{x}_{k|k} = \hat{x}_{k|k-1} + K(z_k - H\hat{x}_{k|k-1})$$
$$P_{k|k} = (I - KH) P_{k|k-1}$$

Where:

- `F` -- state transition matrix (constant velocity model)
- `P` -- state covariance (uncertainty)
- `Q` -- process noise covariance
- `H` -- measurement matrix (extracts position from state)
- `R` -- measurement noise covariance (sensor accuracy)
- `K` -- Kalman gain (how much to trust new measurement vs prediction)
- `z` -- measurement vector

### Track Association

New measurements are associated with existing tracks using **Mahalanobis distance** gating:

$$d_M = \sqrt{(\mathbf{z} - H\hat{\mathbf{x}})^T S^{-1} (\mathbf{z} - H\hat{\mathbf{x}})}$$

where `S = H P H^T + R` is the innovation covariance. Measurements with `d_M` below the gating threshold are associated; others start new tracks.

### Where Used

- `detection/estimation.py` -- `KalmanTracker` for all sensor types

### Key Parameters

- `process_noise_std` -- expected target acceleration noise
- `measurement_noise_std` -- sensor measurement accuracy
- `gate_threshold` -- Mahalanobis distance for track association (default: 3.0)
- `max_coasts` -- ticks without measurement before track is dropped

---

## 4. Poisson Process

### What It Models

Random events occurring at a constant average rate. Used for **equipment breakdown** and **maintenance scheduling**.

### Key Formula

Probability of at least one failure in time interval `dt`, given mean time between failures (MTBF):

$$P(\text{fail}) = 1 - e^{-dt / \text{MTBF}}$$

### Example

A tank engine has MTBF = 500 hours. In a 1-hour tick:

$$P(\text{fail}) = 1 - e^{-1/500} = 1 - 0.998 = 0.002$$

So about 0.2% chance of breakdown per hour. Over a 72-hour campaign, the probability of at least one breakdown is:

$$P(\text{any fail}) = 1 - e^{-72/500} = 0.134$$

### Where Used

- `logistics/maintenance.py` -- equipment failure scheduling

### Key Parameters

- `mtbf_hours` -- mean time between failures (per equipment type)
- Modifiers: operating tempo, terrain difficulty, weather severity

---

## 5. M/M/c Queue (Medical Evacuation)

### What It Models

Priority-based service with multiple servers. Used for **medical evacuation** where casualties arrive stochastically and medical facilities have limited capacity.

### Key Concept

- **M/M/c**: Markovian arrivals, Markovian service times, `c` servers
- Casualties are prioritized by severity (T1 urgent > T2 delayed > T3 minimal)
- When the queue exceeds capacity, treatment quality degrades
- Service time is exponentially distributed with mean depending on injury severity

### Queue Dynamics

Arrival rate `lambda` depends on combat intensity. Service rate `mu` depends on facility type and staffing. With `c` treatment slots:

$$\rho = \frac{\lambda}{c \cdot \mu}$$

When utilization `rho > 1`, the queue grows and outcomes degrade.

### Where Used

- `logistics/medical.py` -- medical evacuation and treatment

### Key Parameters

- `capacity` -- number of treatment slots (c)
- `service_rate` -- patients per hour per slot
- Priority classes: T1 (immediate), T2 (delayed), T3 (minimal), T4 (expectant)
- Overwhelm degradation factor when utilization > threshold

---

## 6. SNR-Based Detection (erfc)

### What It Models

Unified probability of detection across all sensor types (visual, thermal, radar, acoustic, sonar). Uses signal-to-noise ratio (SNR) to compute detection probability via the complementary error function.

### Key Formula

$$P_d = 0.5 \times \text{erfc}\left(-\frac{\text{SNR} - \text{threshold}}{\sqrt{2}}\right)$$

SNR is computed from:

$$\text{SNR}_{\text{dB}} = S_{\text{source}} - L_{\text{path}} - N_{\text{noise}} + G_{\text{sensor}}$$

Where:

- `S_source` -- target signature strength (visual, thermal, RCS, acoustic)
- `L_path` -- propagation loss (range, atmosphere, terrain)
- `N_noise` -- ambient noise floor (weather, clutter, electronic)
- `G_sensor` -- sensor gain (aperture, integration time, processing)

### Example

A tank (thermal signature 25 dBW) at 3km, atmospheric loss 15 dB, noise floor 5 dB, sensor gain 10 dB:

$$\text{SNR} = 25 - 15 - 5 + 10 = 15 \text{ dB}$$

With threshold = 12 dB:

$$P_d = 0.5 \times \text{erfc}\left(-\frac{15 - 12}{\sqrt{2}}\right) = 0.5 \times \text{erfc}(-2.12) \approx 0.983$$

### Where Used

- `detection/detection.py` -- unified `DetectionEngine` for all sensor types
- `detection/sonar.py` -- underwater acoustic detection

### Key Parameters

- Signature profiles (per unit, per modality)
- Sensor specifications (sensitivity, range, FOV)
- Environmental conditions (weather, time of day, sea state)
- `detection_threshold_db` -- SNR threshold for detection

---

## 7. Lanchester Attrition Models

### What It Models

Analytical force-on-force attrition for **COA (Course of Action) wargaming**. Provides quick comparative estimates without running full tactical simulation.

### Key Formulas

**Square Law** (aimed fire, modern combat):

$$\frac{dB}{dt} = -\beta \cdot R, \quad \frac{dR}{dt} = -\alpha \cdot B$$

Both sides attrit the opposing force proportional to their own strength.

**Linear Law** (area fire, indirect fire):

$$\frac{dB}{dt} = -\beta \cdot R \cdot B, \quad \frac{dR}{dt} = -\alpha \cdot B \cdot R$$

Attrition proportional to the product of both forces.

### Lanchester Square Law Victory Condition

Blue wins if: $\alpha B_0^2 > \beta R_0^2$

The **force ratio** matters quadratically -- doubling your force is 4x as effective, not 2x.

### Where Used

- `ai/coa.py` -- COA comparative wargaming
- Commander AI uses Lanchester outcomes to rank COA alternatives

### Key Parameters

- `alpha`, `beta` -- per-unit attrition rates (derived from weapon effectiveness)
- `B_0`, `R_0` -- initial force strengths
- Force type multipliers (armor vs infantry vs artillery)

---

## 8. Wayne Hughes Salvo Model

### What It Models

Naval missile exchange between surface combatants. Models the attacker's salvo against the defender's defensive systems to compute "leakers" (missiles that penetrate defenses).

### Key Formula

$$\text{leakers} = \max(0, \alpha \cdot A - \beta \cdot D)$$

Where:

- `alpha` -- offensive missiles per attacking ship
- `A` -- number of attacking ships
- `beta` -- defensive intercepts per defending ship
- `D` -- number of defending ships

Each leaker that hits causes damage proportional to missile lethality. Ships absorb damage up to their staying power.

### Example

4 attacking ships fire 8 missiles each (alpha=8). 3 defending ships intercept 6 missiles each (beta=6):

$$\text{leakers} = \max(0, 8 \times 4 - 6 \times 3) = \max(0, 32 - 18) = 14$$

14 missiles get through defenses.

### Where Used

- `combat/naval_surface.py` -- surface naval engagement resolution

### Key Parameters

- `missiles_per_salvo` -- offensive firepower per ship
- `defensive_capacity` -- intercepts per ship (SAMs + CIWS)
- `missile_pk` -- probability of kill per leaker
- `ship_staying_power` -- damage absorption before mission kill

---

## 9. Boyd OODA Loop

### What It Models

Commander decision-making as a **finite state machine** cycling through four phases: Observe, Orient, Decide, Act. The speed of this cycle relative to the opponent is a key combat multiplier.

### Key Concept

Each phase has a base duration modified by:

$$t_{\text{phase}} = t_{\text{base}} \times f_{\text{echelon}} \times f_{\text{comms}} \times f_{\text{school}} \times X_{\text{lognormal}}$$

Where:

- `t_base` -- base phase duration (seconds)
- `f_echelon` -- echelon multiplier (higher echelons are slower)
- `f_comms` -- communications quality multiplier
- `f_school` -- doctrinal school modifier (e.g., Maneuver school is faster in DECIDE)
- `X_lognormal` -- stochastic friction (log-normal noise)

### Decision Quality

The ORIENT phase produces a **situation assessment** that feeds into DECIDE. Assessment quality depends on:

- Intelligence completeness (fog of war)
- Commander personality traits (risk tolerance, aggression)
- Doctrinal school biases (what the commander considers important)

### Where Used

- `ai/ooda.py` -- `OODAEngine` finite state machine
- `ai/commander.py` -- `CommanderEngine` personality effects
- `ai/schools/` -- 9 doctrinal school implementations

### Key Parameters

- Phase durations per echelon level
- Commander personality traits (risk_tolerance, aggression, adaptability)
- School-specific weight overrides for assessment factors
- Lognormal friction parameters (mu, sigma)

---

## 10. Beer-Lambert Law (DEW)

### What It Models

Atmospheric transmittance for **directed energy weapons** (lasers, high-power microwaves). Determines how much beam power reaches the target after atmospheric absorption and scattering.

### Key Formula

$$\tau = e^{-\alpha \cdot R}$$

Where:

- `tau` -- transmittance (fraction of power reaching target, 0 to 1)
- `alpha` -- atmospheric extinction coefficient (per meter)
- `R` -- range to target (meters)

The extinction coefficient depends on:

- Wavelength
- Weather conditions (humidity, rain, fog, dust)
- Altitude (atmospheric density)

### Laser Damage

Effective power on target:

$$P_{\text{target}} = P_{\text{source}} \times \tau \times \eta_{\text{optics}}$$

Damage occurs when power density exceeds the target's damage threshold for a sufficient dwell time.

### Where Used

- `combat/directed_energy.py` -- `DEWEngine` for laser and HPM weapons

### Key Parameters

- `beam_power_kw` -- source power in kilowatts
- `extinction_coefficient` -- atmospheric attenuation rate
- `dwell_time_s` -- time on target
- `damage_threshold_kw_cm2` -- target material damage threshold
- Weather modifiers (rain increases extinction dramatically)

---

## 11. Calibration Methodology (Dupuy CEV)

### What It Models

Per-scenario calibration of combat effectiveness using **Dupuy's Combat Effectiveness Value (CEV)** concept from *Numbers, Predictions, and War* (1979). CEV captures the aggregate quality advantage of one force over another — encompassing training, morale, leadership, technology, tactical situation, and terrain advantage as a single scalar multiplier.

### Key Concept

Each side in a scenario has a `force_ratio_modifier` in `calibration_overrides`. This is the CEV scalar:

```yaml
calibration_overrides:
  french_force_ratio_modifier: 2.5   # French CEV
  coalition_force_ratio_modifier: 1.0  # Coalition CEV (baseline)
```

The ratio of CEVs (here 2.5:1) determines how effectively each side converts its numerical strength into combat power. A CEV of 2.5 means that side fights as if it had 2.5x its actual numbers.

### Calibration Parameters

The full calibration toolkit includes:

| Parameter | Purpose | Typical Range |
|-----------|---------|---------------|
| `force_ratio_modifier` | Per-side CEV (Dupuy quality scalar) | 0.4 – 3.0 |
| `target_size_modifier_{side}` | Per-side vulnerability (formation density, exposure) | 0.3 – 3.0 |
| `hit_probability_modifier` | Global Pk scaling | 0.5 – 1.8 |
| `destruction_threshold` | Fraction of force lost to trigger force_destroyed | 0.25 – 0.7 |
| `morale_degrade_rate_modifier` | Speed of morale degradation | 0.3 – 3.0 |
| `morale_casualty_weight` | How much casualties affect morale | 0.4 – 0.9 |
| `target_side` | Which side's losses trigger force_destroyed | side name |
| `count_disabled` | Include DISABLED units in loss calculation | true/false |

### Per-Scenario CEV Table

| Scenario | Winner CEV | Loser CEV | Ratio | Source |
|----------|-----------|-----------|-------|--------|
| Austerlitz | 2.5 (French) | 1.0 (Coalition) | 2.5:1 | Chandler, *Campaigns of Napoleon* |
| Trafalgar | 2.5 (British) | 0.6 (French-Spanish) | 4.2:1 | Lambert, *Nelson* |
| Agincourt | 3.0 (English) | 0.4 (French) | 7.5:1 | Barker, *Agincourt*; Keegan, *Face of Battle* |
| Cannae | 3.0 (Carthaginian) | 0.5 (Roman) | 6.0:1 | Goldsworthy, *Cannae* |
| Salamis | 3.0 (Greek) | 0.4 (Persian) | 7.5:1 | Strauss, *Battle of Salamis* |
| Midway | 3.0 (USN) | 0.5 (IJN) | 6.0:1 | Parshall & Tully, *Shattered Sword* |
| Hastings | 1.5 (Norman) | 1.2 (Saxon) | 1.25:1 | Gravett, *Hastings 1066* |

### Note on Circular Calibration

CEV values are calibrated to produce correct historical outcomes — the same outcomes they are derived from. This circularity is acceptable for **historical validation** (confirming the engine can reproduce known results with plausible parameters) but does not constitute **predictive validation**. Predictive validation requires testing against engagements not used for calibration, which is done via the Monte Carlo regression suite with multiple seeds.

### Where Used

- `calibration_overrides` in every scenario YAML
- `simulation/calibration.py` — `CalibrationSchema` pydantic model
- `simulation/battle.py` — applied during engagement resolution

---

## Summary Table

| Model | Module | Purpose | Key Formula |
|-------|--------|---------|-------------|
| Markov Chains | weather, morale | State transitions | P(next) = T[current] |
| Monte Carlo | validation | Statistical outcome estimation | N runs, aggregate stats |
| Kalman Filter | detection | Enemy state tracking | Predict-update with gating |
| Poisson Process | logistics | Equipment breakdown | P(fail) = 1 - exp(-dt/MTBF) |
| M/M/c Queue | logistics | Medical evacuation | Priority queue, overwhelm degradation |
| SNR Detection | detection | Unified sensor Pd | Pd = 0.5 * erfc(-(SNR-thresh)/sqrt(2)) |
| Lanchester | ai/planning | COA wargaming | dF/dt = -b * E (square law) |
| Wayne Hughes | combat | Naval missile exchange | leakers = max(0, aA - bD) |
| Boyd OODA | ai | Commander decision cycle | phase_time * modifiers * lognormal |
| Beer-Lambert | combat | DEW transmittance | tau = exp(-alpha * R) |
| Dupuy CEV | calibration | Per-scenario force quality | force_ratio_modifier per side |
