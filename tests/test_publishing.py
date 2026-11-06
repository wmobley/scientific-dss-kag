"""No network: verify publication gates and immediate Dashboard addition."""
import importlib.util
from pathlib import Path
import sys
import pytest


def module():
    spec=importlib.util.spec_from_file_location('publish_planning',Path(__file__).parents[1]/'scripts/publish_planning.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod


def test_dry_run_has_no_external_calls(monkeypatch,capsys):
    mod=module()
    monkeypatch.setattr(sys,'argv',['publish','--repo','wmobley/scientific-dss-kag'])
    monkeypatch.setattr(mod,'gh',lambda *args:pytest.fail('dry-run called GitHub'))
    mod.main()
    assert 'wmobley/scientific-dss-kag' in capsys.readouterr().out


def test_each_issue_is_immediately_added_and_resume_deduplicates(monkeypatch,tmp_path):
    mod=module();calls=[]
    monkeypatch.setattr(mod,'STATE',tmp_path/'published.json')
    monkeypatch.setattr(sys,'argv',['publish','--repo','wmobley/scientific-dss-kag','--apply'])
    def gh(*args):
        calls.append(args)
        if args==('api','user'):return {'login':'wmobley'}
        if args[0:2]==('repo','view'):return {'nameWithOwner':'wmobley/scientific-dss-kag','visibility':'PUBLIC'}
        if args[0:2]==('project','view'):return {'title':'Research Dashboard'}
        if args[0:2]==('project','item-add'):return {'id':'item'}
        if args[0]=='api' and '?' in args[1]:return []
        if args[1].endswith('/milestones'):return {'number':1}
        if args[1].endswith('/issues'):return {'number':len(calls),'html_url':'https://github.com/wmobley/scientific-dss-kag/issues/'+str(len(calls))}
        pytest.fail(str(args))
    monkeypatch.setattr(mod,'gh',gh)
    mod.main()
    creates=[i for i,args in enumerate(calls) if args[0]=='api' and args[1].endswith('/issues')]
    assert len(creates)==9
    assert all(calls[i+1][0:2]==('project','item-add') for i in creates)
    calls.clear();mod.main()
    assert not any(a[0]=='api' and a[1].endswith('/issues') for a in calls)
