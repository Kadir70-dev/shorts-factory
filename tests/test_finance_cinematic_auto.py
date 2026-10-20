"""F2 auto-selection tests; CPU-only, no network or generated financial facts."""
from __future__ import annotations
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.finance_cinematic_cpu.auto import select_scenes, prepare_specs, auto_apply
from tools.finance_cinematic_cpu.engine import EngineError


def _scene(scene_id, image=None, kind='ai_image', duration=4, channel='ai_broll',
           role='', data=None, overlays=None, visual_type='dramatic', evidence=None):
    v=NS(type=kind,budget_channel=channel,asset_path=str(image) if image else None,
         motion='ken_burns',layers=[],evidence_card_path=evidence,
         scene_visual_type=visual_type,visual_intent='markets skyline')
    return NS(id=scene_id,duration_sec=duration,visual=v,narration='Markets changed.',
              beat_role=role,data=data,overlays=overlays or [])


class Graph(NS):
    def model_copy(self,*,deep):
        return copy.deepcopy(self)


def _graph(*scenes):
    return Graph(width=1920,height=1080,fps=30,scenes=list(scenes))


def test_select_from_actual_ai_stills_only(tmp_path):
    img=tmp_path/'ai.png'
    Image.new('RGB',(100,80),'blue').save(img)
    g=_graph(_scene('ai',img,role='reveal'),
             _scene('chart',img,kind='dataviz'),
             _scene('official',img,channel='official'),
             _scene('moving',img,kind='ai_video'),
             _scene('missing',tmp_path/'absent.png'))
    r=select_scenes(g,max_clips=3,spacing_sec=0)
    assert [x['scene_id'] for x in r['selected']]==['ai']
    reasons={x['scene_id']:x['reason'] for x in r['skipped']}
    assert reasons['chart']=='not_an_AI_still'
    assert reasons['official']=='not_an_AI_broll_channel'
    assert reasons['moving']=='not_an_AI_still'
    assert reasons['missing']=='missing_or_unsupported_source_still'


def test_spacing_rank_and_duration_filters(tmp_path):
    img=tmp_path/'a.jpg';Image.new('RGB',(140,100),'green').save(img)
    g=_graph(_scene('s1',img,role='hook',duration=4),
             _scene('s2',img,duration=4),
             _scene('s3',img,role='reveal',duration=4),
             _scene('s4',img,duration=14),
             _scene('s5',img,role='reveal',duration=4))
    r=select_scenes(g,max_clips=2,spacing_sec=8)
    assert [x['scene_id'] for x in r['selected']]==['s1','s3']
    assert any(x['scene_id']=='s4' and x['reason']=='duration_outside_window' for x in r['skipped'])


def test_stat_source_evidence_and_data_preserved(tmp_path):
    img=tmp_path/'a.jpg';Image.new('RGB',(140,100),'green').save(img)
    good=NS(valid=lambda:True)
    g=_graph(_scene('data',img,data=good),
             _scene('overlay',img,overlays=[NS(type='stat')]),
             _scene('evidence',img,evidence='evidence.png'),
             _scene('safe',img))
    r=select_scenes(g,spacing_sec=0)
    assert [x['scene_id'] for x in r['selected']]==['safe']


def test_prepare_real_image_specs_with_correct_aspect(tmp_path):
    img=tmp_path/'a.jpg';Image.new('RGB',(320,200),'blue').save(img)
    g=_graph(_scene('s1',img))
    r=select_scenes(g)
    r['output_width']=g.width;r['output_height']=g.height
    specs=prepare_specs(r,tmp_path/'specs',width=320,fps=12)
    spec=json.loads(specs['s1'].read_text())
    assert spec['width']==320 and spec['height']==180
    assert spec['duration_sec']==4
    assert (specs['s1'].parent/'plate.jpg').is_file()


def test_dry_run_does_not_touch_files(tmp_path):
    img=tmp_path/'a.jpg';Image.new('RGB',(320,200),'blue').save(img)
    g=_graph(_scene('s1',img))
    r=select_scenes(g)
    assert r['mode']=='dry_run'
    assert len(list(tmp_path.iterdir()))==1


def test_apply_preserves_original_scenegraph(tmp_path):
    img=tmp_path/'a.jpg';Image.new('RGB',(320,200),'blue').save(img)
    g=_graph(_scene('s1',img,duration=1))
    r=select_scenes(g,min_dur=0.5)
    edited=auto_apply(g,r,tmp_path/'generated',width=320,fps=12)
    assert edited is not g
    assert g.scenes[0].visual.asset_path==str(img)
    assert edited.scenes[0].visual.type=='ai_video'
    assert Path(edited.scenes[0].visual.asset_path).exists()


def test_zero_safe_candidates_raises_without_mutation(tmp_path):
    g=_graph(_scene('chart',kind='dataviz'))
    r=select_scenes(g)
    with pytest.raises(EngineError,match='No safe AI stills'):
        auto_apply(g,r,tmp_path/'generated')
    assert not (tmp_path/'generated').exists()
