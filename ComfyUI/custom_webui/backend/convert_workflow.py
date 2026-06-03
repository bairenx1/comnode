import sys, json, re
from pathlib import Path

WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / "workflows"
USER_WORKFLOWS_DIR = Path(__file__).resolve().parent.parent.parent / "user" / "default" / "workflows"

SKIP_TYPES = {'MarkdownNote', 'Note'}

KSAMPLER_WIDGET_MAP = {
    0: ('seed', int, {'type': 'number', 'default': 1}),
    2: ('steps', int, {'type': 'number', 'default': 20, 'min': 1, 'max': 10000}),
    3: ('cfg', float, {'type': 'number', 'default': 7.5, 'min': 1, 'max': 30, 'step': 0.5}),
    4: ('sampler_name', str, {'type': 'combo', 'default': 'euler'}),
    5: ('scheduler', str, {'type': 'combo', 'default': 'normal'}),
    6: ('denoise', float, {'type': 'number', 'default': 1.0, 'min': 0, 'max': 1, 'step': 0.05}),
}

SAMPLER_NAMES = ['euler', 'euler_ancestral', 'heun', 'heunpp2', 'dpm_2', 'dpm_2_ancestral',
    'lms', 'dpm_fast', 'dpm_adaptive', 'dpmpp_2s_ancestral', 'dpmpp_sde', 'dpmpp_sde_gpu',
    'dpmpp_2m', 'dpmpp_2m_sde', 'dpmpp_2m_sde_gpu', 'dpmpp_3m_sde', 'dpmpp_3m_sde_gpu',
    'ddim', 'uni_pc', 'uni_pc_bh2', 'lcm']

SCHEDULERS = ['normal', 'karras', 'exponential', 'sgm_uniform', 'simple', 'ddim_uniform',
    'beta', 'linear_quadratic', 'kl_optimal']


def convert_native_to_api(native_data):
    nodes = native_data.get('nodes', [])
    links = native_data.get('links', [])

    link_map = {}
    for link in links:
        link_id, from_node, from_slot, to_node, to_slot, _ = link
        link_map[link_id] = (from_node, from_slot, to_node, to_slot)

    node_api = {}
    field_mapping = {}
    ui_fields = []
    clip_text_count = 0
    seen_ui_field_names = set()

    for node in nodes:
        nid = node['id']
        ntype = node.get('type', '')
        if ntype in SKIP_TYPES:
            continue

        inputs = {}
        widgets_values = node.get('widgets_values', [])
        node_inputs = node.get('inputs', [])

        is_clip = ntype == 'CLIPTextEncode'

        if ntype == 'KSampler':
            for idx, (field_name, cast_fn, cfg) in KSAMPLER_WIDGET_MAP.items():
                if idx < len(widgets_values) and widgets_values[idx] is not None:
                    val = widgets_values[idx]
                    try:
                        val = cast_fn(val) if cast_fn != str else str(val)
                    except (ValueError, TypeError):
                        val = cfg.get('default', 0)
                    inputs[field_name] = val
                    field_mapping[field_name] = f'{nid}.inputs.{field_name}'
                    field_cfg = dict(cfg)
                    if field_name == 'sampler_name':
                        field_cfg['options'] = SAMPLER_NAMES
                    elif field_name == 'scheduler':
                        field_cfg['options'] = SCHEDULERS
                    ui_fields.append({'name': field_name, **field_cfg})

        widget_idx = 0
        for inp in node_inputs:
            inp_name = inp['name']
            link = inp.get('link')

            if link is not None:
                from_node, from_slot, _, _ = link_map.get(link, (None, None, None, None))
                if from_node is not None:
                    inputs[inp_name] = [str(from_node), from_slot]
            elif ntype != 'KSampler':
                if inp.get('widget') or inp.get('type') in ('INT', 'FLOAT', 'STRING', 'COMBO'):
                    val = widgets_values[widget_idx] if widget_idx < len(widgets_values) else None

                    # CLIPTextEncode text: map to prompt / negative_prompt
                    if is_clip and inp_name == 'text' and val is not None:
                        inputs[inp_name] = val
                        clip_text_count += 1
                        fname = 'prompt' if clip_text_count == 1 else 'negative_prompt'
                        field_mapping[fname] = f'{nid}.inputs.text'
                        if fname not in seen_ui_field_names:
                            seen_ui_field_names.add(fname)
                            ui_fields.append({
                                'name': fname,
                                'type': 'string',
                                'default': inp.get('default', val),
                            })
                        widget_idx += 1
                        continue

                    if val is not None:
                        inputs[inp_name] = val
                        field_cfg = {'type': inp.get('type', 'string').lower(), 'default': inp.get('default', val)}
                        for k in ('min', 'max', 'step', 'tooltip'):
                            if k in inp:
                                field_cfg[k] = inp[k]

                        if inp_name in ('width', 'height', 'batch_size'):
                            field_mapping[inp_name] = f'{nid}.inputs.{inp_name}'
                            field_cfg['type'] = 'number'
                            if inp_name not in seen_ui_field_names:
                                seen_ui_field_names.add(inp_name)
                                ui_fields.append({'name': inp_name, **field_cfg})
                        elif inp_name == 'ckpt_name':
                            field_mapping[inp_name] = f'{nid}.inputs.{inp_name}'
                            field_cfg['type'] = 'combo'
                            if 'checkpoint' not in seen_ui_field_names:
                                seen_ui_field_names.add('checkpoint')
                                ui_fields.append({'name': 'checkpoint', **field_cfg})
                    widget_idx += 1

        if inputs:
            node_api[str(nid)] = {'class_type': ntype, 'inputs': inputs}

    return node_api, field_mapping, ui_fields
def auto_convert_all():
    converted = 0
    for fpath in sorted(USER_WORKFLOWS_DIR.glob('*.json')):
        try:
            native = json.loads(fpath.read_text(encoding='utf-8'))
            if 'nodes' not in native:
                continue
            api_data, field_mapping, ui_fields = convert_native_to_api(native)
            if not api_data:
                print(f'SKIP {fpath.name}: no convertible nodes')
                continue
            workflow_id = re.sub(r'[^a-zA-Z0-9_]', '_', fpath.stem).lower()
            if not workflow_id:
                workflow_id = f'workflow_{converted}'
            api_path = WORKFLOWS_DIR / f'{workflow_id}.json'
            api_path.write_text(json.dumps(api_data, indent=2, ensure_ascii=False), encoding='utf-8')
            name = native.get('extra', {}).get('workflow_name', fpath.stem)
            mapping = {
                'workflow_id': workflow_id,
                'name': name,
                'category': 'converted',
                'workflow_file': f'{workflow_id}.json',
                'mapping_file': f'{workflow_id}.mapping.json',
                'ui_schema': {'fields': ui_fields},
                'field_mapping': field_mapping,
            }
            mapping_path = WORKFLOWS_DIR / f'{workflow_id}.mapping.json'
            mapping_path.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding='utf-8')
            print(f'OK {fpath.name} -> {workflow_id}')
            converted += 1
        except Exception as e:
            print(f'ERR {fpath.name}: {e}')
    print(f'Converted {converted} workflows')
    return converted

if __name__ == '__main__':
    auto_convert_all()
