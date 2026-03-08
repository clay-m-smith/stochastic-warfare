# Stochastic Warfare — Block 5 Brainstorm

## Context

Blocks 1–4 (Phases 0–39) built the complete simulation engine, 5 historical eras, a REST API, a React web application, Docker packaging, and ~7,833 tests. 42 scenarios (27 modern + 15 historical). The engine has 19+ modules across all combat domains.

Block 4 completed the web application and made the product runnable via a single command. Block 5 is the first systematic effort to improve **core combat fidelity** — comparing simulation outputs against historical outcomes and fixing the engine mechanics that produce incorrect results.

---

## Motivation: Systematic Scenario Evaluation

Running all 42 scenarios and comparing outputs to historical outcomes reveals **systemic fidelity gaps** in the engine. These are not bugs but architectural simplifications made during initial development that now produce unrealistic results.

### Scenarios with Wrong Winner (6 of 16 historical)

| Scenario | Era | Historical Winner | Sim Winner | Core Issue |
|----------|-----|-------------------|------------|------------|
| Agincourt | Ancient/Medieval | English (decisive) | French (time_expired) | No mud penalty, archers ineffective vs charging knights |
| Salamis | Ancient/Medieval | Greek (decisive) | Persian (time_expired) | No terrain advantage (narrow strait), numbers dominate |
| Trafalgar | Napoleonic | British (0 sunk) | Franco-Spanish (all British sunk) | No gunnery quality, no tactical maneuver modeling |
| Midway | WW2 | USN (4 IJN carriers sunk) | IJN (all 3 USN carriers sunk) | No intelligence/surprise, numbers dominate |
| Stalingrad | WW2 | Soviet (held city) | German (time_expired) | No urban defensive advantage, reinforcement timing |
| Golan Heights | Modern | Israeli (4.6:1 exchange) | Syrian (blue annihilated) | No hull-down, no defensive quality multiplier |

### Scenarios with Draw Instead of Decisive Result (4 of 16)

| Scenario | Historical Winner | Sim Result | Core Issue |
|----------|-------------------|------------|------------|
| Austerlitz | French (decisive) | Draw (3 total casualties) | 22 engagements in 7200 ticks — forces barely fight |
| Waterloo | British | Draw (3 total casualties) | Same — units don't close within musket range in time |
| Cambrai | British (tanks breakthrough) | Draw (0 German casualties) | Tanks stuck, never reach engagement range |
| Somme July 1 | German held (7:1 casualty ratio) | Draw (mutual annihilation 10/10) | No trench advantage, symmetric damage |

### Correct Direction but Wrong Magnitude (3 of 16)

| Scenario | Issue |
|----------|-------|
| Cannae | Both sides annihilated; should be Carthaginian decisive with Roman encirclement |
| Kursk | Soviet wins by numbers; historically a tactical draw at Prokhorovka |
| Jutland | British losses correct direction but too total (16/16 destroyed) |

### Roughly Acceptable (3 of 16)

| Scenario | Notes |
|----------|-------|
| Hastings | Norman victory, correct direction |
| 73 Easting | Blue wins decisively; exchange ratio correct |
| Falklands Campaign | Aircraft losses reasonable, ships survive |

**Summary**: 10 of 16 historical scenarios produce materially incorrect results (wrong winner or wrong-direction magnitude).

---

## Complete Scenario-by-Scenario Analysis

### Ancient & Medieval Era

#### 1. Agincourt (1415) — **WRONG WINNER**
- **Historical**: Decisive English victory. French ~50% casualties (6,000–10,000 of ~12,000), English ~5% (~400 of ~8,000). Longbows devastated French cavalry in mud.
- **Sim**: French wins on time_expired. English 2/5 active (3 destroyed), French 4/4 active (0 casualties).
- **What happened**: Longbows fired 96 times with 29% hit rate, but damage per arrow = 0.075 (need ~13 hits to kill). French knights took 0 casualties. After arrow expenditure, French closed to melee and destroyed English archers.
- **Root causes**: No mud/terrain penalty on cavalry charge. Arrow damage too low for aggregate representation. No defensive stakes for archers. No fire-on-move penalty (French close while being shot at). CENTROID_COLLAPSE on French side.
- **Fixes needed**: [A] [B] [C] [D] [G]

#### 2. Cannae (216 BC) — **CORRECT DIRECTION, WRONG MAGNITUDE**
- **Historical**: Decisive Carthaginian victory. Roman casualties ~85% (~70,000). Carthaginian ~8% (~6,000). Double envelopment.
- **Sim**: Roman wins on time_expired. Carthaginian 0/4 active, Roman 1/5 active. Both sides devastated.
- **What happened**: Carthaginian horse archers effective at range (48 longbow engagements). Melee engagements then destroyed both sides' infantry. No encirclement mechanic — pure frontal attrition.
- **Root causes**: No flanking/encirclement bonus. No quality differential (veteran Carthaginian vs conscript Roman). No morale cascade when surrounded. Both sides use identical unit types.
- **Fixes needed**: [C] [E] [F] [H]

#### 3. Hastings (1066) — **CORRECT DIRECTION, RATIO SLIGHTLY OFF**
- **Historical**: Norman victory. Saxon ~50% casualties. Norman ~30%.
- **Sim**: Norman victory (force_destroyed). Saxon 0/3 destroyed (100%). Norman 1 destroyed, 1 disabled (25% loss).
- **What happened**: Norman archers softened Saxons from range (20 longbow engagements), then cavalry closed. Saxon huscarls destroyed one at a time. Norman losses too low (25% vs historical 30%).
- **Root causes**: No shield wall defensive bonus. Archers inflict some damage but Saxon posture not considered. CENTROID_COLLAPSE on Norman side.
- **Fixes needed**: [A] [C] [G]

#### 4. Salamis (480 BC) — **WRONG WINNER**
- **Historical**: Decisive Greek victory. Persian ~200 ships destroyed (~30% of fleet), Greek ~40. Narrow strait negated Persian numerical advantage.
- **Sim**: Persian wins on time_expired. Greek 12/60 active (80% lost), Persian 52/60 active (13% lost). **Completely reversed.**
- **What happened**: 259 engagements, Greeks lost the attrition war. Persian numerical superiority (60 vs 60, but Persian ships larger/heavier) dominated in open water combat.
- **Root causes**: No narrow strait force channeling. No terrain-driven tactical advantage. Greek ramming doctrine superiority not modeled. Numbers dominate.
- **Fixes needed**: [C] [E] [H]

### Napoleonic Era

#### 5. Austerlitz (1805) — **DRAW (should be decisive French victory)**
- **Historical**: Decisive French victory. Coalition ~27% casualties. Masterful maneuver at Pratzen Heights.
- **Sim**: Draw on time_expired. French 8/9 active, Coalition 7/9 active. Only 22 engagements total, 4 hits, 3 disabled in 7200 ticks (10 hours).
- **What happened**: Units started 8km apart. Infantry musket range = 200m. Only 6 cavalry saber engagements reached melee range. Artillery (1200–1600m range) never fired (no engagement, possibly detection issue). Forces essentially stood across the field without closing.
- **Root causes**: Forces don't close within engagement range in time. Artillery doesn't engage (detection or targeting issue). No volley fire aggregate model. No hold-fire discipline (would need to close to 100m for effective musketry). Cavalry fights alone.
- **Fixes needed**: [B] [D] [G]

#### 6. Trafalgar (1805) — **WRONG WINNER**
- **Historical**: Decisive British victory. 22 Franco-Spanish ships captured/sunk. 0 British ships sunk. British gunnery superiority (3:1 broadside rate).
- **Sim**: Franco-Spanish wins. All 23 British ships destroyed. Only 12 of 30 Franco-Spanish ships destroyed. **Completely reversed.**
- **What happened**: 2698 engagements, massive naval gunfight. British ships destroyed first because Franco-Spanish had more guns firing (30 vs 23 ships). No modeling of: British breaking the line, superior gunnery rate, better crew quality, Nelson's tactics.
- **Root causes**: Pure numerical advantage (30 vs 23). No crew quality/training multiplier. No tactical maneuver (breaking the line). No gunnery rate advantage. No morale cascade after flagship loss.
- **Fixes needed**: [E] [F] [H]

#### 7. Waterloo (1815) — **DRAW (should be British victory)**
- **Historical**: Decisive British victory after Prussian reinforcement. French ~40% casualties. Multiple French cavalry charges repulsed by infantry squares.
- **Sim**: Draw on time_expired. French 9/10 active, British 7/9 active. Only 19 engagements, 3 hits in 5760 ticks. 2 British destroyed, 1 French disabled.
- **What happened**: Same as Austerlitz — forces too far apart (4km), musket range 200m. Cavalry made 6 saber engagements. Infantry barely engaged. Artillery never fired. No infantry square vs cavalry dynamic.
- **Root causes**: Same as Austerlitz. Additionally, no formation system active in battle loop (squares vs charges). No Prussian reinforcement mechanic.
- **Fixes needed**: [B] [D] [G]

### World War I Era

#### 8. Somme July 1 (1916) — **WRONG CASUALTY RATIO**
- **Historical**: 7:1 British casualties (57,000 British vs 8,000 German). German first line held across most of front. British infantry slaughtered by MG positions.
- **Sim**: Draw on time_expired. All 10 units destroyed (5 British, 5 German). Mutual annihilation. 100% casualties on both sides.
- **What happened**: 19 engagements, 10 hits. British and German infantry exchanged rifle fire symmetrically. All units destroyed within 399 ticks. German MG positions had no defensive advantage.
- **Root causes**: No trench defensive posture. No MG emplacement advantage. No attacking-into-prepared-defenses penalty. Symmetric damage model. No suppression effect on advancing troops.
- **Fixes needed**: [A] [C] [E] [F]

#### 9. Cambrai (1917) — **DRAW (should be British tactical victory)**
- **Historical**: Deepest advance on Western Front in 3 years (~8km). First massed tank assault. Tank mechanical loss ~30%.
- **Sim**: Draw on time_expired. British 4/7 active (3 infantry destroyed), German 0/3 active (all casualties from infantry rifles). 4 of 10 units stuck. Tanks never engaged.
- **What happened**: 27 engagements, all Lee-Enfield rifles. British infantry closed and were destroyed. Mark IV tanks had no ranged weapons that connected (possibly detection/range issues). German sturmtruppen killed British infantry with rifles.
- **Root causes**: Tanks stuck (movement pathfinding issue). Tanks have no way to engage at range (their weapon definitions may be incomplete). Infantry-only fight produces symmetric results.
- **Fixes needed**: [A] [C] (+ tank weapon/data review)

#### 10. Jutland (1916) — **CORRECT DIRECTION, TOO EXTREME**
- **Historical**: Tactical German victory. British lost 14 ships (3 battlecruisers, 3 armoured cruisers, 8 destroyers). German lost 11 ships (1 battlecruiser, 1 pre-dreadnought, 4 light cruisers, 5 torpedo boats). British casualties: 6,094 killed.
- **Sim**: German victory (force_destroyed). All 16 British ships destroyed (100%). German lost 9 ships (5 Königs + 4 destroyers), 4 surviving (2 destroyers, 2 U-boats). 20 total casualties.
- **What happened**: 661 engagements. British capital ships all destroyed. German battleships also all destroyed but destroyers/U-boats survived. British losses too total (100% vs historical ~25%).
- **Root causes**: All British capital ships destroyed — no survivable damage model for battleships. Hit = destroy for capital ships is too lethal. No armor protection model reducing damage. No British gunnery advantage.
- **Fixes needed**: [E] [F] (+ naval damage model review)

### World War II Era

#### 11. Kursk/Prokhorovka (1943) — **CORRECT DIRECTION, DEBATABLE VICTOR**
- **Historical**: Roughly a tactical draw at Prokhorovka. Soviet lost ~300 tanks, German ~80. German tactical victory but strategic Soviet success.
- **Sim**: German wins on time_expired. Soviet 0/80 active (all destroyed), German 15/65 active (5 destroyed, 45 disabled). 897 engagements, 334 hits.
- **What happened**: Massive engagement (largest engagement count of any scenario). Soviet T-34s destroyed German Panthers/Panzer IVs but Soviet numbers ran out. German armor proved more survivable (disabled vs destroyed). Exchange ratio: ~80 Soviet destroyed vs 50 German lost (5 destroyed + 45 disabled). Roughly 1.6:1.
- **Root causes**: Exchange ratio not as extreme as historical (should be ~3.75:1). German tactical advantage not sufficient. Tiger I should be more lethal/survivable. Disabled vs destroyed distinction helps realism here.
- **Fixes needed**: [E] (slight quality differential)

#### 12. Midway (1942) — **WRONG WINNER**
- **Historical**: Decisive USN victory. All 4 IJN carriers sunk. 1 USN carrier sunk (Yorktown). US codebreaking enabled ambush.
- **Sim**: IJN wins on time_expired. All 3 USN carriers destroyed, all 4 USN destroyers disabled. IJN: 0 carriers lost, 6 Zeros destroyed, 1 destroyer destroyed. **Completely reversed.**
- **What happened**: IJN Zeros destroyed by USN air defense immediately (6 destroyed in first 5 ticks). But IJN carriers then attacked USN carriers — 3 destroyed by tick 52. IJN carriers completely intact.
- **Root causes**: No surprise/intelligence advantage for USN. No carrier vulnerability when aircraft on deck (historical key factor). No strike package mechanic (USN dive bombers catching IJN rearming). Numbers + initiative advantage to IJN. No carrier air wing offensive capability difference.
- **Fixes needed**: [E] [H] (+ carrier warfare model, intelligence/surprise mechanic)

#### 13. Normandy Bocage (1944) — **WRONG CASUALTY RATIO**
- **Historical**: 2:1 attacker:defender casualty ratio. Hedgerows provided ~2x defensive advantage. Slow grinding advance.
- **Sim**: German wins on time_expired. All 12 US rifle squads destroyed, all 8 German rifle squads destroyed, 2 German Panzer IV active. 10 total casualties. Only 8 ticks!
- **What happened**: 135 engagements in 8 ticks — extremely lethal mutual annihilation. All infantry destroyed nearly simultaneously. Only German tanks survived. Battle ended in seconds, not hours.
- **Root causes**: No hedgerow defensive cover. No urban/terrain combat modifier. Infantry vs infantry too lethal at close range. No defensive posture for German defenders. Battle resolves too fast.
- **Fixes needed**: [A] [C] [D] [E]

