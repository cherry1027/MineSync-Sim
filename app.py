import json
from dataclasses import asdict, replace
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from model import Scenario, MineModel, STRATEGIES, INTERSECTIONS, STATIONS, ROADS, RESTRICTED, compare

st.set_page_config(page_title='MineSync Sim', page_icon='⬡', layout='wide')
st.markdown('''<style>
.block-container{padding-top:4rem;max-width:1600px}h1{font-weight:750;letter-spacing:-1.5px}h2,h3{letter-spacing:-.5px}
[data-testid="stMetric"]{background:#19242f;border:1px solid #2c3a46;border-radius:8px;padding:15px}
[data-testid="stMetricLabel"]{color:#aabbc9}.eyebrow{color:#f4b942;font-size:13px;font-weight:700;letter-spacing:2px}
.arch{padding:18px;background:#19242f;border-left:3px solid #f4b942;border-radius:4px;color:#c4d1df;line-height:1.8}
.notice{font-size:14px;color:#b6c5d2;border-top:1px solid #314151;padding-top:14px;margin-top:25px}
</style>''',unsafe_allow_html=True)

VIEWS=['Scenario Builder','Live Simulation','Coordination Comparison','Situational Awareness','Robustness Lab','KPI & Sensitivity Dashboard']
COLORS={'A':'#f4b942','B':'#4fc7ce','C':'#a78bfa'}
if 'config' not in st.session_state: st.session_state.config=Scenario()
cfg=st.session_state.config
with st.sidebar:
    st.markdown('### ⬡ MineSync Sim')
    st.caption('COLLABORATIVE MINING • RESEARCH LAB')
    view=st.radio('Workspace',VIEWS,label_visibility='collapsed')
    st.divider()
    st.markdown('**Active scenario**')
    st.caption(f'Seed {cfg.seed} · {cfg.vehicles} vehicles · {round(cfg.autonomous*100)}% autonomous')
    st.caption(f'Fingerprint `{cfg.identity()}`')
    st.markdown('**Simulation clock**')
    st.caption('1 tick = 5 s · 1 cell = 20 m')
    st.caption('Synthetic research demonstrator — not RISE/CAVE operational data.')
st.markdown('<div class="eyebrow">AUTONOMOUS OPERATION ZONE / MINESYNC</div>',unsafe_allow_html=True)
st.title(view)

def zone(model,height=470):
    fig=go.Figure()
    for y in (2,8,14):
        fig.add_trace(go.Scatter(x=[2,18],y=[y,y],mode='lines',line=dict(color='#344757',width=18),hoverinfo='skip',showlegend=False))
    for x in (2,10,18):
        fig.add_trace(go.Scatter(x=[x,x],y=[2,14],mode='lines',line=dict(color='#344757',width=18),hoverinfo='skip',showlegend=False))
    for y in (2,8,14):
        fig.add_annotation(x=6,y=y,text='→' if y in (2,8) else '←',showarrow=False,font=dict(color='#d3dce5',size=20))
    for x in (2,10,18):
        fig.add_annotation(x=x,y=6.5,text='↑' if x!=2 else '↓',showarrow=False,font=dict(color='#d3dce5',size=20))
    fig.add_shape(type='rect',x0=11.5,x1=15.5,y0=9.5,y1=12.5,fillcolor='#653e35',line=dict(color='#d57b62',dash='dash'))
    fig.add_annotation(x=13.5,y=11,text='RESTRICTED<br>NO ENTRY',showarrow=False,font=dict(color='#edb09e',size=12))
    fig.add_trace(go.Scatter(x=[p[0] for p in sorted(INTERSECTIONS)],y=[p[1] for p in sorted(INTERSECTIONS)],mode='markers',marker=dict(size=18,symbol='square-open',color='#8597a7'),name='Intersection'))
    for p,name in STATIONS.items():
        fig.add_trace(go.Scatter(x=[p[0]],y=[p[1]],mode='markers',marker=dict(size=20,symbol='square',color='#83b989' if name.startswith('Loading') else '#769abf'),showlegend=False,hovertext=name))
        fig.add_annotation(x=p[0],y=p[1],text=name,showarrow=False,yshift=24,font=dict(size=12,color='#e7edf4'))
    for supplier in 'ABC':
        vs=[v for v in model.fleet if v.supplier==supplier]
        fig.add_trace(go.Scatter(x=[v.position[0] for v in vs],y=[v.position[1] for v in vs],mode='markers',name=f'Supplier {supplier}',marker=dict(size=13,color=COLORS[supplier],symbol=['diamond' if v.autonomy_type=='Manual' else 'circle' for v in vs],line=dict(color='#10171f',width=2)),text=[f'{v.label} · {v.kind}<br>{v.current_state}<br>{v.intention}' for v in vs],hovertemplate='%{text}<extra></extra>'))
    b=model.blocked_cells()
    if b: fig.add_trace(go.Scatter(x=[p[0] for p in b],y=[p[1] for p in b],mode='markers',marker=dict(size=22,symbol='x',color='#ef7272'),name='Blocked'))
    fig.update_layout(height=height,margin=dict(l=10,r=10,t=20,b=10),paper_bgcolor='#10171f',plot_bgcolor='#131e28',font=dict(color='#bccbd8'),legend=dict(orientation='h',y=-.05),xaxis=dict(range=[0,20],showgrid=False,zeroline=False,title='20 m grid cells'),yaxis=dict(range=[0,16],showgrid=False,zeroline=False,scaleanchor='x',scaleratio=1))
    return fig

