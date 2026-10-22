const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const path = require('node:path');

(async () => {
  const formPath = path.resolve(__dirname, '../frontend/src/config/pluginForm.js');
  const { collectActionInputs, restoreActionInputs } = await import(pathToFileURL(formPath));
  const refineUi = {version: 1, fields: [{bind: 'target_size', component: 'dimensions', label: 'Size',
    alignment: 32, presets: [{edge: 720, label: '720P'}]}]};
  const source = {width: 768, height: 432, params: {latent_width: 768, latent_height: 432}};
  const restoredRefine = restoreActionInputs(refineUi, null, {width: 1376, height: 768});
  assert.equal(restoredRefine.target_size, '1376x768');
  assert.equal(collectActionInputs(refineUi, {target_size: '1536x864'}).width, 1536);
  assert.equal(collectActionInputs(refineUi, {target_size: '1536x864'}).height, 864);

  const speechUi = {version: 1, fields: [
    {bind: 'text', component: 'textarea', label: 'Text', required: true},
    {bind: 'preset_id', component: 'voice', label: 'Voice', required: true},
    {bind: 'speed', component: 'number', label: 'Speed', default: 1},
  ]};
  assert.deepEqual(restoreActionInputs(speechUi, null, {
    text: 'Original narration', character: 'young_female', speed: 1.25,
  }), {settings: {}, parameters: {}, text: 'Original narration', preset_id: 'young_female', speed: 1.25});
  const changedSpeech = collectActionInputs(speechUi, {
    text: 'Edited narration', preset_id: 'news_male', speed: 0.9,
  }, {category_id: 'category-1'});
  assert.deepEqual(changedSpeech, {
    category_id: 'category-1', text: 'Edited narration', preset_id: 'news_male', speed: 0.9,
  });
})().catch(error => { console.error(error); process.exitCode = 1; });
