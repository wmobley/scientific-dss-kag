#!/usr/bin/env python3
"""Publish reviewed planning artifacts into the explicitly selected repository.

Dry-run by default. Invoke only with authorization for external writes. Saves
issue IDs before immediate Dashboard addition and stops on any failure.
"""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "planning/published.json"


def gh(*args):
    result = subprocess.run(["gh", *args], check=True, capture_output=True, text=True)
    return json.loads(result.stdout) if result.stdout.strip() else None


def save(state):
    temp = STATE.with_suffix('.tmp')
    temp.write_text(json.dumps(state, indent=2)+"\n")
    temp.replace(STATE)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--repo', required=True, choices=['wmobley/scientific-dss-kag'])
    parser.add_argument('--apply', action='store_true')
    args=parser.parse_args()
    milestones=json.loads((ROOT/'planning/milestones.json').read_text())
    issues=json.loads((ROOT/'planning/issues.json').read_text())
    if not args.apply:
        print(json.dumps({'repository':args.repo,'visibility':'public','milestones':milestones,'issues':issues,'dashboard':'wmobley project 5'},indent=2))
        return
    if gh('api','user')['login'] != 'wmobley':
        raise RuntimeError('Refusing different GitHub identity')
    meta=gh('repo','view',args.repo,'--json','nameWithOwner,visibility')
    if meta['nameWithOwner'] != args.repo or meta['visibility'] != 'PUBLIC':
        raise RuntimeError('Repository identity/visibility mismatch')
    project=gh('project','view','5','--owner','wmobley','--format','json')
    if project['title'] != 'Research Dashboard':
        raise RuntimeError('Dashboard identity mismatch')
    state=json.loads(STATE.read_text()) if STATE.exists() else {'repo':args.repo,'milestones':{},'issues':{}}
    if state['repo'] != args.repo: raise RuntimeError('State destination mismatch')
    existing=gh('api',f'repos/{args.repo}/milestones?state=all&per_page=100')
    for milestone in milestones:
        title=milestone['title']
        matching=next((m for m in existing if m['title']==title),None)
        if not matching:
            matching=gh('api',f'repos/{args.repo}/milestones','-f',f'title={title}','-f',f'description={milestone["description"]}')
        state['milestones'][title]=matching['number'];save(state)
    for issue in issues:
        key=issue['key']
        if key not in state['issues']:
            # Stable marker permits recovery if process failed before saving state.
            marker=f'<!-- scientific-dss-plan:{key} -->'
            existing_issues=gh('api',f'repos/{args.repo}/issues?state=all&per_page=100')
            found=next((x for x in existing_issues if marker in (x.get('body') or '')),None)
            if not found:
                found=gh('api',f'repos/{args.repo}/issues','-f',f'title={issue["title"]}','-f',f'body={issue["body"]}\n\n{marker}','-F',f'milestone={state["milestones"][issue["milestone"]]}')
            state['issues'][key]={'number':found['number'],'url':found['html_url'],'dashboard_added':False};save(state)
        row=state['issues'][key]
        if not row['dashboard_added']:
            # Required immediately after each creation; never background this.
            gh('project','item-add','5','--owner','wmobley','--url',row['url'],'--format','json')
            row['dashboard_added']=True;save(state)
        print(row['url'])


if __name__=='__main__': main()