def kpis(m):
    vals=m.metrics()
    for col,key,label,suffix in zip(st.columns(4),['productivity_t_h','average_wait_s','throughput_trips_h','queue_length'],['Productivity','Avg. cumulative wait / vehicle','Throughput','Current queue'],['t/h','s','trips/h','vehicles']):
        col.metric(label,f'{vals[key]:,.1f} {suffix}')

def export_models(models,config,ticks):
    rows=pd.DataFrame([dict(strategy=s,**m.metrics()) for s,m in models.items()])
    st.download_button('Download KPI comparison · CSV',rows.to_csv(index=False),'minesync_comparison.csv','text/csv')
    data=dict(scenario=asdict(config),fingerprint=config.identity(),ticks=ticks,engine='MineSync Sim 1.0 / Mesa 3.3.1',results={s:dict(scenario=asdict(m.config),strategy=m.strategy,kpi=m.metrics(),history=m.history,events=m.events) for s,m in models.items()})
    st.download_button('Download reproducible experiment · JSON',json.dumps(data,indent=2),'minesync_experiment.json','application/json')

@st.cache_data(show_spinner=False)
def experiment(config,ticks): return compare(config,ticks)

if view=='Scenario Builder':
    st.caption('Configure a synthetic fleet, inspect the zone, and apply a reproducible scenario.')
    left,right=st.columns([.9,1.7],gap='large')
    with left:
        with st.form('scenario'):
            st.subheader('Fleet & communications')
            seed=st.number_input('Random seed',0,999999,int(cfg.seed))
            count=st.slider('Vehicle count',3,60,cfg.vehicles)
            auto=st.slider('Autonomous share (%)',0,100,round(cfg.autonomous*100),5)
            delay=st.slider('Communication delay (ticks)',0,10,cfg.delay)
            quality=st.slider('Information quality (%)',0,100,round(cfg.quality*100),5,help='Probability a position/intent packet passes validation; rejected packets are treated as missing.')
            rules=st.selectbox('Priority rules',['Loaded first','Manual first','Equal priority'],index=['Loaded first','Manual first','Equal priority'].index(cfg.priority_rule))
            blocked=st.multiselect('Blocked intersections',sorted(INTERSECTIONS),default=list(cfg.blocked),format_func=lambda p:f'J{sorted(INTERSECTIONS).index(p)+1:02} · {p}')
            if st.form_submit_button('Apply scenario',type='primary',use_container_width=True):
                st.session_state.config=replace(cfg,seed=int(seed),vehicles=count,autonomous=auto/100,delay=delay,quality=quality/100,priority_rule=rules,blocked=tuple(blocked))
                st.session_state.pop('live',None); st.session_state.running=False; st.rerun()
    with right:
        st.subheader('Zone topology')
        st.plotly_chart(zone(MineModel(cfg)),use_container_width=True)
        st.caption('● Autonomous  ◆ Manual · A/B/C identify synthetic suppliers. All vehicles obey one-way lanes and exclusive cell occupancy.')
        st.info('Four service points · nine intersections · permanent restricted area · LHDs every fifth vehicle')
    st.subheader('System architecture')
    st.markdown('<div class="arch">Vehicles → Shared Position/Intentions → Coordination Layer → Movement Decisions → Simulation → KPI Evaluation</div>',unsafe_allow_html=True)
    with st.expander('Model assumptions & strategy definitions'):
        st.markdown('''**Local priority:** next-cell arbitration using the selected priority rule and stable vehicle-ID ties. Local sensing remains available during message loss.

**Central traffic management:** global next-cell reservations from delayed shared intentions, with longest-wait-first ordering. Stale reservations may hold a vehicle.

**Broker / mediator:** a shared packet contract normalises supplier identities and intentions; local reconciliation updates the next movement request. Age-weighted bids and rotating supplier tie breaks arbitrate access.

Each policy shares the same physical occupancy guard. The broker is a conceptual in-process mediator, not a vendor protocol implementation. Information quality is packet validity, not spatial measurement error. Manual vehicles use seeded hesitation and autonomous vehicles yield during nearby encounters.''')

