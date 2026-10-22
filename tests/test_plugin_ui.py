import copy
import unittest

from backend.modules.generation.plugin_ui import form_values, validate_form


class PluginFormTests(unittest.TestCase):
    def setUp(self):
        self.config = {"parameters": {"amount": {"type": "number"}, "enabled": {"type": "boolean"}}}
        self.ui = {"version": 1, "fields": [
            {"bind": "prompt", "component": "textarea", "label": "Prompt", "required": True},
            {"bind": "parameters.amount", "component": "number", "label": "Amount", "default": 2, "minimum": 0, "maximum": 4},
            {"bind": "parameters.enabled", "component": "checkbox", "label": "Enabled", "default": True},
        ]}

    def test_defaults_do_not_overwrite_zero_false_or_mutate_request(self):
        validate_form(self.ui, self.config)
        payload = {"prompt": "Create", "parameters": {"amount": 0, "enabled": False}}
        original = copy.deepcopy(payload)
        result = form_values(self.ui, payload)
        self.assertEqual(result["parameters"], {"amount": 0, "enabled": False})
        self.assertEqual(payload, original)
        self.assertEqual(form_values(self.ui, {"prompt": "Create"})["parameters"], {"amount": 2, "enabled": True})

    def test_required_range_and_types_reject_before_submission(self):
        for payload in ({"prompt": " "}, {"prompt": "Create", "parameters": {"amount": 5}},
                        {"prompt": "Create", "parameters": {"amount": True}},
                        {"prompt": "Create", "parameters": {"enabled": "false"}}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                form_values(self.ui, payload)

    def test_references_require_a_matching_upload_control(self):
        self.config["references"] = {"image": {"min": 1, "max": 4}}
        with self.assertRaisesRegex(ValueError, "Missing media UI"):
            validate_form(self.ui, self.config)
        self.ui["fields"].append({"bind": "settings.reference_image", "component": "media", "label": "Reference", "media": "image"})
        validate_form(self.ui, self.config)
        self.ui["fields"][-1]["media"] = "audio"
        with self.assertRaises(ValueError):
            validate_form(self.ui, self.config)

    def test_bindings_and_duplicate_fields_are_rejected(self):
        for bind in ("settings.invalid.name", "parameters.missing", "__proto__.x", "target_size", "prompt"):
            ui = copy.deepcopy(self.ui)
            ui["fields"].append({"bind": bind, "component": "text", "label": "Invalid"})
            with self.subTest(bind=bind), self.assertRaises(ValueError):
                validate_form(ui, self.config)

    def test_option_templates_preserve_user_prompts(self):
        ui = {"version": 1, "fields": [{"bind": "settings.music_style_id", "component": "select", "label": "Style",
            "options": [{"value": "pop", "label": "Pop", "prompt": "Pop music."}], "default": "pop"}],
            "prompt_template": {"fields": ["settings.music_style_id"], "suffix": "Clear vocals."}}
        validate_form(ui, {})
        self.assertEqual(form_values(ui, {})["prompt"], "Pop music. Clear vocals.")
        self.assertEqual(form_values(ui, {"prompt": "Custom arrangement"})["prompt"], "Custom arrangement")
        with self.assertRaises(ValueError):
            form_values(ui, {"settings": {"music_style_id": "missing"}})

    def test_postprocess_dimensions_and_parameters_share_the_protocol(self):
        ui = {"version": 1, "fields": [self.ui["fields"][1],
            {"bind": "target_size", "component": "dimensions", "label": "Size", "alignment": 32,
             "presets": [{"edge": 720, "label": "720P"}]}]}
        validate_form(ui, self.config, postprocess=True)
        self.assertEqual(form_values(ui, {"target_size": "1280x736"})["parameters"]["amount"], 2)
        ui["fields"].append(self.ui["fields"][0])
        with self.assertRaisesRegex(ValueError, "Unsupported postprocess"):
            validate_form(ui, self.config, postprocess=True)

    def test_edit_presentation_contract_and_legacy_defaults(self):
        validate_form(self.ui, self.config)
        self.ui["edit"] = {
            "prompt": {"visible": False, "label": "Source description", "label_key": "edit.prompt"},
            "summary": [
                {"source": "operation_name", "label": "Operation", "label_key": "edit.operation"},
                {"source": "provider_name", "label": "Service"},
            ],
            "parameters": {"label": "Enhancement settings", "label_key": "edit.settings"},
        }
        validate_form(self.ui, self.config)

    def test_edit_presentation_contract_rejects_unknown_sources_and_bad_types(self):
        invalid = [
            {"edit": {"prompt": "hidden"}},
            {"edit": {"prompt": {"visible": "no"}}},
            {"edit": {"summary": [{"source": "workflow_path", "label": "Workflow"}]}},
            {"edit": {"summary": [{"source": "model_name", "label": "Model"},
                                    {"source": "model_name", "label": "Engine"}]}},
            {"edit": {"parameters": {"label": 5}}},
        ]
        for extension in invalid:
            ui = {**self.ui, **extension}
            with self.subTest(extension=extension), self.assertRaises(ValueError):
                validate_form(ui, self.config)

    def test_generated_action_form_can_bind_schema_inputs(self):
        ui = {"version": 1, "fields": [
            {"bind": "text", "component": "textarea", "label": "Text", "required": True},
            {"bind": "parameters.strength", "component": "number", "label": "Strength", "default": 0.5},
            {"bind": "target_size", "component": "dimensions", "label": "Size", "alignment": 32,
             "presets": [{"edge": 720, "label": "720P"}]},
        ]}
        schema = {"type": "object", "properties": {
            "text": {"type": "string"}, "width": {"type": "integer"},
            "height": {"type": "integer"}, "parameters": {"type": "object", "properties": {"strength": {"type": "number"}}},
        }}
        validate_form(ui, {}, action_schema=schema)

    def test_generated_action_form_rejects_unmapped_fields(self):
        ui = {"version": 1, "fields": [{"bind": "parameters.hidden", "component": "text", "label": "Hidden"}]}
        with self.assertRaisesRegex(ValueError, "not declared"):
            validate_form(ui, {}, action_schema={"type": "object", "properties": {"parameters": {"type": "object"}}})

    def test_generated_action_dimensions_require_integer_schema_fields(self):
        ui = {"version": 1, "fields": [{"bind": "target_size", "component": "dimensions", "label": "Size",
             "alignment": 32, "presets": [{"edge": 720, "label": "720P"}]}]}
        schema = {"type": "object", "properties": {"width": {"type": "number"}, "height": {"type": "integer"}}}
        with self.assertRaisesRegex(ValueError, "integer width and height"):
            validate_form(ui, {}, action_schema=schema)


if __name__ == "__main__":
    unittest.main()
