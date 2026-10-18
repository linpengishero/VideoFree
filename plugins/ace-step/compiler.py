"""Plugin-owned workflow preparation; shared execution stays in the gateway."""

def prepare(workflow, config, request, media, job_id, prompt):
    for node in workflow.values():
        if node.get('class_type') == 'TextEncodeAceStepAudio1.5':
            node['inputs']['duration'] = float(request.duration_seconds)
            node['inputs']['lyrics'] = '[Instrumental]'
        elif node.get('class_type') == 'EmptyAceStep1.5LatentAudio':
            node['inputs']['seconds'] = float(request.duration_seconds)