#### 14. Stalingrad (1942) — **WRONG WINNER**
- **Historical**: Soviet victory (held the city). Both sides ~60-80% casualties. Soviet reinforcements critical. 7-day campaign duration.
- **Sim**: German wins on time_expired. Soviet 0/12 active (all destroyed), German 7/10 active (70%). German Tiger I dominant.
- **What happened**: 75 engagements. German 88mm KwK36 (Tiger I gun) accounted for 36 engagements. Soviet forces destroyed by superior German firepower. No urban defensive advantage. Soviet reinforcements (scheduled at 48h and 96h) may not have arrived.
- **Root causes**: No urban terrain defensive advantage. Tiger I too dominant without counter. Soviet defensive posture not modeled. Reinforcement timing may not work. No building-to-building fighting model.
- **Fixes needed**: [A] [C] [E] [F]

### Modern Era — Historical Engagements

#### 15. 73 Easting (1991) — **CORRECT DIRECTION, VICTORY BUG**
- **Historical**: 28:1 exchange ratio. Blue (Eagle Troop) decisively defeated red (Tawakalna Division). ~23 minutes.
- **Sim**: "Draw" on time_expired despite blue 21/21 (100%) active and red 0/50 (0%). All 50 red destroyed, 0 blue losses. 305 engagements. **Exchange ratio is correct (infinite).**
- **What happened**: M1A1s and Bradleys systematically destroyed all T-72s and BMPs. Blue used M256 120mm (234 rounds) and TOW (47 rounds). No blue casualties. 50 red units "stuck" (never moved, probably due to standoff calculation).
- **Root causes**: **BUG in `evaluate_force_advantage()`** — `is_tie` starts True and is never set to False when winning side iterates first in dict. Blue has 100%, red has 0%, but declared "Draw". Also 50/71 red units stuck (standoff/pathfinding issue).
- **Fixes needed**: [F] (is_tie bug), pathfinding review

#### 16. Bekaa Valley (1982) — **CORRECT DIRECTION, LABELED DRAW**
- **Historical**: Israeli SEAD destroyed 17 of 19 SA-6 batteries. 0 Israeli aircraft lost. SAM suppression rate 89%.
- **Sim**: "Draw" on time_expired. Blue 40/46 active (87%), red 0/19 (all destroyed). Blue lost 6 F-16s. All 19 red SAM batteries destroyed.
- **What happened**: 426 engagements (mostly M61A1 Vulcan). All red SAMs destroyed. Blue F-16s engaged by red Patriot missiles (57 engagements) — 6 destroyed. EW scenario but engagements are kinetic.
- **Root causes**: Same `is_tie` bug — blue has 87% vs red 0%, labeled "Draw". Blue air losses too high (should be 0 historical). Vulcan cannon is wrong weapon for SEAD (should be HARM/standoff). No SEAD mission profile. **Red Patriot SAMs shoot at F-16s — historically these were SA-6 Gainful, not friendly Patriot systems (unit type mismatch in scenario data).**
- **Fixes needed**: [F] [H] (+ scenario data fix: red should use SA-6, not Patriot)

#### 17. Falklands Campaign (1982) — **PARTIALLY CORRECT**
- **Historical**: 2 British ships sunk (Ardent, Antelope), ~10 Argentine aircraft destroyed. 5-day campaign.
- **Sim**: "Draw". Blue 13/16 active (3 Sea Harriers destroyed, 0 ships lost), red 0/8 (all aircraft destroyed). Blue ships untouched.
- **What happened**: All 8 Argentine Super Étendards destroyed. 3 British Sea Harriers lost in air combat. No ship kills — Argentine aircraft destroyed before launching Exocets.
- **Root causes**: Argentine aircraft too fragile / destroyed too quickly (before attacking ships). No standoff missile launch before intercept. `is_tie` bug labels this "Draw" despite clear blue advantage.
- **Fixes needed**: [F] [D] (+ missile standoff attack modeling)

#### 18. Falklands Goose Green (1982) — **CORRECT DIRECTION, LABELED DRAW**
- **Historical**: British (2 Para) victory. Blue: 18 killed, 35 wounded. Red: 47 killed, 145 prisoner. 14-hour battle.
- **Sim**: "Draw". Blue 4/6 active (2 destroyed), red 0/8 (all destroyed). M240 used for all 145 engagements.
- **What happened**: Both sides advanced. Blue smaller force destroyed all 8 red defenders but lost 2 units. Casualty ratio ~3:1 in favor of blue (close to historical).
- **Root causes**: `is_tie` bug (blue 67% vs red 0% = "Draw"). No Argentine surrender mechanic (prisoners). All same unit type (us_rifle_squad proxy). Duration compressed (204 ticks vs 14 hours).
- **Fixes needed**: [F] [E]

#### 19. Falklands Naval — Sheffield (1982) — **CORRECT DIRECTION, LABELED DRAW**
- **Historical**: HMS Sheffield sunk by Exocet. 1 of 2 missiles hit (50%).
- **Sim**: "Draw". Blue 7/8 active (1 Sea Harrier destroyed), red 0/2 (both Super Étendards destroyed). No ships hit. Exocet used 4 times, Sea Dart 2 times, Sidewinder 4 times.
- **What happened**: Sea Harriers intercepted Super Étendards before Exocets reached ships. Both attackers destroyed. 1 Sea Harrier lost. No ship damage.
- **Root causes**: `is_tie` bug. No standoff missile launch sequence (Exocets should fire at ~40km before intercept). Air intercept too effective vs sea-skimming missiles.
- **Fixes needed**: [F] [D]

#### 20. Falklands San Carlos (1982) — **CORRECT DIRECTION, LABELED DRAW**
- **Historical**: HMS Ardent sunk, Argonaut & Brilliant damaged. 5 Argentine aircraft destroyed. 12 hours of air raids.
- **Sim**: "Draw". Blue 11/12 active (1 Sea Harrier destroyed), red 0/8 (all aircraft destroyed). No ships hit. 73 engagements.
- **What happened**: Blue air defense destroyed all 8 red aircraft almost immediately (most in tick 0). No Exocets hit ships. M61A1 Vulcan (40 rounds), Sea Dart (15), Sidewinder (11), Exocet (7).
- **Root causes**: `is_tie` bug. Same air intercept issue — aircraft destroyed before reaching attack profile. **Red uses MiG-29A and Super Étendard together — MiG-29 is incorrect for Falklands (should be A-4 Skyhawk).**
- **Fixes needed**: [F] [D] (+ scenario data fix)

#### 21. Golan Campaign (1973) — **WRONG WINNER**
- **Historical**: Israeli victory over 4 days. ~1,100 Syrian tanks destroyed, ~250 Israeli.
- **Sim**: Red wins on time_expired. Blue 0/40 active (all destroyed), red 210/260 active (81%). 492 engagements.
- **What happened**: Blue Shot Kals engaged red forces (206 L7 105mm rounds), but were overwhelmed by volume. Red AT-3 Sagger ATGMs (160 rounds) and BMP-1 autocannons destroyed Israeli tanks. Israeli tanks lost before inflicting sufficient casualties.
- **Root causes**: No hull-down defensive advantage. No Golan escarpment elevation advantage. No Israeli gunnery superiority. 40 vs 260 = pure numerical annihilation. BMP-1 Sagger ATGMs too effective vs tanks. Reinforcements at 36h/72h may arrive but too late.
- **Fixes needed**: [A] [C] [E] [F]

#### 22. Golan Heights — Valley of Tears (1973) — **WRONG WINNER**
- **Historical**: Israeli victory on Day 2. ~100 Syrian tanks destroyed, ~15 Israeli. Israeli 7th Armored Brigade held.
- **Sim**: Red wins on time_expired. Blue 0/40 active, red 14/250 active (6%). 700 engagements, 299 hits. 276 total casualties. All blue destroyed.
- **What happened**: Massive engagement. Blue destroyed many red units (236 destroyed/disabled) but was itself annihilated. Exchange ratio ~6:1 in favor of blue (close to historical!) but not enough — 40 tanks can't kill 250 fast enough.
- **Root causes**: Same as Golan Campaign but magnified. Blue exchange rate is actually realistic (~6:1) but starting 40 vs 250 means blue runs out of tanks. Historically, hull-down positions and reinforcements prevented this. Reinforcements not modeled for this single-day battle.
- **Fixes needed**: [A] [C] [E]

#### 23. Gulf War EW Night One (1991) — **CORRECT DIRECTION, LABELED DRAW**
- **Historical**: IADS suppression rate ~75% in first 6 hours. Coalition lost 1 aircraft (F/A-18).
- **Sim**: "Draw". Blue 71/80 active (89%), red 0/24 (all destroyed). Blue lost 9 F-16s. 814 engagements.
- **What happened**: All 24 red SAM batteries destroyed. Blue lost 9 F-16s to Patriot SAMs. M61A1 Vulcan was primary weapon (760 rounds) — incorrect for EW/SEAD mission.
- **Root causes**: `is_tie` bug. Blue air losses too high (9 vs historical 1). Wrong weapon being used (Vulcan cannon vs HARM standoff). **Same red Patriot mislabel as Bekaa Valley.** No EW suppression effect.
- **Fixes needed**: [F] [H] (+ scenario data fix)

### Modern Era — Contemporary Scenarios

#### 24. Korean Peninsula — **PLAUSIBLE BUT BLUE UNDERPERFORMS**
- **Historical expectation**: ROK/US qualitative advantage vs DPRK quantity. Blue should hold with fewer losses.
- **Sim**: Red wins on max_ticks. Blue 2/16 active (12%), red 4/22 active (18%). All 4 blue F-16s destroyed early. Blue Patriots destroyed. 717 engagements.
- **What happened**: Blue air assets destroyed in first 10 ticks by ground fire (T-72 125mm shooting at F-16s — weapon-target mismatch). Blue ground forces then outnumbered. Bradleys and M1A2s fought T-72s and T-90As.
- **Root causes**: T-72s engaging F-16s with tank guns. No domain-appropriate target selection. Blue air superiority negated by inappropriate ground-to-air engagement. No combined arms synergy.
- **Fixes needed**: [H] [E]

#### 25. Suwalki Gap — **RED WINS (should be contested)**
- **Historical expectation**: NATO defense with EW/air superiority should contest Russian advance. RAND studies suggest blue holds with casualties.
- **Sim**: Red wins on time_expired. Blue 0/17 active (all destroyed), red 14/21 active (67%). 557 engagements.
- **What happened**: Blue F-16s destroyed in first 10 ticks. Blue Leopard 2A6s and Challengers destroyed rapidly. Red T-90As and BMP-2s dominant. No EW effect on engagement despite EW config enabled.
- **Root causes**: Blue air assets destroyed inappropriately (ground units targeting aircraft). No NATO combined arms advantage. No defensive positions. EW config present but effects don't influence engagement outcomes measurably. No doctrinal school effect on combat.
- **Fixes needed**: [A] [E] [H]

#### 26. Taiwan Strait — **PLAUSIBLE, LABELED DRAW**
- **Historical expectation**: US/Taiwan naval/air superiority should contest PLA amphibious assault. Contested result.
- **Sim**: "Draw". Blue 8/16 active (50%), red 0/16 (all destroyed). Blue DDG-51s, SSN, M1A2s survived. Blue lost all F-16s and some Patriot systems. All red destroyed.
- **What happened**: 135 engagements. Blue destroyed all red forces. Blue F-16s and Patriot absorbed red fire. Blue naval assets and tanks untouched. Actual result: blue victory, mislabeled "Draw".
- **Root causes**: `is_tie` bug. F-16s destroyed early again (domain mismatch). Result actually reasonable for scenario design.
- **Fixes needed**: [F] [H]

### Unconventional / Escalation Scenarios

#### 27. COIN Campaign — **PLAUSIBLE, LABELED DRAW**
- **Sim**: "Draw". Blue 6/6 active (100%), red 0/6 (all destroyed). Only 12 TOW engagements. Bradleys destroyed all insurgent squads sequentially (1 per 6 ticks).
- **Root causes**: `is_tie` bug. TOW ATGM against rifle squads = weapon-target mismatch (overkill). No asymmetric warfare mechanics (IED, ambush, guerrilla). Very sterile result.
- **Fixes needed**: [F] [H] (+ unconventional warfare engagement model)

#### 28. Hybrid Gray Zone — **PLAUSIBLE, LABELED DRAW**
- **Sim**: "Draw". Blue 7/8 active (88%), red 0/3 (all destroyed). 56 M240 engagements. 1 SF ODA destroyed.
- **Root causes**: `is_tie` bug. Gray zone operations should involve non-kinetic effects but only kinetic combat modeled. Escalation engine not visible in results.
- **Fixes needed**: [F]

#### 29. Halabja (1988) — **WRONG MECHANIC**
- **Historical**: Chemical attack on Kurdish civilians. ~5,000 killed. No conventional combat.
- **Sim**: Red wins. Blue 0/3 destroyed by TOW ATGMs in 3 ticks. Chemical weapon not used — pure kinetic kill.
- **Root causes**: CBRN scenario doesn't exercise CBRN engine. Modeled as conventional military engagement, not chemical attack. Blue "Kurdish civilians" are US rifle squads with weapons.
- **Fixes needed**: (Scenario redesign needed — not a combat realism fix)

#### 30. Srebrenica (1995) — **PLAUSIBLE DIRECTION**
- **Sim**: Red wins. Blue 0/2 destroyed by TOW ATGMs. Red 11/11 active. Result matches historical (Serb forces overwhelmed defenders).
- **Root causes**: No UN protection mechanic. No escalation consequences. Modeled as simple force mismatch.
- **Fixes needed**: [F] (escalation effects on outcome)

### CBRN Validation Scenarios

#### 31. Chemical Defense — **WRONG MECHANIC**
- **Expected**: Chemical exposure should be primary damage mechanism. MOPP effectiveness comparison.
- **Sim**: Red wins. Blue 0/4 destroyed by 155mm artillery (M284). Chemical agent not exercised. Pure kinetic kill.
- **Root causes**: CBRN engine may not be wired into battle loop for this scenario. Artillery kills faster than chemical dispersion effects.
- **Fixes needed**: (CBRN wiring review)

#### 32. Nuclear Tactical — **WRONG MECHANIC**
- **Expected**: Nuclear detonation should cause mass casualties. Blue ~80% casualties from 10kT blast.
- **Sim**: "Draw". Blue 10/10 active (100%), red 0/2 destroyed. Blue M1A2s destroyed both red tanks with 120mm. Nuclear effects not visible.
- **Root causes**: Nuclear detonation either not triggered or effects not applied. Pure kinetic tank engagement. Blue takes 0 casualties vs expected 80%.
- **Fixes needed**: (CBRN/nuclear wiring review)

### Space Scenarios

