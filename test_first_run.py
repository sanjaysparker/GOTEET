from pathlib import Path
from unittest.mock import patch
import settings

def test_fresh_profile_is_neutral_and_collection_opt_in(tmp_path):
    with patch.object(settings, 'DATA', tmp_path):
        value=settings.get()
        assert value['display_name']=='Local user'
        assert value['start_view']=='Connections'
        assert not any(value[k] for k in ['auto_analysis','github_enabled','local_index_enabled','activity_enabled','agent_observer_enabled'])

def test_existing_profile_and_permissions_are_preserved(tmp_path):
    with patch.object(settings, 'DATA', tmp_path):
        settings.save({'display_name':'Team member','auto_analysis':True})
        assert settings.get()['display_name']=='Team member'
        assert settings.get()['auto_analysis']

def test_missing_reference_catalog_is_an_empty_list():
    import api
    with patch.object(api.engine,'read_json',return_value={}):
        assert api.research()==[]


def test_google_imports_only_granted_sources(monkeypatch):
    import google_auth
    seen=[]
    monkeypatch.setattr(google_auth,'status',lambda:{'sources':{'gmail':True,'drive':False}})
    monkeypatch.setattr(google_auth,'sync',lambda sources:seen.extend(sources))
    google_auth.setup_sources(['gmail','drive'])
    assert seen==['gmail']
    assert google_auth.SERVICE=='in.droneos.goteet.google'


def test_legacy_keychain_transfer_is_explicit_and_preserves_current(monkeypatch):
    import google_auth
    import json
    current={'google-client':{'client_id':'current'}}
    reads=[]
    monkeypatch.setattr(google_auth,'read_secret',lambda name:current.get(name))
    monkeypatch.setattr(google_auth.keyring,'get_password',lambda service,name:(reads.append((service,name)) or json.dumps({'profile':{'sub':'legacy'}})))
    monkeypatch.setattr(google_auth,'save_secret',lambda name,value:current.update({name:value}))
    assert google_auth.migrate_legacy()=={'migrated':1}
    assert current['google-client']['client_id']=='current'
    assert reads==[('in.droneos.workmate','google-tokens')]
