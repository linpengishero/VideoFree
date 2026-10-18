import { gateway as platform } from '@framework/services/api';

async function run(action, projectId, inputs = {}) {
  const response = await platform.runPluginAction(`film.${action}`, {projectId, inputs});
  return response.result;
}

export const gateway = {
  films: projectId => run('list', projectId),
  filmSources: projectId => run('sources', projectId),
  filmAssets: projectId => run('assets', projectId),
  addFilmClip: (projectId, id, clip) => run('add-clip', projectId, {film_id:id, clip}),
  saveFilm: (projectId, plan, id, revision=null) => run('save', projectId, {
    ...(id ? {film_id:id} : {}), ...(revision == null ? {} : {expected_revision:revision}), plan,
  }),
  renderFilm: (projectId, id) => run('render', projectId, {film_id:id}),
  deleteFilm: (projectId, id) => run('delete', projectId, {film_id:id}),
  filmProgress: (projectId, id, progress) => run('progress', projectId, {film_id:id, progress}),
  transcribeFilm: (projectId, id, options={}) => run('transcribe', projectId, {film_id:id, ...options}),
  previewFilm: (projectId, id) => run('preview', projectId, {film_id:id}),
  cancelFilm: (projectId, id, quality='final') => run('cancel', projectId, {film_id:id, quality}),
  filmProxies: (projectId, jobId, index=0, libraryPath=null) => run('proxies', projectId, jobId ? {job_id:jobId, artifact_index:index} : {library_path:libraryPath, artifact_index:index}),
  selectSource: (projectId, jobId, selected) => run('select-source', projectId, {job_id:jobId, selected}),
  upload: file => platform.upload(file),
  importAsset: (projectId, uploadId, name) => run('import-asset', projectId, {upload_id:uploadId, name}),
  deleteAsset: (projectId, libraryPath) => run('delete-asset', projectId, {library_path:libraryPath}),
};