#### 33. ASAT Escalation — **PLAUSIBLE**
- **Sim**: "Draw". Blue 4/8 active (4 F-16s destroyed, 4 M1A2s survive), red 0/8 (all T-72s destroyed). All F-16s destroyed by T-72 125mm guns in first 6 ticks.
- **Root causes**: `is_tie` bug. T-72s shooting F-16s with tank guns. ASAT effects not visible in outcome. Space mechanics may run but don't influence tactical combat.
- **Fixes needed**: [F] [H]

#### 34. GPS Denial — **PLAUSIBLE CONCEPT, DOMAIN MISMATCH**
- **Sim**: Red wins. Blue 0/4 (all F-16s destroyed), red 8/8 active. T-72 125mm destroyed all F-16s in first 6 ticks. GPS effects not visible.
- **Root causes**: Same T-72 vs F-16 domain mismatch. GPS degradation may run but doesn't change outcome because ground units kill aircraft before GPS-guided weapons matter.
- **Fixes needed**: [H]

#### 35. ISR Gap — **CORRECT CONCEPT**
- **Sim**: "Draw". Blue 4/4 active (M1A2s), red 0/8 destroyed (T-72s). M1A2s destroyed all T-72s with 120mm.
- **Root causes**: `is_tie` bug (blue 100%, red 0% = "Draw"). ISR gap concept works but outcome is mislabeled.
- **Fixes needed**: [F]

### Test/Validation Scenarios

#### 36. Test Scenario (Desert Storm) — **MISLABELED DRAW**
- **Sim**: "Draw". Blue 10/10 active (100%), red 0/8 (all destroyed). M1A2s and Bradleys destroyed all T-72s.
- **Root causes**: `is_tie` bug. Result should be blue victory.
- **Fixes needed**: [F]

#### 37–40. Test Campaigns — **FUNCTIONAL**
- Campaign scenarios produce varied results. Some blue wins, some red wins depending on numbers. Reinforcements arrive and shift balance. Basic mechanics work but `is_tie` bug affects some.
- **Fixes needed**: [F]

---

## Cross-Cutting Patterns Discovered

### Pattern 1: `evaluate_force_advantage()` is_tie Bug — **Affects 15+ scenarios**

The `is_tie` variable in `victory.py:600` starts as `True` and is only set to `False` when a second side overtakes the first. But when the winning side is iterated first (dict order), `is_tie` stays `True` because `best_survival` is `-1.0` (< 0) on the first comparison. This means **the function returns "Draw" whenever the winning side happens to be iterated first in the dict**, regardless of the survival ratio.

**Affected scenarios**: 73 Easting (21/21 vs 0/50 = "Draw"), Bekaa Valley (40/46 vs 0/19 = "Draw"), all Falklands variants, Gulf War EW, Taiwan Strait, COIN, Space ISR Gap, Space ASAT, Test Scenario, and more.

**Fix**: Simple — track the number of sides sharing the best survival rate, or initialize `is_tie = False`.

### Pattern 2: Tank Guns Engaging Fighter Aircraft — **Affects 8+ scenarios**

T-72 125mm guns (2a46m_125mm) and M256 120mm guns engage F-16s and other aircraft. Target selection is "closest enemy" with no domain filtering. This causes:
- Air assets destroyed in the first few ticks before performing their mission
- Ground units "wasting" tank rounds on aircraft (unrealistic Pk)
- Air superiority negated by inappropriate engagement

**Affected scenarios**: Korean Peninsula, Suwalki Gap, Space ASAT, Space GPS Denial, all scenarios mixing air and ground units.

### Pattern 3: All Infantry Is Identical — **Affects 10+ scenarios**

Many scenarios use `us_rifle_squad` as a proxy for all infantry (Kurdish civilians, Argentine garrison, PMC, insurgents). This means:
- Identical weapon loadout (M240, TOW)
- Identical training, morale, speed
- No asymmetry between professional soldiers and militia/insurgents
- TOW ATGMs used against unarmored infantry (overkill)

### Pattern 4: CBRN/EW/Space Effects Don't Influence Combat Outcomes

The CBRN chemical scenario kills with artillery, not chemicals. The nuclear scenario sees no nuclear effects. EW scenarios show no measurable EW impact on engagement. Space scenarios have GPS/ASAT running but tactical outcomes unchanged. These specialized engines may be running but their effects don't meaningfully alter the combat resolution in `_execute_engagements()`.

### Pattern 5: Napoleonic/Ancient Battles Have Near-Zero Engagement Rates

Austerlitz: 22 engagements in 7200 ticks. Waterloo: 19 in 5760 ticks. These armies should be exchanging thousands of musket volleys and cannonballs. The per-unit, per-tick engagement model produces far too few interactions for pre-modern massed warfare.

---

## Root Cause Analysis: 10 Systemic Issues

### Issue 0: Victory Evaluation Bug (`is_tie` in `evaluate_force_advantage`)

**This is a bug, not a design issue.** The `is_tie` variable in `victory.py:600–627` uses flawed initialization logic:

```python
is_tie = True  # Starts True
for side, units in units_by_side.items():
    if survival > best_survival:
        if best_survival >= 0:    # Only set False when overtaking a non-negative value
            is_tie = False
        best_survival = survival
        best_side = side
    elif survival == best_survival:
        is_tie = True
```

When the winning side iterates first, `best_survival` is `-1.0` on the first comparison, so `is_tie` is never set to `False`. The function returns "Draw" for scenarios like 73 Easting (blue 100%, red 0%). This affects **15+ scenarios** and masks correct outcomes.

**Fix**: Track sides sharing best survival, or initialize correctly:
```python
sides_at_best = 0
for side, units in units_by_side.items():
    if survival > best_survival:
        best_survival = survival
        best_side = side
        sides_at_best = 1
    elif survival == best_survival:
        sides_at_best += 1
is_tie = sides_at_best != 1
```

### Issue 1: Posture Exists but Is Never Wired

**The mechanics are already built** — they're just disconnected:

- `GroundUnit.posture` attribute: `MOVING / HALTED / DEFENSIVE / DUG_IN / FORTIFIED` (`entities/unit_classes/ground.py`)
- `hit_probability.py`: posture modifier table reduces hit probability 15–60%:
  - `DEFENSIVE: 0.85`, `DUG_IN: 0.60`, `FORTIFIED: 0.40`
- `damage.py`: posture blast/frag protection (DUG_IN = 70–95% reduction)
- **But**: `_execute_engagements()` in `battle.py` never passes `target_posture` — it defaults to `"MOVING"` for every unit in every engagement

This single disconnect means dug-in defenders get zero protection benefit. It explains why trenches at the Somme, hull-down positions at Golan, and hedgerows at Normandy provide no advantage.

### Issue 2: Fire-on-Move Penalty Is Half-Built

- `hit_probability.py` computes: `shoot_pen = max(0.3, 1.0 - 0.25 × (shooter_speed_mps / 10.0))`
  - 10 m/s → 25% penalty, 20 m/s → 50%, 40 m/s → 70% (capped)
- **But**: `shooter_speed_mps` is passed as 0.0 or not at all from the battle loop
- Units that moved this tick should have their current speed used as `shooter_speed_mps`
- Historical: Tanks must halt for aimed fire (pre-stabilized turrets). Archers cannot fire at gallop. Musketeers fire in standing/kneeling volley. Even modern MBTs with stabilization have ~30% penalty on the move.

### Issue 3: Terrain Affects Speed but Not Combat (Rich Data, Zero Wiring)

`movement/engine.py` computes terrain-modified speed:
```
speed = base × terrain_factor × slope_factor × road_factor × weather_factor × night_factor
```

But **none of these factors feed into engagement resolution**. The terrain system has **extensive per-position queryable data** that goes completely unused by combat:

| Existing Module | Available Data | Used For Today |
|----------------|---------------|---------------|
| `terrain/classification.py` | `cover` (0.0–0.8), `concealment` (0.0–0.9), `trafficability` (0.2–1.0) per 15 `LandCoverType` | Movement speed only |
| `terrain/obstacles.py` | 10 obstacle types via STRtree spatial queries, FORTIFICATION/WIRE/MINEFIELD | Movement blocking only |
| `terrain/trenches.py` | 4 trench types with `cover_value` (0.50–0.85), `movement_factor` | WW1 era unit tests only |
| `terrain/infrastructure.py` | Building `cover_value` (0–1), polygon footprint, height | LOS obstruction only |
| `terrain/heightmap.py` | Elevation, slope, aspect per cell | LOS calculation only |
| `environment/conditions.py` | `GroundState` (DRY/WET/SATURATED/THAWING/FROZEN/SNOW), `trafficability`, `concealment_modifier` | Movement speed only |
| `environment/seasons.py` | `mud_depth` tracking, seasonal transitions | Weather effects only |
| `terrain/classification.py` | `SoilType` (7 types incl. MUD) | Movement friction only |

This means:
- A unit in a FOREST_DECIDUOUS cell (cover=0.5, concealment=0.9) gets **zero** protection benefit in combat
- A unit in a building (cover_value=0.7) is hit with the same probability as one in an open field
- A unit in a FIRE_TRENCH (cover_value=0.85) receives no cover from the trench
- A unit on a hilltop has no elevation advantage over one in a valley
- French knights charging through SATURATED ground at Agincourt face speed reduction but **no charge effectiveness penalty**
- Narrow straits at Salamis don't limit Persian fleet deployment

The data is there. The queries work. They just aren't called from `_execute_engagements()`.

### Issue 4: Engagement Range = Weapon Max Range

Units fire as soon as a target is detected within weapon max range. There is no concept of:
- **Effective range** vs. max range (musket effective at 100m but fires at 200m)
- **Hold fire** for better opportunity (volley fire doctrine, ambush, prepared kill zones)
- **ROE-driven engagement authorization** — the ROE engine (`c2/roe.py`) has full WEAPONS_HOLD / WEAPONS_TIGHT / WEAPONS_FREE logic but **is never called from the battle loop**

Standoff range (80% of max weapon range) only affects movement — it stops units from advancing but doesn't prevent them from firing at max range.

### Issue 5: Numerical Advantage Dominates

The engine is essentially a fair fight where larger numbers always win:
- No quality multiplier for training/experience/doctrine
- No defensive advantage multiplier for prepared positions
- Force ratio in morale and victory checks uses raw unit count, not combat power
- The time_expired tiebreaker awards victory to whoever has more active units

This explains Golan (40 vs 250 → blue loses despite historical 4.6:1 exchange ratio), Midway (7 USN vs 14 IJN → USN loses), and Trafalgar (23 vs 30 → British lose).

### Issue 6: Morale Effects Not Enforced in Engagements

The morale engine computes accuracy/speed/initiative multipliers per state:
```python
STEADY:  accuracy 1.0, speed 1.0
SHAKEN:  accuracy 0.7, speed 0.7
BROKEN:  accuracy 0.3, speed 0.3
ROUTED:  accuracy 0.1, speed 0.1
```

But `_execute_engagements()` doesn't apply these. A SHAKEN unit fires with full accuracy. A BROKEN unit still fights at 100%. Only ROUTED units stop fighting (via status check). This weakens morale cascade as a defeat mechanism.

### Issue 7: Aggregate Models Exist but Aren't Used in Battle Loop

Phase 22–23 built aggregate fire models:
- **Volley fire** (`combat/volley_fire.py`): Binomial trials with range-dependent hit tables (smoothbore: 15% at 50m, 1% at 200m)
- **Massed archery** (`combat/archery.py`): Per-archer hit tables (longbow: 20% at 50m, 1% at 250m), formation vulnerability
- **Cavalry charge** (`movement/cavalry.py`): Phase-based charge with pre-contact morale

These are standalone modules exercised in era-specific tests but **never called from `_execute_engagements()`**. The battle loop uses the generic `EngagementEngine.execute_engagement()` for all eras, which treats a longbow volley from 100 archers the same as a single rifle shot.

### Issue 8: Target Selection Is Always "Closest Enemy"

`_execute_engagements()` selects targets by Euclidean distance:
```python
dists = np.sqrt(np.sum(diffs * diffs, axis=1))
best_idx = np.argmin(dists)
```

No consideration of:
- Threat level (anti-tank vs soft target)
- Commander intent or mission priority
- Target type suitability (using anti-ship missiles on infantry)
- Kill probability at this range (prefer high-Pk shots)

### Issue 9: No Domain Filtering in Target Selection

Tank guns (125mm, 120mm) engage fighter aircraft. ATGMs engage unarmored infantry. There is zero domain validation — a T-72's 125mm smoothbore cannon can target and destroy an F-16 flying overhead. This produces nonsensical results in 8+ multi-domain scenarios where air assets are destroyed by ground units in the first few ticks before performing their mission.

The engine has `UnitDomain` (LAND, AIR, NAVAL, SUB, SPACE) and `WeaponCategory` (RIFLE, ARTILLERY, MISSILE, etc.) but these are never checked against the target's domain during engagement.

### Issue 10: Specialized Engine Effects Don't Influence Tactical Combat

CBRN, EW, and Space engines run their models but their outputs don't meaningfully affect `_execute_engagements()`:
- Chemical agents disperse via Pasquill-Gifford but don't cause tactical casualties in the battle loop
- EW jamming degrades sensors but sensor degradation doesn't affect engagement detection range in practice
- GPS denial changes DOP/CEP but guided weapon Pk isn't adjusted by GPS state
- Nuclear detonation effects aren't applied as damage in the engagement phase

These engines were built as standalone subsystems (Phases 16–18) and wired at the campaign level (Phase 25), but the tactical combat loop in `battle.py` doesn't query their state during engagement resolution.

---

## Proposed Improvements

### Improvement A: Wire Posture into Combat Resolution

**Difficulty**: Low — the mechanics exist, they just need connecting.

**Changes**:
1. In `_execute_engagements()`, extract `target.posture` (or unit status) and pass as `target_posture` to engagement engine
2. Auto-assign posture based on unit activity:
   - `MOVING` if unit moved this tick
   - `HALTED` if unit didn't move this tick (standoff reached or no movement order)
   - `DEFENSIVE` if unit is on a `defensive_sides` list and has been halted for >1 tick
   - `DUG_IN` if unit has been defensive for extended time (configurable dig-in time)
   - `FORTIFIED` reserved for scenario-placed fortifications
3. Terrain features can force posture upgrades:
   - Unit behind trench overlay → `DUG_IN`
   - Unit in fortified position → `FORTIFIED`
   - Unit on hill crest → `DEFENSIVE` (partial cover)

**Impact**: Somme, Golan, Normandy, all defensive scenarios immediately benefit.

### Improvement B: Wire Fire-on-Move Penalty

**Difficulty**: Low — the formula exists, it just needs the speed value.

