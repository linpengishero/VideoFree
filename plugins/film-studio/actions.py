"""Application actions exposed through the platform HTTP and MCP dispatcher."""
from .schemas import StageWrite
from .service import CompositionService


async def startup(runtime):
    CompositionService(runtime.application).recover()


async def execute(request, runtime):
    service = CompositionService(runtime.application, runtime)
    inputs = request['inputs']
    project_id = runtime.project_id
    action = request['action']['id'].removeprefix('film.')
    film_id = inputs.get('film_id')
    if action == 'list':
        return {'items': service.list(project_id)}
    if action == 'sources':
        return {'items': service.selected(project_id)}
    if action == 'assets':
        return {'items': service.imported_assets(project_id)}
    if action == 'get':
        return service.get(project_id, film_id)
    if action == 'save':
        return service.save(project_id, inputs['plan'], film_id,
                            expected_revision=inputs.get('expected_revision'))
    if action == 'add-clip':
        return service.add_clip(project_id, film_id, inputs['clip'])
    if action == 'select-source':
        return service.select(inputs['job_id'], inputs['selected'])
    if action == 'import-asset':
        return service.import_asset(project_id, inputs['upload_id'], inputs.get('name', ''))
    if action == 'delete-asset':
        return service.delete_asset(project_id, inputs['library_path'])
    if action == 'progress':
        update = StageWrite.model_validate(inputs['progress'])
        return service.progress(project_id, film_id, update.stage, update.status, update.note)
    if action == 'transcribe':
        return await service.queue_transcribe(project_id, film_id, inputs.get('language', 'zh'),
                                              inputs.get('model', 'large-v3-turbo'))
    if action == 'delete':
        service.delete(project_id, film_id)
        return {'deleted': True}
    if action == 'render':
        return await service.submit(project_id, film_id)
    if action == 'validate':
        return await service.validate(project_id, film_id)
    if action == 'preview':
        return await service.submit(project_id, film_id, 'preview')
    if action == 'cancel':
        return service.cancel(project_id, film_id, inputs.get('quality', 'final'))
    if action == 'proxies':
        return await service.proxies(project_id, inputs.get('job_id'), inputs.get('artifact_index', 0),
                                     inputs.get('library_path'))
    raise ValueError('未知成片动作')
