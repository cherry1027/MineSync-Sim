# MineSync Sim

Synthetic research demonstrator — not RISE/CAVE operational data.

A Python/Mesa agent-based mining traffic prototype with a Streamlit dashboard. All inputs and disturbances are synthetic. The three policies are research abstractions, not vendor integrations or operational safety controllers.

## Run

Python 3.11–3.13 recommended. From this folder:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Visit http://localhost:8501. Run `python -m pytest -q` to validate the model.

## Research workflow

1. **Scenario Builder:** set and apply fleet composition, seed, delay, packet quality, priority and blocked junctions. Pending form edits do not change the active scenario.
2. **Live Simulation:** choose a policy; play, pause, step and reset. The clock advances only while this view is active. Inspect per-vehicle state and route.
3. **Coordination Comparison:** execute all policies from the same initial conditions and horizon. Inspect all eight metrics and download CSV or JSON including configuration, per-policy configuration, time series and events.
4. **Situational Awareness:** inspect the live ground-truth map alongside delayed shared packets and incident logs.
5. **Robustness Lab:** compare fallback on/off with packet loss, stalls, a timed road closure and manual encounters. This is a separate experiment; it does not alter the active scenario.
6. **KPI & Sensitivity Dashboard:** sweep four levels of a parameter across consecutive paired seeds. Error bars are sample standard deviations, not confidence intervals.

## Architecture

Vehicles → Shared Position/Intentions → Coordination Layer → Movement Decisions → Simulation → KPI Evaluation

`Vehicle` extends `mesa.Agent`; `MineModel` extends `mesa.Model`. The model explicitly stages intents, communications, arbitration and movement to avoid activation-order movement bias. `fleet` is an ordered view of Mesa-registered agents. Geometry is a discrete directed road graph; shortest paths use BFS. Only one vehicle occupies each cell. Roads have one-way rules, four capacity-one service points and nine junctions. Non-road restricted cells can never be entered.

### Policies

- **Local priority:** next-cell arbitration by selected priority, then vehicle ID. Does not depend on radio messages.
- **Central traffic management:** global next-cell reservation using delayed shared intent, longest waiting vehicle first, priority and route length ties. A stale reservation holds the vehicle until updated.
- **Broker / mediator:** common position/intent packet contract, supplier-neutral age-weighted bidding and rotating supplier tie breaks. Broker reconciles received intentions with a local movement request. Supplier A/B/C are synthetic labels under a shared schema; proprietary protocol translation is outside this prototype.

All policies use a common conservative occupancy safety interlock: even cells vacated during a tick are not entered until the next tick. Manual vehicles have 25% seeded hesitation; autonomous vehicles yield near manual vehicles on two of every three ticks when encounter handling is enabled. Every fifth vehicle is an LHD. Autonomous share is rounded to a whole number of vehicles.

### Randomness and reproducibility

Mesa's seeded RNG establishes initial placement. Fault/quality/hesitation draws use independent `Random` instances keyed by scenario seed, tick, vehicle index and channel. Policies therefore do not shift one another's random streams. Actual stall onsets can differ if a vehicle is already stalled when a keyed fault occurs. Comparisons include startup transients; there is no warm-up removal. For thesis conclusions use multiple seeds and appropriate statistical analysis rather than interpreting a single run as evidence of superiority.

### Faults and recovery

Information quality is the probability of packet validation, not coordinate noise. Packet loss and invalidity drop packets; latency delays delivery. Packets older than delay + 2 ticks are unavailable. Central/broker stop without current information if fallback is disabled; fallback permits local control. Stalls last 8 ticks with fallback repair or 30 without it. A temporary central-road closure is active on ticks 40–99; vehicles inside can be trapped until reopening. Blocked junctions are permanent for the experiment.

Deadlock detection tracks a cycle in the occupancy wait-for graph persisting for six consecutive ticks. This is a heuristic and may include an episode whose membership changes. A fallback tow explicitly relocates one affected vehicle to a nearby free road cell and logs the relocation. It is not physical driving. Unresolved deadlocks and stalls are reported separately from completed recovery durations.

### KPI definitions

One tick = 5 seconds; one cell = 20 m. Synthetic payloads: LHD 12 t, other vehicles 40 t. Loading occupies 4 ticks including arrival; unloading 3.

- Productivity: delivered tonnes / elapsed hours.
- Average waiting: cumulative non-service waiting seconds / fleet size; stalls are excluded and recorded separately.
- Throughput: completed unloading operations / elapsed hours.
- Queue: current vehicles held by traffic, missing information, hesitation or unavailable routes.
- Resource utilisation: occupied service ticks / (4 stations × elapsed ticks).
- Conflicts: excess concurrent requests for one next cell, not collisions.
- Deadlocks: detected persistent cyclic occupancy-wait episodes.
- Recovery: mean duration of completed stall/deadlock recoveries. Null when none completed; this is not zero. Tow and repair mechanisms are synthetic assumptions.

There is no acceleration, braking envelope, fuel model, real mine geometry, network stack, equipment telemetry or validated safety case. Fleet utilisation is distinct from the reported service-station utilisation. Strategies are intentionally simple and auditable.

## Files

- `model.py`: simulation, scenario contract, policy arbitration and KPI collection.
- `app.py`: six interactive views.
- `test_model.py`: deterministic replay, shared initial conditions, connectivity, safety, KPI bounds, loss fallback and deadlock recovery tests.
- `test_ui.py`: navigation and research-action smoke checks.
- `example_experiment.json`: default 300-tick paired experiment with configuration and traces.

Implementation references: [Mesa 3 migration guide](https://mesa.readthedocs.io/stable/migration_guide.html) and [Streamlit fragments](https://docs.streamlit.io/develop/concepts/architecture/fragments).