elif view=='Live Simulation':
    top=st.columns([2,1,1,1,1])
    strategy=top[0].selectbox('Coordination strategy',STRATEGIES)
    if 'live' not in st.session_state or st.session_state.live.strategy!=strategy or st.session_state.live.config!=cfg:
        st.session_state.live=MineModel(cfg,strategy); st.session_state.running=False
    if top[1].button('▶ Play',use_container_width=True): st.session_state.running=True
    if top[2].button('Ⅱ Pause',use_container_width=True): st.session_state.running=False
    if top[3].button('Step +1',use_container_width=True): st.session_state.live.step()
    if top[4].button('↺ Reset',use_container_width=True): st.session_state.live=MineModel(cfg,strategy); st.session_state.running=False
    @st.fragment(run_every=1)
    def live():
        m=st.session_state.live
        if st.session_state.get('running',False): m.step()
        st.caption(f'Tick {m.tick:04} · elapsed {m.tick*5} s · {"RUNNING" if st.session_state.get("running") else "PAUSED"}')
        kpis(m)
        a,b=st.columns([2,1])
        a.plotly_chart(zone(m),use_container_width=True)
        with b:
            st.subheader('Fleet state')
            states=pd.DataFrame(m.rows()).groupby('state').size().rename('vehicles')
            st.bar_chart(states,color='#f4b942')
            st.caption(f'{m.message_received} / {m.message_sent} packets received (includes in-flight delay)')
            st.caption('Live execution advances one tick per second while this view is active.')
        st.dataframe(pd.DataFrame(m.rows()),hide_index=True,use_container_width=True)
    live()

elif view=='Coordination Comparison':
    st.caption('Identical initial fleet, seed, disturbances, and horizon. Only the coordination policy changes.')
    a,b=st.columns([3,1])
    ticks=a.slider('Experiment horizon (ticks)',60,720,300,60)
    run=b.button('Run all three strategies',type='primary',use_container_width=True)
    if run:
        with st.spinner('Running three paired experiments…'): st.session_state.comparison=(cfg,ticks,experiment(cfg,ticks))
    if 'comparison' not in st.session_state:
        st.info('Run the experiment to generate measured results for all three policies.')
        st.plotly_chart(zone(MineModel(cfg),380),use_container_width=True)
    else:
        saved,horizon,models=st.session_state.comparison
        if saved!=cfg or ticks!=horizon: st.warning('Showing a previous run. Run again to use the current scenario and horizon.')
        st.caption(f'Experiment {saved.identity()} · seed {saved.seed} · {horizon} ticks ({horizon*5} s)')
        cols=st.columns(3)
        for col,(s,m) in zip(cols,models.items()):
            with col:
                st.subheader(s)
                st.metric('Productivity',f'{m.metrics()["productivity_t_h"]:,.1f} t/h')
                st.caption(f'{m.trips} completed deliveries · {m.tonnes} synthetic tonnes')
        metric=st.selectbox('Compare measure',['productivity_t_h','average_wait_s','throughput_trips_h','queue_length','resource_utilisation_pct','conflicts','deadlocks','recovery_time_s'])
        hist=pd.concat([pd.DataFrame(m.history).assign(strategy=s) for s,m in models.items()])
        st.plotly_chart(px.line(hist,x='tick',y=metric,color='strategy',color_discrete_sequence=['#f4b942','#4fc7ce','#a78bfa']),use_container_width=True)
        st.dataframe(pd.DataFrame({s:m.metrics() for s,m in models.items()}).drop(index='tick'),use_container_width=True)
        st.caption('Recovery time is the mean of completed stall/deadlock recoveries; blank means no completed recovery. Inspect unresolved incidents alongside it.')
        export_models(models,saved,horizon)

