from pathlib import Path
from streamlit.testing.v1 import AppTest

def test_research_workflow():
    at=AppTest.from_file(str(Path(__file__).with_name('app.py')),default_timeout=90).run()
    assert not at.exception
    for view,action in [('Live Simulation','Step +1'),('Coordination Comparison','Run all three strategies'),('Situational Awareness',None),('Robustness Lab','Run robustness experiment'),('KPI & Sensitivity Dashboard','Run sensitivity sweep')]:
        at.sidebar.radio[0].set_value(view).run()
        assert not at.exception
        if action:
            next(b for b in at.button if b.label==action).click().run()
            assert not at.exception
    assert len(at.session_state.sensitivity[-1])==36
