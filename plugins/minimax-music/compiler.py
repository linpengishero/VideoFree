"""Plugin-owned workflow preparation; shared execution stays in the gateway."""

def prepare(workflow, config, request, media, job_id, prompt):
    for node in workflow.values():
        if node.get('class_type') == 'MiniMaxMusic3TextEncode':
            node['inputs']['max_duration'] = float(request.duration_seconds)