elif view=='Situational Awareness':
    m=st.session_state.get('live',MineModel(cfg))
    st.caption(f'Shared operating picture · {m.strategy} · tick {m.tick} · scenario {m.config.identity()}')
    if m.tick==0: st.info('Advance the Live Simulation to populate received messages and event history.')
    a,b=st.columns([2,1])
    a.plotly_chart(zone(m),use_container_width=True)
    with b:
        st.subheader('Shared intention contract')
        selected=st.selectbox('Inspect vehicle',[v.label for v in m.fleet])
        v=next(v for v in m.fleet if v.label==selected)
        st.json(dict(vehicle=v.label,supplier=v.supplier,ground_truth_position=v.position,destination=v.destination,intention=v.intention,received_packet=v.messages,message_age_ticks=None if v.last_seen is None else m.tick-v.last_seen))
        st.caption('Map shows simulation ground truth. Received packets expose the coordinator’s delayed view.')
    st.dataframe(pd.DataFrame(m.rows()),hide_index=True,use_container_width=True)
    st.subheader('Event log')
    st.dataframe(pd.DataFrame(m.events,columns=['tick','type','detail']),hide_index=True,use_container_width=True)

elif view=='Robustness Lab':
    st.caption('Paired stress test: identical faults with fallback enabled and disabled.')
    a,b=st.columns([1,2])
    with a:
        loss=st.slider('Message loss (%)',0,100,20,5)
        stalls=st.slider('Stall probability / vehicle / tick (%)',0.0,5.0,.5,.1)
        blocked_zone=st.checkbox('Block central road · ticks 40–99',True)
        encounters=st.checkbox('Yield on manual encounters',True)
        strategy=st.selectbox('Coordination policy',STRATEGIES,index=2)
        ticks=st.slider('Stress horizon (ticks)',120,720,300,60)
        go_run=st.button('Run robustness experiment',type='primary')
        st.caption('Fallback uses local sensing for missing messages, an 8-tick repair instead of 30 ticks, and explicit tow recovery for cyclic deadlocks.')
    with b:
        if go_run:
            stress=replace(cfg,message_loss=loss/100,stall_probability=stalls/100,blocked_zone=blocked_zone,manual_encounters=encounters)
            with st.spinner('Replaying identical faults…'):
                models={label:MineModel(replace(stress,fallback=enabled),strategy).run(ticks) for label,enabled in [('Fallback on',True),('Fallback off',False)]}
            st.session_state.robust=(stress,ticks,strategy,models)
        if 'robust' in st.session_state:
            saved,horizon,policy,models=st.session_state.robust
            st.caption(f'Saved stress run · {policy} · {horizon} ticks · seed {saved.seed} · loss {saved.message_loss:.0%}')
            expected=replace(cfg,message_loss=loss/100,stall_probability=stalls/100,blocked_zone=blocked_zone,manual_encounters=encounters)
            if saved!=expected or ticks!=horizon or strategy!=policy: st.warning('Controls changed; run again to update results.')
            st.dataframe(pd.DataFrame({s:m.metrics() for s,m in models.items()}),use_container_width=True)
            hist=pd.concat([pd.DataFrame(m.history).assign(mode=s) for s,m in models.items()])
            st.plotly_chart(px.line(hist,x='tick',y='queue_length',color='mode',color_discrete_sequence=['#4fc7ce','#f4b942']),use_container_width=True)
            st.dataframe(pd.DataFrame([dict(mode=s,**e) for s,m in models.items() for e in m.events]),hide_index=True,use_container_width=True)
            export_models(models,saved,horizon)
        else: st.plotly_chart(zone(MineModel(replace(cfg,blocked_zone=True)),380),use_container_width=True)

