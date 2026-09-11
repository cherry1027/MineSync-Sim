from dataclasses import replace
import pytest
from model import *

def test_repeatability_and_paired_initial_conditions():
    config=Scenario()
    starts=[MineModel(config,s).rows() for s in STRATEGIES]
    assert starts[0]==starts[1]==starts[2]
    a=compare(config,100); b=compare(config,100)
    for s in STRATEGIES:
        assert a[s].history==b[s].history
        assert a[s].rows()==b[s].rows()

@pytest.mark.parametrize('strategy',STRATEGIES)
def test_safety_and_kpi_bounds(strategy):
    m=MineModel(Scenario(vehicles=36,message_loss=.4,stall_probability=.01,blocked_zone=True),strategy)
    for _ in range(180):
        before={v.index:v.position for v in m.fleet}
        m.step()
        assert len(set(v.position for v in m.fleet))==len(m.fleet)
        assert all(v.position in ROADS and v.position not in RESTRICTED for v in m.fleet)
        assert all(v.position not in m.blocked_cells() for v in m.fleet if v.position!=before[v.index])
        assert 0<=m.metrics()['resource_utilisation_pct']<=100
    assert m.trips>=0

def test_road_connectivity_and_productivity():
    m=MineModel(Scenario(vehicles=3,autonomous=1,delay=0))
    assert all(m.path(start,goal) for start in ROADS for goal in STATIONS if start!=goal)
    m.run(300)
    assert m.trips>0 and m.tonnes>0
    assert m.metrics()['productivity_t_h']==m.tonnes*720/300

def test_missing_message_fallback():
    config=Scenario(vehicles=3,autonomous=1,message_loss=1)
    frozen=MineModel(replace(config,fallback=False),STRATEGIES[1]).run(40)
    active=MineModel(config,STRATEGIES[1]).run(40)
    assert frozen.message_received==0
    assert all(v.wait_time==40 for v in frozen.fleet)
    assert any(v.wait_time<40 for v in active.fleet)

def test_blocked_route_is_safe():
    m=MineModel(Scenario(blocked=tuple(INTERSECTIONS))).run(30)
    assert all(v.position not in INTERSECTIONS for v in m.fleet)

def test_explicit_deadlock_recovery():
    m=MineModel(Scenario(vehicles=3,autonomous=1,manual_encounters=False))
    # Inject a stable cyclic wait-for graph to isolate detection and tow logic.
    for v,p in zip(m.fleet,[(2,3),(2,4),(2,5)]): v.position=p; v.destination=(18,11)
    targets={(2,3):(2,4),(2,4):(2,5),(2,5):(2,3)}
    m.path=lambda start,goal:[targets[start]] if start in targets else [(2,6)]
    m.run(6)
    assert m.deadlocks==1
    assert any(e['type']=='Tow' for e in m.events)
    assert len(set(v.position for v in m.fleet))==3
