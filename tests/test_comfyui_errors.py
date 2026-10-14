import json
import unittest

from backend.integrations.comfyui.errors import describe_failure


class ComfyUIErrorsTest(unittest.TestCase):
    def test_missing_node(self):
        raw = 'ComfyUI HTTP 400: ' + json.dumps({"error": {"type": "missing_node_type", "extra_info": {"class_type": "UnknownNode"}}})
        result = describe_failure(raw)
        self.assertEqual(result["missing_items"], ["UnknownNode"])
        self.assertEqual(result["raw"], raw)

    def test_model_choice(self):
        result = describe_failure("Node 34 (VAELoader), vae_name: 'qwen.safetensors' unavailable in ComfyUI; available: []")
        self.assertEqual(result["code"], "comfyui_missing_model")
        self.assertIn("models/vae/", result["suggestion"])

    def test_http_model_validation(self):
        raw = json.dumps({"node_errors": {"1": {"errors": [{"type": "value_not_in_list", "extra_info": {"input_name": "lora_name", "received_value": "test.safetensors"}}]}}})
        self.assertIn("models/loras/", describe_failure(raw)["suggestion"])

    def test_execution_oom(self):
        raw = json.dumps({"messages": [["execution_error", {"node_type": "Upscaler", "exception_message": "CUDA out of memory"}]]})
        result = describe_failure(raw)
        self.assertEqual(result["code"], "comfyui_out_of_memory")
        self.assertIn("Upscaler", result["message"])

    def test_unknown_preserved(self):
        self.assertEqual(describe_failure("unexpected error")["message"], "unexpected error")

    def test_connection_and_dependency(self):
        self.assertEqual(describe_failure("无法连接 ComfyUI：http://localhost:8189")["code"], "comfyui_connection_failed")
        self.assertEqual(describe_failure("No module named 'sageattention'")["code"], "comfyui_missing_dependency")