else:
    st.caption('Sensitivity experiments use paired seeds across strategies at each parameter value.')
    a,b,c=st.columns(3)
    parameter=a.selectbox('Parameter',['Communication delay','Autonomous share','Vehicle count','Information quality'])
    reps=b.slider('Seed replications',2,8,3)
    ticks=c.select_slider('Horizon (ticks)',[120,240,360],value=240)
    if st.button('Run sensitivity sweep',type='primary'):
        choices={'Communication delay':('delay',[0,2,4,6]),'Autonomous share':('autonomous',[0.,.5,.75,1.]),'Vehicle count':('vehicles',[6,12,24,36]),'Information quality':('quality',[.25,.5,.75,1.])}
        field,values=choices[parameter]; rows=[]
        progress=st.progress(0)
        for i,value in enumerate(values):
            for r in range(reps):
                config=replace(cfg,**{field:value,'seed':cfg.seed+r})
                for s,m in experiment(config,ticks).items(): rows.append(dict(value=value,seed=config.seed,strategy=s,**m.metrics()))
                progress.progress((i*reps+r+1)/(len(values)*reps))
        st.session_state.sensitivity=(parameter,cfg,ticks,reps,pd.DataFrame(rows))
    if 'sensitivity' in st.session_state:
        param,saved,horizon,n,df=st.session_state.sensitivity
        st.caption(f'{param} · seeds {saved.seed}–{saved.seed+n-1} · {horizon} ticks per run')
        if (param,saved,horizon,n)!=(parameter,cfg,ticks,reps): st.warning('Showing a previous sweep; run again to apply current settings.')
        metric=st.selectbox('Response measure',['productivity_t_h','average_wait_s','throughput_trips_h','queue_length','resource_utilisation_pct','conflicts','deadlocks','recovery_time_s'])
        summary=df.groupby(['value','strategy'])[metric].agg(['mean','std']).reset_index()
        st.plotly_chart(px.line(summary,x='value',y='mean',color='strategy',error_y='std',markers=True,labels={'value':param,'mean':metric},color_discrete_sequence=['#f4b942','#4fc7ce','#a78bfa']),use_container_width=True)
        st.caption('Error bars show ±1 sample standard deviation across seeds, not confidence intervals. No optimal strategy is assumed.')
        st.dataframe(summary,hide_index=True,use_container_width=True)
        st.download_button('Download all sweep observations',df.to_csv(index=False),'minesync_sensitivity.csv','text/csv')
    with st.expander('KPI definitions',expanded=True):
        st.markdown('''| Measure | Definition |
|---|---|
| Productivity | Delivered synthetic tonnes / elapsed simulation hours |
| Average waiting time | Total non-service waiting seconds / fleet size (cumulative) |
| Throughput | Completed unloading operations / elapsed simulation hours |
| Queue length | Vehicles held by traffic, communication, hesitation or unavailable routes at that tick |
| Resource utilisation | Occupied loading/unloading station ticks / (4 × elapsed ticks) |
| Conflict count | Excess simultaneous requests for the same next cell; not collisions |
| Deadlocks | Episodes of cyclic occupancy waits persisting for 6 ticks |
| Recovery time | Mean duration of completed stall and deadlock recoveries; unresolved incidents reported separately |

Payloads are synthetic: LHD = 12 t; other vehicles = 40 t. A service point has capacity one. Loading takes 4 ticks including arrival; unloading takes 3. There is no physical acceleration, braking, fuel, or validated mine geometry. Restricted areas are outside the road graph. Vehicles inside a temporary closure may wait until it reopens at tick 100. Tow recovery is a discrete relocation logged as an event.''')
st.markdown('<div class="notice">Synthetic research demonstrator — not RISE/CAVE operational data.</div>',unsafe_allow_html=True)