**Changes**:
1. In `_execute_engagements()`, compute `shooter_speed_mps` from unit's movement in the current tick
2. Track whether unit moved this tick (boolean or distance traveled)
3. Pass to `execute_engagement()` as `shooter_speed_mps` parameter
4. Make penalty configurable per era and unit type:
   - Modern MBT with stabilization: 20% penalty
   - WW2 tank without stabilization: 50% penalty
   - Mounted archer at trot: 40% penalty, at gallop: 80% penalty
   - Infantry on foot: 15% penalty while walking, 60% while running
   - Musketeer: 90% penalty while moving (must stop to fire)
   - Artillery: 100% penalty (cannot fire while moving — must deploy)

**Impact**: Prevents the unrealistic "advancing wall of fire" pattern. Units must choose between closing distance and maintaining fire accuracy.

### Improvement C: Terrain-Combat Interaction (Comprehensive)

**Difficulty**: Medium — the terrain data infrastructure already exists and is queryable per-position. The work is wiring it into `_execute_engagements()` in `battle.py`.

**Existing infrastructure (built but disconnected from combat)**:

| Module | API | Data Available | Currently Used In |
|--------|-----|---------------|-------------------|
| `terrain/classification.py` | `properties_at(pos) → TerrainProperties` | `cover: 0.0–0.8`, `concealment: 0.0–0.9`, `trafficability: 0.2–1.0` for all 15 `LandCoverType` values | Movement speed only |
| `terrain/obstacles.py` | `obstacles_at(pos) → list[Obstacle]` | 10 `ObstacleType` values (FORTIFICATION, MINEFIELD, WIRE, etc.) via STRtree spatial queries | Movement blocking only |
| `terrain/trenches.py` | `query_at(pos) → TrenchQueryResult` | 4 `TrenchType` values with `cover_value` (0.50–0.85) and `movement_factor` | WW1 era tests only |
| `terrain/infrastructure.py` | buildings via polygon footprint | `cover_value: 0.0–1.0`, `height`, polygon bounds | LOS obstruction only |
| `terrain/heightmap.py` | `elevation_at(pos)`, `slope_at(pos)` | Elevation, slope, aspect per cell | LOS calculation only |
| `environment/conditions.py` | `LandConditions` | `GroundState` (DRY/WET/SATURATED/THAWING/FROZEN/SNOW_COVERED), `trafficability`, `concealment_modifier` | Movement speed only |
| `environment/seasons.py` | Season engine | `mud_depth` tracking, seasonal weather transitions | Weather effects only |
| `terrain/classification.py` | `SoilType` enum | 7 soil types incl. MUD with distinct properties | Movement friction only |

**None of the above feeds into `_execute_engagements()`.** Every engagement resolves as if every unit is standing in an open field.

**Changes — Terrain → Unit (terrain affects combat)**:

1. **Cover modifier from terrain classification** (direct wiring):
   - In `_execute_engagements()`, call `classification.properties_at(target_pos)` to get `TerrainProperties.cover`
   - Pass `cover` as a hit probability modifier: `terrain_cover_mod = 1.0 - cover`
   - Already-defined values in `classification.py`:
     - `OPEN: cover=0.0` (no change)
     - `GRASSLAND: cover=0.1` (10% hit reduction)
     - `FOREST_DECIDUOUS: cover=0.5` (50% hit reduction)
     - `FOREST_CONIFEROUS: cover=0.6` (60% hit reduction)
     - `URBAN_DENSE: cover=0.8` (80% hit reduction)
     - `URBAN_SPARSE: cover=0.5` (50% hit reduction)
     - `ROCKY: cover=0.4` (40% hit reduction)
   - These values are already tuned and data-driven — zero new constants needed

2. **Concealment modifier from terrain classification** (direct wiring):
   - Call `classification.properties_at(target_pos)` for `TerrainProperties.concealment`
   - Reduce effective detection range: `detection_range *= (1.0 - concealment)`
   - Already-defined values:
     - `OPEN: concealment=0.0` (no effect)
     - `FOREST_DECIDUOUS: concealment=0.9` (90% detection range reduction — dense cover)
     - `URBAN_DENSE: concealment=0.7` (70% reduction)
     - `TALL_VEGETATION: concealment=0.6` (60% reduction — hedgerows, crops)
     - `DESERT: concealment=0.1` (minimal)
   - Concealment reduces detection but not hit probability once detected (vs cover which reduces hit probability)

3. **Trench cover bonus** (direct wiring):
   - Query `trenches.query_at(target_pos)` for `TrenchQueryResult`
   - If occupied: use trench `cover_value` (0.50–0.85) as hit reduction modifier
   - Stacks with posture: unit in trench auto-promoted to DUG_IN posture (Improvement A)
   - WW1 Somme: German MG in FIRE_TRENCH (0.85 cover) = 85% hit reduction + DUG_IN posture modifier

4. **Building cover** (direct wiring):
   - Query building polygons at target position
   - If inside building: use building `cover_value` as hit reduction
   - Building height provides elevation advantage (upper floors)
   - Stalingrad: Soviet defenders in buildings get cover_value (typically 0.6–0.8)

5. **Obstacle effects on engagements**:
   - Query `obstacles_at(target_pos)` for defensive obstacles
   - FORTIFICATION obstacles: bonus cover (0.7–0.9)
   - WIRE obstacles between attacker and target: slow approach, channelize movement
   - MINEFIELD obstacles: attrition on advancing units (already modeled for movement — extend to engagement context)

6. **Elevation advantage from heightmap** (new computation, existing data):
   - Compute `elevation_delta = elevation_at(shooter_pos) - elevation_at(target_pos)`
   - High ground bonus: `elevation_mod = 1.0 + min(0.3, max(-0.1, elevation_delta / 100.0))`
     - +10% per 33m height advantage, capped at +30%
     - -10% for extreme low ground (shooting uphill)
   - Defilade detection: units just below ridgeline (`slope > threshold AND elevation_delta < 5m`) get partial hull-down equivalent
   - Golan Heights: Israeli tanks on escarpment gain +20-30% hit probability AND reduced target profile

7. **Soft ground / mud effects on combat effectiveness**:
   - Query `GroundState` from `environment/conditions.py`
   - SATURATED/MUD: cavalry charge effectiveness reduced 40–60% (momentum lost in mud)
   - WET: vehicle acceleration penalty, wheeled > tracked impact
   - FROZEN: improved trafficability but reduced traction for sharp maneuvers
   - `SoilType.MUD` compounds with `GroundState.SATURATED` for worst case
   - Agincourt: French knights charging through saturated clay = 60% charge effectiveness reduction

8. **Narrow terrain / force channeling**:
   - Compute engagement frontage from terrain geometry at engagement zone
   - Narrow strait/pass/bridge: limit `max_engagers_per_side` proportional to terrain width
   - Options for determining width:
     - Scenario YAML field `terrain_width_m` (simple, explicit)
     - Automatic: compute navigable width between obstacles/terrain edges at engagement point
   - Salamis: narrow strait limits Persian fleet to ~3 abreast vs 15+ in open sea
   - Thermopylae: pass width = 2 engagers max per side

**Changes — Unit → Terrain (units affect terrain)**:

9. **Cratering from explosions**:
   - HE/artillery impacts modify local terrain trafficability downward
   - Heavy bombardment zones become rough terrain (trafficability 0.3–0.5)
   - WW1 no-man's-land: accumulated cratering makes terrain nearly impassable
   - Track crater density per cell; above threshold → terrain degrades

10. **Defensive preparation over time** (links to Improvement A):
    - Units in DEFENSIVE posture for extended time improve local terrain cover:
      - 1+ ticks halted → HALTED posture
      - 5+ ticks → DEFENSIVE (scrape/hasty fighting position)
      - 20+ ticks → DUG_IN (prepared fighting position)
      - Scenario-placed → FORTIFIED
    - Engineering units accelerate dig-in time (existing engineering module in `logistics/`)
    - Preparation creates virtual cover: `effective_cover = terrain_cover + preparation_bonus`

11. **Defoliation and terrain modification from fire**:
    - Incendiary weapons reduce vegetation concealment (FOREST → lower concealment post-fire)
    - Nuclear thermal flash strips vegetation in radius
    - Links to existing `IncendiaryDamageEngine` fire zone expansion

**Changes — Unit-Type × Terrain Compound Effects**:

12. **Domain-specific terrain interactions**:
    - **Cavalry/horses in mud**: Charge momentum penalty scales with `ground_softness × unit_weight`
    - **Cavalry in forest**: Cannot charge in FOREST_DECIDUOUS/CONIFEROUS (trees block charge lanes). Must dismount or use column.
    - **Tanks in urban**: Vulnerability to close-range flank shots. Reduced turret traverse utility. Urban terrain negates armor advantage partially.
    - **Infantry in forest**: Bonus concealment. Shorter engagement ranges. Favors defender.
    - **Naval in shallow water**: Draft restrictions. Grounding risk near shore.
    - **Aircraft over terrain**: Terrain irrelevant for air-to-air. Ground cover applies to air-to-ground target acquisition.
    - Implemented as a `UnitDomain × LandCoverType → modifier` lookup table in YAML (data-driven, not hardcoded)

13. **Weather × terrain compound effects**:
    - Rain + clay soil = mud (GroundState transitions)
    - Snow + slopes = reduced trafficability beyond base snow penalty
    - Fog + forest = near-zero detection (concealment compounds)
    - Heat + desert = reduced crew effectiveness (links to environment conditions)
    - Already partially tracked by `environment/seasons.py` mud_depth — needs to feed into engagement

**Wiring plan (implementation path)**:
```
_execute_engagements() currently:
  1. Find targets (closest enemy)
  2. Check ammo
  3. Execute engagement (no terrain query)

_execute_engagements() after Improvement C:
  1. Find targets (closest enemy → Improvement H adds scoring)
  2. Check ammo
  3. Query terrain at target position:
     a. classification.properties_at(target_pos) → cover, concealment
     b. trenches.query_at(target_pos) → trench_cover (if trench overlay exists)
     c. obstacles_at(target_pos) → fortification bonus
     d. buildings_at(target_pos) → building cover
     e. elevation_at(shooter_pos) - elevation_at(target_pos) → elevation_mod
     f. ground_state_at(target_pos) → mud/soft ground effects
  4. Compute terrain modifier:
     effective_cover = max(terrain_cover, trench_cover, building_cover, obstacle_cover)
     terrain_hit_mod = (1.0 - effective_cover) × elevation_mod
  5. Pass terrain_hit_mod to execute_engagement()
  6. Query terrain at attacker position for soft ground effects on charge/advance
```

**Key design decision**: Use `max()` for stacking cover sources (a unit gets the best available cover, not additive). Additive would make a unit in a trench inside a forest nearly invulnerable. Concealment stacks multiplicatively (forest + fog = very low detection).

**Impact**: Agincourt (mud + archers in treeline), Normandy (hedgerow cover + concealment), Salamis (strait channeling), Golan (elevation + hull-down), Somme (trench cover + DUG_IN), Stalingrad (urban cover), all forest/urban/defensive scenarios. This single improvement, combined with Improvement A (posture wiring), transforms the engine from "open field combat only" to terrain-aware combat.

### Improvement D: Engagement Range & Hold-Fire

**Difficulty**: Medium — behavioral change to engagement decision.

**Changes**:
1. **Effective range**: Each weapon gets an `effective_range_m` (alongside `max_range_m`)
   - Engagement at effective range: full hit probability
   - Engagement at max range: reduced (natural via dispersion, but can add multiplier)
   - Below effective range: improved (closer = better)
2. **Hold-fire preference**: Units prefer to engage within effective range
   - If target is between effective and max range: fire with reduced probability (existing behavior)
   - But defensive units / ambush doctrine: suppress engagement until target crosses effective range threshold
   - Configurable via behavior rules: `hold_fire_until_effective_range: true`
3. **Wire ROE into battle loop**:
   - Call `check_engagement_authorized()` before each engagement
   - Respect WEAPONS_HOLD / WEAPONS_TIGHT / WEAPONS_FREE
   - Commander can set ROE via OODA orders
4. **Volley fire coordination**:
   - Multiple units with same target fire simultaneously (volley)
   - Higher combined effect than sequential individual shots
   - Especially important for Napoleonic and WW1 eras

**Impact**: Realistic fire discipline. Defenders hold fire until effective range. Musketeers fire disciplined volleys at 100m not 200m. Archers wait for optimal conditions.

### Improvement E: Force Quality & Training

**Difficulty**: Medium — extends existing crew_skill into a broader quality system.

**Changes**:
1. **Unit quality attribute**: `training_level` (0.0–1.0) on unit definition
   - Elite: 0.9–1.0 (SAS, Waffen-SS, Immortals, Old Guard)
   - Veteran: 0.7–0.9 (experienced regular forces)
   - Regular: 0.5–0.7 (standard conscript/regular)
   - Green: 0.3–0.5 (militia, raw recruits, levy)
   - Untrained: 0.0–0.3 (civilian, mob)
2. **Quality multiplier on engagement**:
   - Modifies crew_skill: `effective_skill = base_skill × (0.5 + 0.5 × training_level)`
   - Modifies fire rate: trained units reload faster
   - Modifies reaction time: trained units detect and engage faster
3. **Quality in force ratio calculations**:
   - Force ratio uses `sum(quality × combat_power)` not raw count
   - Morale thresholds adjusted by quality (elite units break at higher casualty rates)
   - Victory evaluation weighs quality-adjusted force ratios
4. **Doctrine effectiveness**: Per-era doctrine templates include quality modifiers
   - British gunnery superiority at Trafalgar: faster reload, better accuracy
   - Israeli tank gunnery: superior training and hull-down discipline
   - WW1 German MG doctrine: interlocking fields of fire

**Impact**: Golan (Israeli quality vs Syrian numbers), Trafalgar (British gunnery), 73 Easting (US training advantage), Midway (intelligence and training).

### Improvement F: Victory Condition Improvements

**Difficulty**: Low-Medium — extends existing victory evaluator.

**Changes**:
1. **Combat-power-weighted force advantage**: Time_expired tiebreaker uses quality-weighted combat power, not raw unit count
2. **Morale-based victory**: Rout cascade as a first-class victory condition
   - When >60% of a side is ROUTED/SURRENDERED → morale collapse
   - Morale collapse triggers faster via cascade mechanic
   - Defender advantage in morale: attacking into prepared positions degrades attacker morale
3. **Phased victory assessment**:
   - Early phase: attacker momentum vs defender preparation
   - Late phase: attrition, exhaustion, culmination
   - "Culminating point of attack" — attacker loses momentum when casualties/supply reach threshold
4. **Objective-based victory weight**:
   - Territory control checks should weight objectives by importance
   - Some objectives are decisive (capital, supply depot), others are tactical
5. **Time_expired adjudication**:
   - Instead of simple force count, evaluate: territorial gains, casualties inflicted, supply state, morale state
   - Composite score: `0.3 × force_ratio + 0.3 × territory_score + 0.2 × casualty_exchange + 0.2 × morale_ratio`

