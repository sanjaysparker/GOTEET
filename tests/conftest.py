"""Never let a test touch the real workspace: point WORKMATE_HOME at a throwaway dir before modules import DATA."""
import os,tempfile
os.environ['WORKMATE_HOME']=tempfile.mkdtemp(prefix='goteet-tests-')

import json
import pytest

@pytest.fixture
def isolated(tmp_path,monkeypatch):
    """Fresh DATA dir for every module that reads it; mirrors test_workmate.workspace."""
    import api,collector,engine,settings,google_auth
    data=tmp_path/'data';data.mkdir()
    for module in (engine,collector,api,settings,google_auth):monkeypatch.setattr(module,'DATA',data)
    monkeypatch.setattr(engine,'STATE',tmp_path);monkeypatch.setattr(api,'STATE',tmp_path)
    (data/'inventory.json').write_text(json.dumps({'github':[],'local':{'repos':[],'files':[]},'captured_at':'2026-10-21T09:00:00+05:30'}))
    (data/'workspace.json').write_text(json.dumps({'followups':[]}))
    return data
