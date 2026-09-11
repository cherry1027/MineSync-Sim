"""Seeded synthetic traffic experiment. One tick = 5 seconds; one cell = 20 m."""
from dataclasses import dataclass, asdict, replace
from collections import deque, defaultdict
import hashlib
import random
import statistics
import mesa

STRATEGIES = ('Local priority', 'Central traffic management', 'Broker / mediator')
INTERSECTIONS = {(x,y) for x in (2,10,18) for y in (2,8,14)}
STATIONS = {(2,5):'Loading 01', (18,11):'Loading 02', (6,14):'Unloading 01', (14,2):'Unloading 02'}
LOADS = tuple(p for p,n in STATIONS.items() if n.startswith('Loading'))
DUMPS = tuple(p for p,n in STATIONS.items() if n.startswith('Unloading'))
ROADS = {(x,y) for x in range(2,19) for y in range(2,15) if x in (2,10,18) or y in (2,8,14)}
RESTRICTED = {(x,y) for x in range(12,16) for y in range(10,13)}

@dataclass(frozen=True)
class Scenario:
    seed: int = 42
    vehicles: int = 18
    autonomous: float = .75
    delay: int = 1
    quality: float = .95
    priority_rule: str = 'Loaded first'
    blocked: tuple = ()
    message_loss: float = 0.
    stall_probability: float = 0.
    blocked_zone: bool = False
    manual_encounters: bool = True
    fallback: bool = True
    def __post_init__(self):
        if not 1 <= self.vehicles <= 60: raise ValueError('Vehicle count must be 1–60')
        if not 0 <= self.delay <= 10: raise ValueError('Delay must be 0–10 ticks')
        if any(not 0 <= x <= 1 for x in (self.autonomous,self.quality,self.message_loss,self.stall_probability)):
            raise ValueError('Probabilities must be between zero and one')
        if not set(self.blocked) <= INTERSECTIONS: raise ValueError('Invalid blocked intersection')
    def identity(self):
        return hashlib.sha256(repr(asdict(self)).encode()).hexdigest()[:10]

class Vehicle(mesa.Agent):
    def __init__(self, model, index, position):
        super().__init__(model)
        self.index = index
        self.label = f'V{index+1:02}'
        self.position = position
        self.supplier = 'ABC'[index % 3]
        self.autonomy_type = 'Autonomous' if index < round(model.config.vehicles*model.config.autonomous) else 'Manual'
        self.kind = 'LHD' if index % 5 == 0 else 'Haul truck' if self.autonomy_type == 'Autonomous' else 'Manual vehicle'
        self.destination = LOADS[index % 2]
        self.intention = 'Travel to loading point'
        self.priority = 1
        self.current_state = 'Ready'
        self.wait_time = 0
        self.consecutive_wait = 0
        self.route = []
        self.loaded = False
        self.service = 0
        self.stalled_until = 0
        self.trips = 0
        self.messages = None
        self.last_seen = None