**Impact**: More nuanced outcomes for drawn-out battles. Prevents pure numerical advantage from determining every time_expired result.

### Improvement G: Aggregate Model Integration

**Difficulty**: High — requires routing logic in the battle loop per era.

**Changes**:
1. **Era-aware engagement resolution**: Battle loop checks `ctx.era` and uses appropriate model:
   - `Era.ANCIENT_MEDIEVAL` → `ArcheryEngine.fire_volley()` for ranged, `MeleeEngine` for close
   - `Era.NAPOLEONIC` → `VolleyFireEngine.fire_volley()` for musket/rifle, `CavalryChargeEngine` for charges
   - `Era.WW1` → `VolleyFireEngine` for rifle, creeping barrage for artillery
   - `Era.WW2` / `Era.MODERN` → existing `EngagementEngine.execute_engagement()`
2. **Formation-based casualty assessment**:
   - Aggregate models compute casualties per volley (e.g., 150 muskets × 5% hit = 7.5 casualties)
   - Apply these as fractional unit health damage
   - Currently: one engagement = one round = one hit/miss for the whole unit
3. **Simultaneous fire**: Multiple units in volley fire shoot together
   - Combine fire effects into single damage calculation
   - Prevents "one unit shoots, then the next" serial behavior

**Impact**: Napoleonic battles actually have meaningful casualties. Longbow volleys at Agincourt produce realistic casualty rates. WW1 MG positions create actual kill zones.

### Improvement H: Target Selection & Tactical AI

**Difficulty**: Medium — extends target selection with scoring.

**Changes**:
1. **Threat-based scoring**: Replace closest-enemy with weighted score:
   - `score = threat × Pk × value` where:
     - `threat` = target's ability to damage us (weapon range, damage potential)
     - `Pk` = our probability of hitting at current range
     - `value` = target's tactical value (commander, artillery, SAM)
2. **Commander intent integration**:
   - OODA DECIDE phase sets priority target types for each unit
   - Tanks prioritize other tanks, infantry prioritizes infantry, AA prioritizes aircraft
3. **Weapon-target matching**: Don't use anti-ship missiles on infantry
   - Match weapon category to target category
   - Prefer appropriate weapons even if not optimal range
4. **Fire concentration**: Multiple units coordinate fire on same high-value target
   - Especially important for concentrated fire doctrine (Nelson's crossing the T, Lanchester's concentration of force)

**Impact**: More realistic target prioritization. Units don't waste HE on heavily armored targets. Artillery focuses on high-value targets. Air defense prioritizes aircraft over ground units.

### Improvement I: Domain-Appropriate Engagement Filtering

**Difficulty**: Low — add domain check before engagement.

**Changes**:
1. **Domain validation**: Before engaging, check if weapon can target the enemy domain:
   - Tank guns (RIFLE category, LAND domain weapons) cannot target AIR domain units
   - SAMs (MISSILE category, anti-air) should only target AIR domain
   - Torpedoes only target NAVAL/SUB domain
   - ATGMs should prefer armored targets over infantry
2. **Weapon-target compatibility matrix**:
   - Map `WeaponCategory × TargetDomain → allowed/penalty/forbidden`
   - Some weapons are multi-domain (Vulcan cannon can be AA or ground support)
   - ATGM vs soft target: allow but with reduced effectiveness
3. **Engagement filtering in battle loop**:
   - Skip targets whose domain is incompatible with all available weapons
   - Select weapon THEN find compatible targets, not the reverse

**Impact**: Fixes 8+ multi-domain scenarios. F-16s stop being destroyed by tank guns. Proper air-to-air, ground-to-ground, and AA engagement routing.

### Improvement J: Specialized Engine Integration

**Difficulty**: Medium-High — requires querying subsystem state during engagement.

**Changes**:
1. **CBRN casualties in battle loop**:
   - Query contamination grid at unit position each tick
   - Apply chemical/radiation exposure as damage (already exists in CBRN engine)
   - Check MOPP level for protection
2. **EW effects on detection**:
   - Query EW engine for J/S ratio at sensor location
   - Apply jamming degradation to detection range in `_execute_engagements()`
   - GPS spoofing affects guided weapon Pk
3. **Space effects on precision weapons**:
   - Query GPS engine for current DOP at unit location
   - Apply CEP degradation to guided weapon Pk
   - SATCOM disruption affects C2 orders propagation
4. **Nuclear effects on units**:
   - Nuclear detonation applies blast/thermal/radiation damage to all units in radius
   - Use existing nuclear blast model output as input to damage engine

**Impact**: CBRN, EW, Space scenarios produce realistic specialized effects instead of defaulting to kinetic-only combat.

### Improvement K: Wire Suppression Engine

**Difficulty**: Low — the engine exists, it's hardcoded to 0.0.

**Changes**:
1. In `_execute_engagements()`, replace `suppression_level=0.0` with actual suppression state per unit
2. Track suppression accumulation: sustained fire on a position builds suppression level
3. Suppression feeds into accuracy (already in hit_probability formula), speed (suppressed units move slower), and morale (suppression degrades morale)
4. Suppression decays over time when fire lifts (already in `SuppressionEngine`)

**Impact**: Enables "suppress and maneuver" doctrine. MG positions create actual suppression effects. Artillery prep fires suppress defenders before assault. All infantry combat becomes more realistic.

### Improvement L: Weather & Night Effects in Combat

**Difficulty**: Medium — requires querying weather engine and astronomy engine during engagement.

**Changes**:
1. **Rain/fog on engagement**: Query weather state, apply hit probability penalty:
   - Light rain: 5% penalty. Heavy rain: 15%. Fog: 30%. Storm: 40%.
   - Guided weapons less affected by visual weather (use sensor-type check)
2. **Night combat**: Query `AstronomyEngine` for illumination level
   - Full darkness (new moon): 50% detection range for visual sensors
   - Thermal/NVG sensors unaffected or enhanced at night
   - Illumination rounds create temporary 100% visibility zones
3. **Sea state on naval gunnery**: Wave height increases dispersion
4. **Wind on ballistics**: Already in RK4 model, but wind vector not passed to it from weather engine
5. **Obscurants**: Smoke screens reduce detection in specific sectors (directional)

**Impact**: Night operations, adverse weather scenarios, naval operations in rough seas. Thermal sensor advantage at night is a fundamental modern warfare mechanic.

### Improvement M: Logistics Engine Wiring

**Difficulty**: Medium — requires calling 7 logistics engines from simulation loop.

**Changes**:
1. **Maintenance breakdowns**: Call `MaintenanceEngine` each tick. Equipment can break down (Poisson), removing units temporarily until repaired.
2. **Medical evacuation**: Call `MedicalEngine` for wounded units. M/M/c queue determines evacuation time and survival.
3. **Engineering**: Call `EngineeringEngine` for obstacle creation/clearance and route improvement.
4. **Transport**: Call `TransportEngine` for supply delivery routing.
5. Gate combat capability by supply state (low ammo → reduced fire rate; no fuel → immobile)

**Impact**: Campaign-length scenarios decided by logistics (Stalingrad, Napoleonic Russia). Equipment attrition from mechanical failure (major in WW2 North Africa).

### Improvement N: Indirect Fire Routing

**Difficulty**: Medium — requires routing artillery/mortar engagements through indirect fire engine.

**Changes**:
1. Detect weapon type: if `WeaponCategory.ARTILLERY` or `WeaponCategory.MORTAR`, route to `IndirectFireEngine`
2. Indirect fire uses CEP-based area effect, not direct-fire Pk
3. Observer correction improves accuracy over successive fire missions
4. Minimum range for indirect fire (mortar cannot fire at target 10m away)
5. Fire mission timing: request → compute → flight time → impact (delay, not instant)

**Impact**: Artillery-heavy scenarios (WW1 barrages, modern combined arms). Currently all artillery uses the same direct-fire Pk model as rifles — fundamentally wrong.

### Improvement O: Mathematical Model Hardening

**Difficulty**: High — requires formula changes with careful validation.

**Changes**:
1. **Blast damage**: Replace Gaussian `exp(-d²/2σ²)` with Hopkinson-Cranz overpressure scaling:
   - `DP = K × (R / W^(1/3))^(-a)` with regime-dependent exponent (strong shock: a≈2.65, weak shock: a≈1.4)
   - Use same approach as nuclear blast (already implemented correctly there) scaled to conventional weapons
   - Apply overpressure thresholds for kill/injury/suppression
2. **Morale Markov constants**: Research and source from:
   - Trevor Dupuy "Attrition" (1990) — WEI/WUV combat power methodology
   - S.L.A. Marshall "Men Against Fire" — combat participation rates
   - NATO STANAG on combat stress
   - Derive casualty_weight, suppression_weight, leadership_weight from literature
3. **Maintenance model**: Evaluate Weibull distribution as replacement for exponential:
   - Weibull shape parameter k: k<1 = infant mortality, k=1 = exponential (constant), k>1 = wear-out
   - Military equipment typically k=1.2–1.8 (gradual wear-out dominates)
   - Source MTBF from MIL-HDBK-217F reliability prediction
4. **Hit probability**: Review multiplicative modifier independence assumption:
   - Consider conditional probability: `P(hit | conditions) = P(hit | good) × P(good conditions)` rather than `P = base × mod1 × mod2 × mod3`
   - Ensure modifiers don't compound to unrealistic values (e.g., 0.01 Pk in moderate conditions)
   - Research whether area-ratio or conditional formulation is more appropriate
5. **A* threat cost**: Replace linear `(threat_radius - d) / threat_radius × 5` with exponential:
   - `cost = k × exp(α × (1 - d/threat_radius))` where α controls steepness
   - More realistic: entering the last 10% of threat radius should be much more costly than the first 10%

**Impact**: Global fidelity lift across all scenarios. Blast model affects all indirect fire and explosives. Morale model affects all battles. Maintenance affects all campaigns.

### Improvement P: Constant Sourcing & Configuration

**Difficulty**: Medium — research-heavy, low implementation risk.

**Changes**:
1. **Source the 10 critical unsourced constant groups** (listed in Mathematical Model Audit section)
2. **Move ~30 assessment thresholds** from hardcoded `_THRESHOLDS` tuples to pydantic `AssessmentConfig` model
3. **Move ~40 weight constants** from hardcoded values to pydantic config models with YAML overrides
4. **Add source citations as comments** for all physics and military constants:
   ```python
   # Glasstone & Dolan, "Effects of Nuclear Weapons", 3rd ed., 1977, Table 3.74
   _BLAST_LETHAL_PSI = 12.0
   ```
5. **Create `constants.py` reference module** per domain (e.g., `combat/constants.py`, `morale/constants.py`) that collects sourced constants with citations, replacing inline magic numbers

**Impact**: Audit trail for every number in the engine. Configurable constants allow per-era and per-doctrine tuning without code changes. Citations make the codebase defensible as a serious modeling effort.

---

## Additional Disconnected Systems Discovered

Beyond the 10 systemic issues documented above, a comprehensive codebase audit revealed **7 additional built-but-unwired systems** that have handles in the engine but produce no effect on simulation outcomes:

### Issue 11: Suppression Engine Hardcoded to Zero

**File**: `simulation/battle.py:1148`

The full `SuppressionEngine` class exists in `combat/suppression.py` with `compute_suppression_effect()`, `update_suppression()`, `spread_suppression()`, and a 5-level suppression state machine. But in `battle.py`, the engagement call passes `suppression_level=0.0` as a hardcoded constant. Every unit is unsuppressed in every engagement.

**Should affect**: Suppressed units should have reduced accuracy, speed, initiative. Sustained fire should build suppression, making it harder for targets to return fire. This is a fundamental infantry combat mechanic — "suppress and maneuver" doctrine depends on it.

### Issue 12: Target Identification Confidence Never Assessed

Parameters `identification_level` and `identification_confidence` exist in the engagement signature and are tracked by the `IdentificationEngine` module. Fog of war maintains identification status per contact. But these values are **never queried** during engagement — targets are engaged regardless of identification confidence.

**Should affect**: Low-confidence targets should trigger ROE checks (especially under WEAPONS_TIGHT). Misidentification should be possible (fratricide risk). IFF failure should prevent engagement in strict ROE modes.

### Issue 13: Command Authority Engine Not Instantiated

`c2/command.py` contains a full `CommandEngine` with hierarchical authority and command range. But `scenario.py:1076–1077` explicitly sets `command_engine=None` with a comment: "CommandEngine requires hierarchy/task_org — create minimal stubs."

**Should affect**: Units outside command range should have degraded initiative and slower OODA cycles. Loss of a commander should cascade to subordinate units. Command disruption should be a first-class defeat mechanism.

### Issue 14: Logistics Engines Beyond Consumption Are Silent

Seven logistics engines exist but are never called from the simulation loop:

| Engine | Module | Built For |
|--------|--------|-----------|
| `MaintenanceEngine` | `logistics/maintenance.py` | Equipment breakdown/repair (Poisson) |
| `MedicalEngine` | `logistics/medical.py` | Casualty evacuation (M/M/c queue) |
| `EngineeringEngine` | `logistics/engineering.py` | Route improvement, obstacle creation |
| `TransportEngine` | `logistics/transport.py` | Supply transport routing |
| `DisruptionEngine` | `logistics/disruption.py` | Supply route interdiction |
| `NavalLogisticsEngine` | `logistics/naval_logistics.py` | Naval supply operations |
| `PrisonerEngine` | `logistics/prisoner.py` | Prisoner handling |

Only `ConsumptionEngine` is called (battle.py:339–340) for supply consumption. Maintenance breakdowns never happen. Medical evacuation never occurs. Engineering never builds or clears obstacles. Campaigns that should be decided by logistics (Stalingrad, Napoleonic Russia) have no logistical pressure.

### Issue 15: Weather Effects Stop at Visibility

The `WeatherEngine`, `SeaStateEngine`, and `ObscurantsEngine` compute detailed environmental state including fog, rain, snow, wind, sea state, and smoke. But only `visibility_m` is extracted and passed to the engagement loop. Detailed effects are lost:

- Rain/fog: should reduce sensor performance beyond just visibility distance
- Snow/ice: should affect vehicle mobility and weapon reliability
- Sea state: should affect naval gunnery accuracy and aircraft launch/recovery
- Smoke/obscurants: should reduce detection range in specific sectors (directional)
- Wind: should affect ballistic trajectory and chemical dispersal (dispersal engine exists but isn't queried mid-battle)

### Issue 16: Night/Day Cycle Has No Combat Effect

`AstronomyEngine` computes solar elevation, lunar illumination, twilight phases, and the `TimeOfDayEngine` derives visibility contrast and illumination level. None of this affects engagement:

- Night engagements should favor units with thermal/NVG sensors
- Dawn/dusk should create silhouette advantages (backlit targets)
- Moonless nights should drastically reduce visual detection
- Illumination rounds should create temporary visibility windows

### Issue 17: Indirect Fire Engine Not Routed

`combat/indirect_fire.py` contains artillery/mortar indirect fire logic separate from the direct-fire engagement model. It's never called from `_execute_engagements()`, which treats all weapons as direct-fire. Artillery should use indirect fire mechanics (area effect, observer correction, CEP-based dispersion, fire mission timing).

### Issue 18: Naval Domain Engines Never Routed (5 engines)

Five naval combat engines are built and in some cases instantiated, but **never called** from the engagement loop:

| Engine | Module | Status | Purpose |
|--------|--------|--------|---------|
| `NavalSurfaceEngine` | `combat/naval_surface.py` | Never instantiated | Surface action group combat |
| `NavalSubsurfaceEngine` | `combat/naval_subsurface.py` | Never instantiated | Torpedo warfare, evasion/CM |
| `NavalGunneryEngine` | `combat/naval_gunnery.py` | Instantiated (WW2 era) | Bracket convergence, salvo fire |
| `NavalGunfireSupportEngine` | `combat/naval_gunfire_support.py` | Never called | Shore bombardment |
| `MineWarfareEngine` | `combat/mine_warfare.py` | Never instantiated | Mine laying/sweeping |

All naval scenarios currently use the generic `EngagementEngine.execute_engagement()` — the same Pk formula used for rifle fire. This means a Bismarck broadside and an infantry rifle shot use the same math.

### Issue 19: Detection Intelligence Pipeline Disconnected (4 engines)

Beyond target identification (Issue 12), four entire detection subsystem engines from Phase 3 are built but **never instantiated in the scenario loader**:

| Engine | Module | Purpose |
|--------|--------|---------|
| `IntelFusionEngine` | `detection/intel_fusion.py` | Multi-source intelligence correlation, contact deduplication |
| `DeceptionEngine` | `detection/deception.py` | Decoy generation, feint assessment |
| `SonarEngine` | `detection/sonar.py` | Active/passive sonar detection for naval |
| `UnderwaterDetectionEngine` | `detection/underwater_detection.py` | MAD, periscope detection, dipping sonar |

The detection module computes SNR-based detection probability (high-fidelity model), but this information is consumed only for the initial "can I see the target" gate. **Detection quality (SNR level, identification confidence, tracking accuracy) never modulates engagement Pk.** A marginally detected target at SNR=1dB and a perfectly tracked target at SNR=40dB are treated identically in the engagement loop.

### Issue 20: Population/Civilian Engines Never Called (5 engines)

Phase 12 built `population/civilians.py` and Phase 24 extended with `insurgency.py`. Five population engines exist but are never instantiated or called from the simulation loop:

| Engine | Module | Purpose |
|--------|--------|---------|
| `CivilianManager` | `population/civilians.py` | Civilian population tracking, displacement |
| `CollateralEngine` | `population/collateral.py` | Collateral damage assessment |
| `DisplacementEngine` | `population/displacement.py` | Refugee flow modeling |
| `CivilianHumintEngine` | `population/humint.py` | Civilian intelligence reporting |
| `InfluenceEngine` | `population/influence.py` | Hearts-and-minds, information operations |

These are critical for COIN, gray zone, escalation, and unconventional warfare scenarios. Without them, collateral damage has no consequence, civilian displacement doesn't occur, and population sentiment doesn't shift.

### Issue 21: Strategic/Campaign Engines Never Called (4 engines)

Four engines designed for operational/strategic tick resolution are built but never called — not even from `CampaignManager`:

| Engine | Module | Status |
|--------|--------|--------|
| `AirCampaignEngine` | `combat/air_campaign.py` | Never instantiated |
| `IadsEngine` | `combat/iads.py` | Never instantiated |
| `StrategicBombingEngine` | `combat/strategic_bombing.py` | Instantiated (WW2 era), never called |
| `StrategicTargetingEngine` | `combat/strategic_targeting.py` | Never instantiated |

These affect the Gulf War EW, WW2 strategic bombing, and modern SEAD scenarios where air campaign mechanics should drive the operational picture.

### Issue 22: Terrain Managers Not Instantiated (4 managers)

Terrain data infrastructure is rich (Issue 3), but several terrain managers from Phase 1–2 are never instantiated in the scenario loader, meaning their data is never loaded or queryable:

| Manager | Module | Purpose |
|---------|--------|---------|
| `InfrastructureManager` | `terrain/infrastructure.py` | Buildings, roads, bridges with cover values |
| `ObstacleManager` | `terrain/obstacles.py` | STRtree-indexed minefields, wire, fortifications |
| `HydrographyManager` | `terrain/hydrography.py` | Rivers, water bodies, fording points |
| `PopulationManager` | `terrain/population.py` | Settlement density, urban boundaries |

Without instantiating `InfrastructureManager`, building cover values (Improvement C, item 4) cannot be queried. Without `ObstacleManager`, obstacle cover (Improvement C, item 5) cannot be queried. These are **prerequisites** for terrain-combat wiring.

---

## Summary: Total Disconnected Systems

| Category | Count | Engines |
|----------|-------|---------|
| Battle loop gaps (Issues 0–10) | 11 | Posture, fire-on-move, terrain, ROE, morale, aggregate×3, target selection, domain filter, subsystem integration |
| Additional tactical gaps (Issues 11–17) | 7 | Suppression, target ID, command authority, logistics×7, weather, night/day, indirect fire |
| Naval domain (Issue 18) | 5 | Surface, subsurface, gunnery, gunfire support, mine warfare |
| Detection pipeline (Issue 19) | 4 | Intel fusion, deception, sonar, underwater detection |
| Population/civilian (Issue 20) | 5 | Civilians, collateral, displacement, HUMINT, influence |
| Strategic/campaign (Issue 21) | 4 | Air campaign, IADS, strategic bombing, strategic targeting |
| Terrain managers (Issue 22) | 4 | Infrastructure, obstacles, hydrography, population |
| **Total** | **~40** | **Built, tested, but disconnected from simulation** |

---

## Mathematical Model Audit

A comprehensive audit of all 20+ mathematical models in the engine assessed their mathematical approach, constant sourcing, and fidelity level.

### High-Fidelity Models (textbook physics, well-sourced constants)

| Model | Module | Approach | Notes |
|-------|--------|----------|-------|
| RK4 Ballistics | `combat/ballistics.py` | 4th-order Runge-Kutta + Mach-dependent drag + Coriolis | ISA standard constants. Mach piecewise but reasonable. Excellent. |
| Detection SNR | `detection/detection.py` | Unified SNR framework + erfc(Pd) | Standard radar range equation, Boltzmann constant, signal detection theory. Best model in codebase. |
| Nuclear Effects | `cbrn/nuclear.py` | Hopkinson-Cranz + inverse-square thermal + exponential radiation | Glasstone-sourced constants. Well-researched framework. |
| Chemical Dispersal | `cbrn/dispersal.py` | Pasquill-Gifford Gaussian puff + Turner coefficients | Standard military/EPA model. Ground reflection formula correct. |
| LOS Ray March | `terrain/los.py` | DDA + earth curvature (4/3 effective earth) | WGS84, military standard. Good implementation. |

### Medium-Fidelity Models (sound approach, some unsourced constants)

| Model | Module | Approach | Concerns |
|-------|--------|----------|----------|
| DeMarre Penetration | `combat/damage.py` | DeMarre^1.5 + armor effectiveness table | Exponent is correct (Glasstone). **Armor effectiveness table has no citations** — values appear calibrated for balance (Composite=1.5 KE/2.5 HEAT, Reactive=1.0/2.0). Velocity decay linearized, not RK4. |
| EW Jamming J/S | `ew/jamming.py` | Schleher self-screening/stand-off equations | Equations correct. Assumes narrowband (no wideband). Deceptive multiplier 1.5 is tuning. |
| Sonar | `detection/sonar.py` | Standard sonar equation | TL correct. **Convergence zones hardcoded at 55km/110km** (should depend on sound velocity profile). Bearing error simplified. |
| Naval Gunnery | `combat/naval_gunnery.py` | Bracket convergence + 2D Gaussian dispersion | WW2-sourced. Linear convergence (reality is logarithmic). **Base Pk 0.05/shell and spotting correction 0.4 are tuning.** |
| Weather Markov | `environment/weather.py` | 8-state Markov chain + OU wind process | Climate zone data sourced. **Markov matrix is static within seasons** (ignores within-season drift). |
| DEW Beer-Lambert | `combat/directed_energy.py` | Beer-Lambert transmittance + exponential laser Pk | Physics correct. **Extinction coefficients wavelength-independent** (real lasers vary 1–10 dB/km). |
| Volley Fire | `combat/volley_fire.py` | Binomial + range table | Phit tables from historical records. Smoke model simplified. No reload time modeled. |
| Archery | `combat/archery.py` | Binomial + armor reduction | Range tables from historical records. Armor reduction empirical but reasonable. |

### Low-Fidelity Models (significant simplifications or unsourced constants)

| Model | Module | Issue | Recommended Fix |
|-------|--------|-------|-----------------|
| **Hit Probability** | `combat/hit_probability.py` | Multiplicative modifier chain `P = disp × skill × motion × vis × posture × unc × cond` lacks theoretical justification. Each modifier is independent — no interaction effects. base_hit_fraction=0.8 is tuning. | Research area-ratio or conditional probability formulation. Consider correlated modifiers. |
| **Blast/Fragmentation** | `combat/damage.py` | Uses Gaussian damage envelope `P_kill = exp(-d²/2σ²)` — this is a **game mechanic, not physics**. Real blast overpressure scales as ~1/r (strong shock) to ~1/r³ (far field), not Gaussian. Posture protection multipliers (DUG_IN=0.3, FORTIFIED=0.1) have no citations. | Replace with Hopkinson-Cranz overpressure scaling (same approach as nuclear, scaled down). Source posture protection from military engineering data. |
| **Morale Markov** | `morale/state.py` | **ALL constants are arbitrary tuning parameters** with no military research sources. base_degrade=0.05, casualty_weight=2.0, suppression_weight=1.5, leadership_weight=0.3. State-dependent scaling (0.2, 0.3) is ad hoc. | Validate against Dupuy WEI/WUV model, S.L.A. Marshall combat stress research, or NATO STANAG morale data. Key reference: Trevor Dupuy "Attrition" (1990). |
| **Maintenance Poisson** | `logistics/maintenance.py` | Exponential time-to-failure assumes constant hazard rate — ignores wear-in and wear-out phases (bathtub curve). base_mtbf=500h appears arbitrary. Environmental stress threshold is binary. | Consider Weibull distribution (shape parameter captures infant mortality and wear-out). Source MTBF from MIL-HDBK-217F or actual equipment reliability data. |
| **A* Threat Avoidance** | `movement/pathfinding.py` | Threat cost uses linear ramp: `(threat_radius - distance) / threat_radius × 5.0`. Linear means equal cost at 50% and 90% of threat radius. Should be exponential (much higher cost near threat center). | Use exponential: `exp(k × (1 - distance/threat_radius))` for more realistic threat avoidance. |

### ~180 Hardcoded Constants Inventory

The codebase contains approximately **180 distinct hardcoded numeric constants** across all modules. By category:

| Category | Count | Examples | Risk |
|----------|-------|----------|------|
| Assessment & decision thresholds | ~30 | Force ratio breakpoints (0.4, 0.8, 1.5, 3.0), morale thresholds | Medium — affect AI behavior significantly |
| Weights & multipliers | ~40 | Assessment weights (0.30, 0.10, 0.15), personality modifiers (0.2–0.4) | High — determine relative importance of factors |
| Physics constants | ~25 | Nuclear K=1e7, Boltzmann, Earth radius, speed of light | Low — well-sourced from standards |
| Time & duration scales | ~25 | Planning duration 28800s, OODA timing, cooldowns | Medium — affect tempo |
| Tactical percentages | ~20 | Force allocation 0.25, reserve 0.15, loss rate 0.02 | Medium — affect combat outcomes |
| Environmental factors | ~15 | Visibility baselines (10km), weather scales, fog 200m | Low-Medium — reasonable defaults |
| Detection & range | ~15 | Uncertainty 5% of range, decay constants, baselines | Medium — affect detection realism |

**Zero TODO/FIXME/HACK/PLACEHOLDER comments were found.** All magic numbers are intentional design decisions — but many lack sourcing or theoretical justification.

### Constants Requiring Literature Sourcing

These constants significantly affect simulation outcomes but have no cited source:

1. **Armor effectiveness matrix** (`damage.py`): Composite×KE=1.5, Reactive×HEAT=2.0 — appears calibrated, not sourced
2. **Morale weights** (`morale/state.py`): casualty_weight=2.0, suppression=1.5 — no military psychology reference
3. **Maintenance MTBF** (`logistics/maintenance.py`): base 500h — no MIL-HDBK reference
4. **Posture blast/frag protection** (`damage.py`): DUG_IN blast=0.3, frag=0.15 — no engineering manual reference
5. **Detection uncertainties** (`detection/`): Position=5% of range, bearing=1–5° — reasonable but unsourced
6. **Assessment weights** (`c2/ai/assessment.py`): force_ratio=0.30, terrain=0.10, supply=0.15 — no doctrinal source
7. **Desperation weights** (`c2/ai/assessment.py`): casualty=0.30, supply=0.20, morale=0.20 — no escalation theory source
8. **Torpedo evasion** (`combat/naval_subsurface.py`): decoy=0.4, depth=0.3, knuckle=0.2 — no naval warfare source
9. **Bracket convergence** (`combat/naval_gunnery.py`): spotting_correction=0.4, base_pk=0.05/shell — no WW2 gunnery source
10. **Casualty thresholds** (`simulation/victory.py`): Various force ratio breakpoints — no Clausewitz/Dupuy reference

---

## Scenario-Specific Analysis: What Fixes Each Historical Battle

### Agincourt (Currently: French win → Should: English decisive)
- **[C]** Mud terrain reduces cavalry charge effectiveness by 60%
- **[A]** English longbowmen in DEFENSIVE posture behind stakes
- **[G]** Massed archery model: 400 archers × 12 arrows/min = realistic attrition
- **[B]** French knights can't fire while charging (melee only, must close)
- **[D]** Archers hold fire until optimal 150m, not waste arrows at 250m

### Cannae (Currently: mutual annihilation → Should: Carthaginian decisive)
- **[H]** Carthaginian cavalry targets Roman cavalry first (historical: flank then rear)
- **[E]** Veteran Carthaginian troops vs Roman conscripts
- **[F]** Roman morale cascade when encircled (no retreat route)
- **[C]** Flanking bonus when units attack from multiple directions

### Salamis (Currently: Persian win → Should: Greek decisive)
- **[C]** Narrow strait limits Persian fleet deployment (force channeling)
- **[E]** Greek triremes superior in close combat (ramming doctrine)
- **[H]** Greeks prioritize tightly packed Persian ships

### Trafalgar (Currently: British lose all → Should: British decisive, 0 sunk)
- **[E]** British gunnery superiority: faster reload (2 min vs 5 min), better accuracy
- **[H]** Breaking the line: British approach concentrates fire on fewer enemies
- **[F]** Franco-Spanish morale breaks after losing flagships
- **[A]** Franco-Spanish fleet initially defensive (poor crew quality)

### Austerlitz/Waterloo (Currently: draws → Should: decisive battles)
- **[G]** Volley fire model: 500 muskets at 100m = 25 casualties per volley
- **[D]** Hold fire until effective range (100m for muskets, not 200m)
- **[B]** Infantry must stop to fire (90% move-and-shoot penalty)
- **[A]** British infantry squares resist cavalry charges (DEFENSIVE posture)

### Midway (Currently: USN loses → Should: USN decisive)
- **[E]** USN intelligence advantage (codebreaking → surprise)
- **[H]** USN attacks IJN carriers while aircraft on deck (vulnerability window)
- **[F]** Loss of 4 carriers → IJN morale collapse

### Somme July 1 (Currently: mutual annihilation → Should: 7:1 German casualty advantage)
- **[A]** German MG positions in DUG_IN/FORTIFIED posture (60% hit reduction)
- **[E]** British infantry advancing in line = high vulnerability
- **[C]** Trench systems provide near-total protection from rifle fire
- **[F]** British morale breaks after catastrophic losses

### Stalingrad (Currently: German wins → Should: Soviet holds)
- **[C]** Urban terrain: 40% hit reduction in buildings
- **[A]** Soviet defenders in DEFENSIVE/DUG_IN posture in ruins
- **[F]** Reinforcement timing: Soviet reinforcements shift force balance
- **[E]** Soviet familiarity with urban terrain

### Golan Heights (Currently: Israeli annihilated → Should: Israeli 4.6:1 exchange)
- **[A]** Israeli tanks in HULL_DOWN on ridge (40% hit reduction)
- **[E]** Israeli gunnery superiority (training_level: 0.9 vs 0.5)
- **[C]** Elevation advantage from Golan escarpment
- **[H]** Israeli tanks prioritize T-62s over BMP-1s

### Normandy Bocage (Currently: US wiped out → Should: 2:1 attacker cost)
- **[C]** Hedgerow terrain provides cover (40% hit reduction)
- **[A]** German infantry in DEFENSIVE behind hedgerows
- **[E]** German experience in bocage defense
- **[D]** Short engagement ranges in bocage (100–300m visibility)

---

## Design Principles for Block 5

1. **Wire before building**: 20+ built-but-disconnected systems exist (posture, shooter speed, ROE, morale effects, suppression, terrain, aggregate models, weather, night/day, logistics, command authority, indirect fire, identification). Priority is connecting existing systems, not creating new ones. The codebase has far more capability than the battle loop exercises.

2. **Data-driven, not hardcoded**: Terrain cover, quality multipliers, effective ranges, assessment weights, and morale constants belong in YAML configuration or pydantic models, not inline magic numbers. ~180 hardcoded constants were identified; the most impactful ~70 should be configurable.

3. **Era-appropriate resolution**: Modern combat uses individual engagement. Napoleonic uses volley fire aggregate. Ancient uses massed archery aggregate. The battle loop should route by era.

4. **Backward compatible**: All new mechanics should have config-gated defaults matching current behavior. Existing scenarios produce the same results until recalibrated.

5. **Validate against history**: Every change must improve at least one historical scenario's fidelity without degrading others. Use the 16 historical scenarios as a regression test.

6. **Source every constant**: No unsourced magic numbers in the final engine. Every military, physics, or empirical constant must cite its source (textbook, standard, or documented calibration rationale). Constants from standards (Glasstone, ISA, SI) are already correct. The ~10 critical unsourced groups must be researched.

7. **Mathematical models must match their domain**: Blast damage should use overpressure physics, not game-mechanic Gaussians. Morale should reference combat stress research, not arbitrary weights. Maintenance should use reliability engineering (Weibull), not simplified exponentials. The goal is a defensible simulation, not a balanced game.

8. **Complete interactibility**: Every system that exists should affect the systems it logically influences. Terrain affects combat, weather affects detection, morale affects accuracy, supply affects capability, time of day affects sensors. No "island" subsystems running in isolation.

---

## Open Questions

1. **How much terrain detail per scenario?** The terrain classification system already provides per-cell `cover`, `concealment`, and `trafficability` for all 15 `LandCoverType` values. The primary wiring work is calling `properties_at(pos)` during engagements. Scenario-specific terrain features (ridgelines, straits, hedgerows) can be specified via:
   - Existing terrain grid generation (heightmap, land cover assignment)
   - Scenario YAML `terrain_features` list for named features (pass width, ridge position)
   - Trench overlay for WW1 scenarios (already exists in `trenches.py`)

2. **Force channeling**: How to model narrow straits / passes limiting simultaneous engagers? Options:
   - Per-scenario `max_engagers_per_side` override
   - Spatial width constraint computed from terrain
   - Engagement queue (units wait their turn)

3. **Aggregate vs individual resolution**: When should the engine use aggregate models?
   - Always for pre-modern eras?
   - Only for massed formations (>10 units of same type)?
   - Hybrid: aggregate for volley fire, individual for melee/special weapons?

4. **Intelligence / surprise**: Midway's outcome depends on US codebreaking. How to model:
   - Pre-battle intelligence giving one side full enemy positions?
   - Surprise bonus on first engagement (higher Pk, lower morale threshold)?
   - "Vulnerability window" concept (aircraft on deck, caught reloading)?

5. **Calibration methodology**: After implementing improvements, how to calibrate?
   - Per-scenario YAML overrides (current approach)?
   - Per-era default parameters?
   - Automated calibration via Monte Carlo against historical outcome ranges?

---

## Risk Assessment

| Improvement | Difficulty | Risk | Reward | Scenarios Fixed |
|-------------|-----------|------|--------|-----------------|
| F0. is_tie Bug Fix | Trivial | None | High | 15+ scenarios mislabeled "Draw" |
| A. Wire Posture | Low | Low — existing mechanics | High | Somme, Golan, Normandy, Stalingrad, Cambrai |
| B. Fire-on-Move | Low | Low — existing formula | Medium | All advancing-fire scenarios |
| I. Domain Filtering | Low | Low — add domain check | High | Korean, Suwalki, Space, Taiwan (8+) |
| K. Wire Suppression | Low | Low — existing engine | High | All sustained-fire scenarios |
| C. Terrain-Combat | Medium | Low — existing data, new wiring | Very High | Agincourt, Normandy, Salamis, Golan, Somme, Stalingrad (12+) |
| E. Force Quality | Medium | Low — extends crew_skill | High | Golan, Trafalgar, Midway, 73 Easting (6+) |
| H. Target Selection | Medium | Medium — changes patterns | Medium | All multi-domain, COIN, TOW-vs-infantry |
| F. Victory Conditions | Low-Med | Low — extends evaluator | Medium | All time_expired battles |
| D. Hold-Fire / ROE | Medium | Medium — behavioral change | Medium | Napoleonic, WW1, ambush scenarios |
| G. Aggregate Models | High | High — alt resolution path | High | Austerlitz, Waterloo, Agincourt, Somme |
| J. Engine Integration | Med-High | Medium — cross-module | Medium | CBRN, EW, Space scenarios (6+) |
| L. Weather/Night in Combat | Medium | Low — existing engines | Medium | Night scenarios, naval, adverse weather |
| M. Logistics Wiring | Medium | Low — existing engines | Medium | Campaign-length scenarios |
| N. Indirect Fire Routing | Medium | Medium — new route path | Medium | Artillery-heavy scenarios |
| Q. Naval Domain Routing | Medium | Medium — 5 engine routes | High | All naval scenarios (Trafalgar, Jutland, Midway, Falklands, Taiwan) |
| R. Detection Pipeline | Medium | Low — instantiate + wire | Medium | All detection-dependent scenarios |
| S. Population/Civilian Wiring | Medium | Low — instantiate + wire | Medium | COIN, gray zone, escalation scenarios |
| T. Strategic/Campaign Engines | Medium | Medium — campaign-level routing | Medium | Gulf War EW, WW2 strategic bombing, SEAD |
| U. Terrain Manager Instantiation | Low | Low — prerequisite for C | High | ALL scenarios (enables terrain queries) |
| O. Math Model Hardening | High | Medium — formula changes | Very High | Blast, morale, maintenance, hit probability |
| P. Constant Sourcing | Medium | Low — research + replace | High | All scenarios (global fidelity lift) |

---

## Dependencies Between Improvements

```
Phase 40 ─────────────────────────────────────────────────────────────────
F0 (is_tie Bug) ──── immediate fix, no dependencies
A (Posture Wiring)  ── no dependencies
B (Fire-on-Move)    ── no dependencies
I (Domain Filtering) ── no dependencies
K (Wire Suppression) ── no dependencies
Morale enforcement ── no dependencies (values computed, just not applied)
U (Terrain Manager Instantiation) ── prerequisite for Phase 41

Phase 41 ─────────────────────────────────────────────────────────────────
C (Terrain-Combat)  ── depends on A (posture from terrain), U (managers instantiated)
E (Force Quality)   ── no dependencies
H (Target Selection) ── depends on I (domain filter informs scoring), E (quality informs threat)
R (Detection Pipeline) ── no dependencies (instantiate + wire)

Phase 42 ─────────────────────────────────────────────────────────────────
D (Hold-Fire / ROE) ── depends on B (fire discipline), H (target scoring)
F (Victory Conditions) ── depends on E (quality-weighted force ratios)
Morale-suppression feedback ── depends on K (suppression feeds morale)

Phase 43 ─────────────────────────────────────────────────────────────────
G (Aggregate Models) ── depends on C (terrain in aggregate calcs), D (hold-fire for volleys)
N (Indirect Fire Routing) ── depends on C (terrain affects indirect fire)
Q (Naval Domain Routing) ── independent (5 naval engines)

Phase 44 ─────────────────────────────────────────────────────────────────
J (Engine Integration) ── CBRN/EW/Space into battle loop
L (Weather/Night) ── weather + astronomy into engagement
M (Logistics Wiring) ── maintenance/medical/engineering into simulation loop
S (Population/Civilian) ── COIN/escalation/gray zone wiring
T (Strategic/Campaign) ── campaign-level engine routing
Command authority engine ── depends on R (detection informs command picture)

Phase 45 ─────────────────────────────────────────────────────────────────
O (Math Model Hardening) ── depends on everything above being wired
P (Constant Sourcing) ── research + replace unsourced constants

Phase 46 ─────────────────────────────────────────────────────────────────
Scenario Data Cleanup ── fix faction/unit mismatches

Phase 47 ─────────────────────────────────────────────────────────────────
Full Recalibration ── depends on all improvements above
```

**Suggested phase ordering (8 phases, Phases 40–47)**:

1. **Phase 40 — Battle Loop Foundation**: Bug fix + immediate wiring of disconnected tactical systems
   - F0: Fix `is_tie` bug in `evaluate_force_advantage()`
   - A: Wire posture into `_execute_engagements()` (target_posture from unit state)
   - B: Wire fire-on-move penalty (pass `shooter_speed_mps` from unit movement)
   - I: Add domain filtering to target selection (prevent tank guns vs aircraft)
   - K: Wire suppression engine (pass actual suppression_level, not hardcoded 0.0)
   - Wire morale multipliers into engagement accuracy (already computed, just not applied)
   - U: Instantiate terrain managers (InfrastructureManager, ObstacleManager, HydrographyManager, PopulationManager) in scenario loader — prerequisite for terrain-combat wiring in Phase 41
   - *Estimated: ~8 files modified, ~100 tests*
   - *Resolves Issues: 0, 1, 2, 6, 9, 11, 22*

2. **Phase 41 — Combat Depth**: Terrain, quality, intelligent targeting, and detection pipeline
   - C: Terrain-combat interaction (cover, concealment, elevation, mud, channeling — comprehensive). Queries `properties_at()`, `query_at()` (trenches), building cover, obstacle cover, elevation delta, ground state. Uses `max()` stacking for cover sources. All 15 LandCoverType values already have tuned cover/concealment properties.
   - E: Force quality / training level system (quality multiplier on engagement, quality-weighted force ratios)
   - H: Threat-based target selection (replace closest-enemy with weighted `score = threat × Pk × value`)
   - R: Instantiate and wire detection pipeline (IntelFusionEngine, DeceptionEngine, SonarEngine, UnderwaterDetectionEngine, IdentificationEngine). Detection quality (SNR) modulates engagement Pk — not just a binary gate.
   - Target identification confidence wiring (ID level affects ROE compliance in Phase 42)
   - *Estimated: ~12 files modified, ~120 tests*
   - *Resolves Issues: 3, 5, 8, 12, 19*

3. **Phase 42 — Tactical Behavior**: Fire discipline, victory, and morale feedback
   - D: Hold-fire / effective range / ROE engine wiring (`check_engagement_authorized()` gate before each engagement)
   - F: Victory condition improvements (combat-power-weighted, morale-based victory, phased assessment, composite time_expired adjudication)
   - Morale effects enforcement in engagement loop (SHAKEN=0.7, BROKEN=0.3 accuracy applied to Pk)
   - Suppression-morale feedback loop (sustained fire builds suppression, suppression degrades morale, morale cascade enables rout-as-victory)
   - *Estimated: ~6 files modified, ~80 tests*
   - *Resolves Issues: 4, 6 (full enforcement)*

4. **Phase 43 — Domain-Specific Resolution**: Aggregate models, indirect fire, and naval combat
   - G: Era-aware engagement routing (volley fire for Napoleonic, massed archery for Ancient, barrage for WW1). Battle loop checks `ctx.era` and dispatches to appropriate aggregate model.
   - N: Indirect fire engine routing (artillery/mortar → `IndirectFireEngine` with CEP, area effect, observer correction, fire mission delay)
   - Q: Naval domain routing (5 engines: `NavalSurfaceEngine` for surface actions, `NavalSubsurfaceEngine` for torpedo warfare, `NavalGunneryEngine` for WW1/WW2 bracket fire, `NavalGunfireSupportEngine` for shore bombardment, `MineWarfareEngine` for mine ops). Battle loop checks `EngagementType` and routes to domain-appropriate engine.
   - Formation-based casualty assessment (aggregate kills applied as fractional unit damage)
   - Simultaneous fire / volley coordination (multiple units fire together, combined effect)
   - *Estimated: ~10 files modified, ~120 tests*
   - *Resolves Issues: 7, 17, 18*

5. **Phase 44 — Full Subsystem Integration**: Wire ALL remaining disconnected engines
   - J: CBRN casualties in battle loop (query contamination grid, apply chemical/radiation exposure as damage, check MOPP level)
   - J: EW effects on detection range and guided weapon Pk (query J/S ratio, apply SNR degradation, GPS spoofing → CEP penalty)
   - J: Space/GPS effects on precision weapon CEP (query GPS DOP, degrade guided weapon accuracy)
   - L: Weather detailed effects (rain/fog/snow → Pk modifier, sea state → naval gunnery dispersion, wind → ballistic trajectory, obscurants → sector-specific detection reduction)
   - L: Night/day cycle effects (solar elevation → illumination, thermal advantage at night, NVG-equipped units benefit, illumination rounds)
   - M: Logistics engine wiring — instantiate and call per tick:
     - `MaintenanceEngine`: equipment breakdown/repair (Poisson failures)
     - `MedicalEngine`: casualty evacuation (M/M/c queue)
     - `EngineeringEngine`: obstacle creation/clearance, route improvement
     - `TransportEngine`: supply delivery routing
     - `DisruptionEngine`: supply route interdiction
     - `NavalBasingEngine` / `NavalLogisticsEngine`: naval supply ops
     - `PrisonerEngine`: prisoner handling
     - Gate combat capability by supply state (low ammo → reduced fire rate; no fuel → immobile)
   - S: Population/civilian engine wiring — instantiate and call per tick:
     - `CivilianManager`: population tracking
     - `CollateralEngine`: collateral damage assessment → feeds escalation
     - `DisplacementEngine`: refugee flow
     - `CivilianHumintEngine`: civilian intelligence
     - `InfluenceEngine`: hearts-and-minds, information ops
   - T: Strategic/campaign engine wiring — call from `CampaignManager`:
     - `AirCampaignEngine`: air campaign phase management
     - `IadsEngine`: integrated air defense
     - `StrategicBombingEngine`: strategic target destruction
     - `StrategicTargetingEngine`: deep strike planning
   - Command authority engine: instantiate `CommandEngine` (currently `None`), wire into OODA timing and unit initiative
   - *Estimated: ~20 files modified, ~150 tests*
   - *Resolves Issues: 10, 13, 14, 15, 16, 20, 21*

6. **Phase 45 — Mathematical Model Audit & Hardening**: Formula correctness and constant sourcing
   - O: Replace Gaussian blast damage with Hopkinson-Cranz overpressure scaling (conventional weapons)
     - Use same scaling approach as nuclear blast model (already correct in `cbrn/nuclear.py`)
     - Regime-dependent exponent: strong shock a≈2.65, weak shock a≈1.4
     - Apply overpressure thresholds for kill/injury/suppression
   - O: Validate morale Markov constants against military research:
     - Dupuy "Attrition" (1990) — WEI/WUV combat power methodology
     - S.L.A. Marshall "Men Against Fire" — combat participation rates
     - NATO STANAG on combat stress
     - Derive casualty_weight, suppression_weight, leadership_weight from literature
   - O: Consider Weibull distribution for maintenance (shape parameter captures bathtub curve)
     - k < 1: infant mortality, k = 1: exponential (current), k > 1: wear-out
     - Military equipment typically k = 1.2–1.8
   - O: Review hit probability modifier chain independence assumption
     - Evaluate conditional probability formulation vs multiplicative
     - Ensure modifiers don't compound to unrealistic Pk in moderate conditions
   - O: Replace linear A* threat cost with exponential
   - P: Source the 10 critical unsourced constant groups:
     1. Armor effectiveness matrix (DeMarre interaction table)
     2. Posture blast/frag protection values
     3. Morale weights (casualty, suppression, leadership, cohesion)
     4. Assessment weights (force_ratio, terrain, supply, morale, intel)
     5. Torpedo evasion/countermeasure probabilities
     6. Naval bracket convergence and base Pk per shell
     7. Maintenance MTBF (MIL-HDBK-217F)
     8. Desperation index weights (escalation model)
     9. Sonar convergence zone depths (oceanographic data)
     10. Detection uncertainty percentages
   - P: Move ~30 assessment thresholds and ~40 weights to pydantic config models (YAML-tunable)
   - P: Add source citations as code comments for all military/physics constants
   - *Estimated: ~15 files modified, ~60 tests (mostly validation)*
   - *Resolves: All low-fidelity model concerns from Mathematical Model Audit*

7. **Phase 46 — Scenario Data Cleanup & Expansion**: Fix faction/unit mismatches
   - Fix Bekaa Valley / Gulf War EW red SAM (Patriot → SA-6 Gainful)
   - Fix Falklands San Carlos red aircraft (MiG-29A → appropriate era/faction type)
   - Fix Cannae Carthaginian infantry (roman_legionary_cohort → Carthaginian infantry)
   - Fix Halabja civilian units (us_rifle_squad → civilian population entity)
   - Fix Eastern Front 1943 era/unit mismatch (modern era → WW2 era, US units → Soviet/German)
   - Create era/faction-appropriate infantry for scenarios using `us_rifle_squad` as universal proxy
   - Create missing adversary units (SA-6 Gainful, A-4 Skyhawk, Carthaginian infantry, etc.)
   - *Estimated: ~20 YAML files, ~5–10 new unit definitions, ~30 tests*

8. **Phase 47 — Full Recalibration & Validation**: Systematic calibration against history
   - Run all 42 scenarios with fully wired and hardened engine
   - Compare each historical scenario against documented outcome
   - Calibrate per-scenario YAML overrides where needed (terrain features, force quality, engagement rules)
   - Establish Monte Carlo confidence intervals (N=100 per scenario)
   - Document calibration rationale for each scenario
   - Create regression test: "all 16 historical scenarios produce correct winner with p > 0.8"
   - Verify no regression on modern/contemporary scenarios
   - *Estimated: ~42 YAML files modified, ~50 tests*

---

## Scenario Data Issues (Separate from Engine Fixes)

These are data/YAML issues in specific scenarios that should be corrected alongside engine improvements:

| Scenario | Issue | Fix |
|----------|-------|-----|
| Bekaa Valley | Red uses `patriot` (US SAM) instead of SA-6 Gainful (Soviet) | Create `sa6_gainful` unit or rename |
| Gulf War EW | Same Patriot-as-adversary-SAM issue | Same fix |
| Falklands San Carlos | Red includes `mig29a` (Soviet 1983+) — Falklands 1982 used A-4 Skyhawk | Use `a4_skyhawk` or existing attack aircraft |
| Cannae | Carthaginian infantry uses `roman_legionary_cohort` (wrong faction) | Create Carthaginian infantry type |
| Halabja 1988 | Blue "Kurdish civilians" are `us_rifle_squad` with military weapons | Create civilian unit type or restructure scenario |
| Eastern Front 1943 | Labeled "modern" era, both sides use `us_rifle_squad` and `m3a2_bradley` | Should use WW2 units |
| Many scenarios | `us_rifle_squad` used as universal infantry proxy | Create era/faction-appropriate infantry |

---

## Summary Statistics

| Category | Count | Details |
|----------|-------|---------|
| Historical scenarios analyzed | 16 | 4 ancient, 3 Napoleonic, 3 WW1, 4 WW2, 9 modern |
| Wrong winner | 6 | Agincourt, Salamis, Trafalgar, Midway, Stalingrad, Golan |
| Wrong-direction draw | 4 | Austerlitz, Waterloo, Cambrai, Somme |
| Correct but mislabeled | 8+ | is_tie bug: 73 Easting, Bekaa, Falklands ×4, etc. |
| Contemporary scenarios | 13 | Korean, Suwalki, Taiwan, COIN, Gray Zone, CBRN ×2, Space ×3, etc. |
| Test scenarios | 5 | Basic functional, some affected by is_tie bug |
| Systemic issues identified | 22 | 0: is_tie bug, 1–10: engine gaps, 11–17: additional tactical, 18–22: domain/pipeline |
| Disconnected systems found | ~40 | Tactical (posture, fire-on-move, terrain, ROE, morale, suppression, ID), domain (5 naval, 4 detection, 5 population, 4 strategic/campaign), infrastructure (7 logistics, 4 terrain managers, command), environmental (weather, night/day) |
| Math models audited | 20 | 5 high-fidelity, 8 medium, 5 low/medium needing hardening |
| Hardcoded constants found | ~180 | ~25 physics (well-sourced), ~155 tuning/empirical (many unsourced) |
| Constants needing sourcing | 10 | Armor table, morale weights, MTBF, posture protection, detection uncertainties, etc. |
| Proposed improvements | 23 | A–U plus scenario data cleanup and full recalibration |
| Estimated phases | 8 | Phases 40–47 |
| Estimated total new tests | ~660 | Across all 8 phases |

---

## Reference: Key Engine Files

### Core Battle Loop
| File | Relevant Mechanics | Gaps |
|------|-------------------|------|
| `simulation/battle.py` | Engagement loop, movement, standoff | Posture not passed, speed not passed, suppression=0.0, no terrain query, no morale enforcement, no ROE check, no ID check, no weather detail, no night/day |
| `simulation/victory.py` | Victory evaluation, force advantage | is_tie bug, raw unit count not quality-weighted |
| `simulation/engine.py` | Master tick loop, engine orchestration | Logistics engines not called (except consumption) |

### Combat Resolution
| File | Relevant Mechanics | Gaps |
|------|-------------------|------|
| `combat/engagement.py` | Hit resolution, damage routing, fire rate | No terrain cover modifier input |
| `combat/hit_probability.py` | Phit formula, posture mods, shooter speed | Modifiers multiplicative without theoretical basis |
| `combat/damage.py` | DeMarre penetration, blast/frag | Armor table unsourced, blast uses Gaussian not overpressure |
| `combat/ballistics.py` | RK4 trajectory, Mach drag, Coriolis | HIGH FIDELITY — no gaps |
| `combat/suppression.py` | Full suppression engine (5 levels) | Never called — hardcoded to 0.0 in battle.py |
| `combat/indirect_fire.py` | Artillery/mortar indirect fire | Never routed from _execute_engagements() |
| `combat/directed_energy.py` | Beer-Lambert laser, HPM | Extinction wavelength-independent |

### Era-Specific (Built but Unwired)
| File | Relevant Mechanics | Gaps |
|------|-------------------|------|
| `combat/volley_fire.py` | Napoleonic aggregate fire model | Never called from battle loop |
| `combat/archery.py` | Ancient/Medieval aggregate archery | Never called from battle loop |
| `combat/naval_gunnery.py` | WW2 bracket convergence | Bracket/Pk constants unsourced |
| `combat/naval_subsurface.py` | Torpedo warfare, evasion | Evasion probabilities unsourced |
| `movement/cavalry.py` | Charge phases, terrain effects | Terrain effects exist but combat impact not wired |

### Detection & Intelligence
| File | Relevant Mechanics | Gaps |
|------|-------------------|------|
| `detection/detection.py` | Unified SNR + erfc(Pd) | HIGH FIDELITY — detection range not coupled to engagement range |
| `detection/sonar.py` | Sonar equation | Convergence zones hardcoded (55/110km) |
| `detection/deception.py` | Decoy effectiveness | Several tuning constants |

### C2 & Decision
| File | Relevant Mechanics | Gaps |
|------|-------------------|------|
| `c2/roe.py` | Full ROE engine (HOLD/TIGHT/FREE) | Never called from battle loop |
| `c2/command.py` | Command authority, hierarchy | Set to None in scenario loader |
| `c2/ai/assessment.py` | ~30 threshold constants, ~10 weight constants | All unsourced tuning parameters |

### Morale
| File | Relevant Mechanics | Gaps |
|------|-------------------|------|
| `morale/state.py` | 5-state Markov, accuracy/speed multipliers | Multipliers not applied in engagement; ALL constants unsourced |

### Terrain & Environment
| File | Relevant Mechanics | Gaps |
|------|-------------------|------|
| `terrain/classification.py` | cover (0–0.8), concealment (0–0.9), 15 LandCover types | Never queried in combat |
| `terrain/trenches.py` | cover_value (0.50–0.85), 4 trench types | Never queried in combat |
| `terrain/infrastructure.py` | Building cover_value, polygon footprint | Never queried in combat |
| `terrain/obstacles.py` | 10 obstacle types, STRtree spatial queries | Only movement blocking, not combat cover |
| `terrain/heightmap.py` | Elevation, slope, aspect | Only LOS, not combat advantage |
| `environment/conditions.py` | GroundState (DRY–SATURATED), trafficability | Only movement, not combat |
| `environment/weather.py` | 8-state Markov, wind OU process | Only visibility_m extracted |
| `environment/astronomy.py` | Solar/lunar position, illumination | Never affects combat |
| `environment/seasons.py` | mud_depth, snow_depth, seasonal transitions | Never affects combat |

### Logistics (Built but Mostly Silent)
| File | Relevant Mechanics | Gaps |
|------|-------------------|------|
| `logistics/consumption.py` | Supply consumption per tick | ONLY engine called from battle loop |
| `logistics/maintenance.py` | Poisson breakdown, repair time | Never called; exponential model (no Weibull) |
| `logistics/medical.py` | M/M/c queue evacuation | Never called |
| `logistics/engineering.py` | Route improvement, obstacle creation | Never called |
| `logistics/transport.py` | Supply transport routing | Never called |
| `logistics/disruption.py` | Supply route interdiction | Never called |

### Domain Engines (Wired at Campaign Level, Not Tactical)
| File | Relevant Mechanics | Gaps |
|------|-------------------|------|
| `cbrn/dispersal.py` | Pasquill-Gifford puff model | Doesn't apply casualties in battle loop |
| `cbrn/nuclear.py` | Hopkinson-Cranz blast, thermal, radiation | Effects not applied as damage in engagement |
| `ew/jamming.py` | J/S ratio, burn-through range | SNR degradation not applied in engagement |
| `space/gps.py` | DOP, CEP degradation | GPS state doesn't affect guided weapon Pk |

### Entities & Movement
| File | Relevant Mechanics | Gaps |
|------|-------------------|------|
| `entities/unit_classes/ground.py` | Posture enum, dug_in_time, training | Posture never read in engagement |
| `entities/base.py` | UnitDomain enum, UnitStatus | Domain never checked in target selection |
| `movement/engine.py` | Terrain-modified speed | Only movement, not combat |
| `movement/pathfinding.py` | A* with terrain cost | Threat cost linear (should be exponential) |