class MineModel(mesa.Model):
    def __init__(self, config=Scenario(), strategy=STRATEGIES[0]):
        super().__init__(seed=config.seed)
        if strategy not in STRATEGIES: raise ValueError(strategy)
        self.config, self.strategy = config, strategy
        self.tick = 0
        self.fleet = []
        self.history, self.events = [], []
        self.pending = defaultdict(list)
        self.conflicts = self.deadlocks = self.tonnes = self.trips = 0
        self.resource_ticks = 0
        self.recovery_times = []
        self.deadlock_active = False
        self.deadlock_start = None
        self.no_progress = 0
        self.message_sent = self.message_received = 0
        positions = sorted(ROADS - set(config.blocked) - set(STATIONS))
        self.random.shuffle(positions)
        for i in range(config.vehicles): self.fleet.append(Vehicle(self,i,positions[i]))
        self.collect()
    def noise(self, vehicle, channel):
        # Keyed exogenous random streams: unrelated strategy decisions never shift draws.
        seed = f'{self.config.seed}:{self.tick}:{vehicle.index}:{channel}'
        return random.Random(seed).random()
    def blocked_cells(self):
        return set(self.config.blocked) | ({(10,y) for y in range(9,14)} if self.config.blocked_zone and 40 <= self.tick < 100 else set())
    def neighbors(self,p):
        x,y=p
        # Directional mine lanes; junctions permit turns. No reverse/head-on moves.
        candidates=[]
        if y in (2,8,14): candidates.append((x+(1 if y in (2,8) else -1),y))
        if x in (2,10,18): candidates.append((x,y+(1 if x in (10,18) else -1)))
        return [q for q in candidates if q in ROADS and q not in self.blocked_cells()]
    def path(self,start,goal):
        queue=deque([(start,[])])
        seen={start}
        while queue:
            p,route=queue.popleft()
            if p==goal: return route
            for q in self.neighbors(p):
                if q not in seen: seen.add(q); queue.append((q,route+[q]))
        return []
    def rank(self,v):
        rule=self.config.priority_rule
        base = 3 if (rule=='Loaded first' and v.loaded) or (rule=='Manual first' and v.autonomy_type=='Manual') else 1
        v.priority=base
        if self.strategy==STRATEGIES[0]: return (base, -v.index)
        if self.strategy==STRATEGIES[1]: return (v.consecutive_wait,base,-len(v.route),-v.index)
        # Supplier-neutral age-weighted bid with round-robin supplier tie break.
        return (base+v.consecutive_wait/4, (self.tick-v.index%3)%3,-v.index)
    def event(self,kind,detail): self.events.append(dict(tick=self.tick,type=kind,detail=detail))
    def step(self):
        self.tick+=1
        blocked=self.blocked_cells()
        occupied={v.position:v for v in self.fleet}
        intents={}
        working=0
        for v in self.fleet:
            self.rank(v)
            if self.tick < v.stalled_until:
                v.current_state='Stalled'; continue
            if v.stalled_until and self.tick==v.stalled_until:
                self.recovery_times.append(self.tick-v.stalled_until+v.stall_duration)
                self.event('Recovery',f'{v.label} returned after {v.stall_duration} ticks')
            if self.noise(v,'stall') < self.config.stall_probability:
                v.stall_duration=8 if self.config.fallback else 30
                v.stalled_until=self.tick+v.stall_duration
                v.current_state='Stalled'; self.event('Stall',v.label); continue
            if v.service:
                v.service-=1; working+=1; v.current_state='Loading' if not v.loaded else 'Unloading'
                if v.service==0:
                    if v.loaded:
                        self.trips+=1; v.trips+=1; self.tonnes+=12 if v.kind=='LHD' else 40
                    v.loaded=not v.loaded
                    targets=DUMPS if v.loaded else LOADS
                    v.destination=targets[(v.index+v.trips)%len(targets)]
                    v.intention='Deliver payload' if v.loaded else 'Travel to loading point'
                continue
            if v.position==v.destination:
                v.service=3 if not v.loaded else 2
                v.current_state='Loading' if not v.loaded else 'Unloading'; working+=1; continue
            v.route=self.path(v.position,v.destination)
            if not v.route:
                v.current_state='No route'; v.wait_time+=1; v.consecutive_wait+=1; continue
            target=v.route[0]
            intents[v.index]=target
            self.message_sent+=1
            if self.noise(v,'loss')>=self.config.message_loss and self.noise(v,'quality')<self.config.quality:
                packet=dict(position=v.position,target=target,tick=self.tick,supplier=v.supplier)
                self.pending[self.tick+self.config.delay].append((v.index,packet))
        for idx,packet in self.pending.pop(self.tick,[]):
            self.fleet[idx].messages=packet; self.fleet[idx].last_seen=packet['tick']; self.message_received+=1
        requests=defaultdict(list)
        for v in self.fleet:
            if v.index not in intents: continue
            target=intents[v.index]
            fresh=v.messages is not None and self.tick-v.last_seen<=self.config.delay+2
            if self.strategy!=STRATEGIES[0] and not fresh and not self.config.fallback:
                v.current_state='Awaiting message'; continue
            if self.config.manual_encounters and v.autonomy_type=='Autonomous' and any(o.autonomy_type=='Manual' and abs(o.position[0]-target[0])+abs(o.position[1]-target[1])<=1 for o in self.fleet):
                if self.tick%3!=0: v.current_state='Yielding to manual'; continue
            if v.autonomy_type=='Manual' and self.noise(v,'manual_speed')<.25:
                v.current_state='Manual hesitation'; continue
            # Central reservations use delayed reported intent. Broker translates and
            # locally reconciles supplier packets; missing packets use local fallback.
            if self.strategy==STRATEGIES[1] and fresh and v.messages['target']!=target:
                v.current_state='Reservation pending'; continue
            if self.strategy==STRATEGIES[2] and not fresh and self.config.fallback:
                v.current_state='Local fallback'
            requests[target].append(v)
        winners={}
        for target,group in requests.items():
            if len(group)>1: self.conflicts+=len(group)-1
            winners[max(group,key=self.rank).index]=target
        # Conservative local safety interlock: occupied cells cannot be entered,
        # even if vacated this tick. All policies share identical collision guard.
        moved=0
        for v in self.fleet:
            if v.index not in intents: continue
            target=winners.get(v.index)
            if target is not None and target not in occupied and target not in blocked:
                v.position=target; v.route=v.route[1:]; v.current_state='Moving'; v.consecutive_wait=0; moved+=1
            else:
                v.wait_time+=1; v.consecutive_wait+=1
                if v.current_state not in ('Awaiting message','Yielding to manual','Manual hesitation','Reservation pending'):
                    v.current_state='Queued'
        self.resource_ticks+=working
        # Detect cycles in the wait-for graph, not normal loading or radio waits.
        graph={v.index:occupied[intents[v.index]].index for v in self.fleet if v.index in intents and intents[v.index] in occupied}
        cycle=set()
        for start in graph:
            trail=[]; node=start
            while node in graph and node not in trail: trail.append(node); node=graph[node]
            if node in trail: cycle.update(trail[trail.index(node):])
        self.no_progress=self.no_progress+1 if cycle else 0
        if self.no_progress>=6 and not self.deadlock_active:
            self.deadlocks+=1; self.deadlock_active=True; self.deadlock_start=self.tick; self.event('Deadlock','Persistent cyclic occupancy wait')
        if self.deadlock_active and self.config.fallback and cycle:
            victim=max((self.fleet[i] for i in cycle),key=lambda v:v.consecutive_wait)
            free=sorted(ROADS-{v.position for v in self.fleet}-blocked-set(STATIONS))
            if free:
                # Explicit synthetic tow relocation, never disguised as normal motion.
                victim.position=min(free,key=lambda p:(abs(p[0]-victim.position[0])+abs(p[1]-victim.position[1]),p))
                victim.current_state='Recovery tow'; self.event('Tow',f'{victim.label} relocated to free road cell')
        if self.deadlock_active and not cycle:
            self.recovery_times.append(self.tick-self.deadlock_start); self.deadlock_active=False
        self.collect()
    def metrics(self):
        elapsed=max(1,self.tick)
        return {'tick':self.tick,'productivity_t_h':self.tonnes*720/elapsed,
                'average_wait_s':sum(v.wait_time for v in self.fleet)*5/len(self.fleet),
                'throughput_trips_h':self.trips*720/elapsed,
                'queue_length':sum(v.current_state in ('Queued','Awaiting message','No route','Reservation pending','Yielding to manual','Manual hesitation') for v in self.fleet),
                'resource_utilisation_pct':100*self.resource_ticks/(elapsed*len(STATIONS)),
                'conflicts':self.conflicts,'deadlocks':self.deadlocks,
                'recovery_time_s':statistics.mean(self.recovery_times)*5 if self.recovery_times else None,
                'completed_trips':self.trips,'tonnes':self.tonnes,
                'unresolved_stalls':sum(self.tick<v.stalled_until for v in self.fleet),
                'unresolved_deadlock':int(self.deadlock_active)}
    def collect(self): self.history.append(self.metrics())
    def rows(self):
        return [dict(vehicle=v.label,position=str(v.position),supplier=v.supplier,autonomy=v.autonomy_type,
                     kind=v.kind,destination=STATIONS[v.destination],intention=v.intention,priority=v.priority,
                     state=v.current_state,wait_s=v.wait_time*5,route=str(v.route),message_age=None if v.last_seen is None else self.tick-v.last_seen) for v in self.fleet]
    def run(self,ticks):
        for _ in range(ticks): self.step()
        return self

def compare(config,ticks=300):
    return {strategy:MineModel(config,strategy).run(ticks) for strategy in STRATEGIES}
