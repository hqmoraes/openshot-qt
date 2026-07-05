"""
 @file
 @brief AI video-editing agent: a tool-use conversation loop built on
 Amazon Bedrock's Converse API, running in a background QThread.

 This is the "genuine AI agent" piece: it maintains conversation history,
 sends it (plus the tool catalog from classes.agent_tools) to a Bedrock
 model, and whenever the model requests a tool call, executes it through
 classes.agent_bridge.AgentBridge and feeds the result back - looping
 until the model produces a final answer.

 No AWS credentials or account-specific values are hard-coded here; every
 credential, region, and model id comes from classes.aws_credentials,
 which reads the user's own Preferences (Preferences > AI Agent). This
 keeps the module reusable/distributable across AWS accounts.

 @section LICENSE

 Copyright (c) 2008-2026 OpenShot Studios, LLC
 (http://www.openshotstudios.com). This file is part of
 OpenShot Video Editor (http://www.openshot.org), an open-source project
 dedicated to delivering high quality video editing and animation solutions
 to the world.

 OpenShot Video Editor is free software: you can redistribute it and/or modify
 it under the terms of the GNU General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 OpenShot Video Editor is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU General Public License for more details.

 You should have received a copy of the GNU General Public License
 along with OpenShot Library.  If not, see <http://www.gnu.org/licenses/>.
"""

import json

from qt_api import QObject, QThread, pyqtSignal, pyqtSlot

from classes import agent_tools
from classes.agent_bridge import AgentBridge
from classes.app import get_app
from classes.logger import log
from classes import aws_credentials

DEFAULT_MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
MAX_TOOL_ITERATIONS = 12

SYSTEM_PROMPT = (
    "You are an AI video-editing assistant embedded inside OpenShot Video Editor. "
    "You help the user edit their project by calling the tools provided to you - "
    "you cannot edit the project any other way. Always inspect the current project "
    "state (get_project_info, list_files, list_tracks, list_clips) before making "
    "changes, so you use real ids rather than guessing them. Prefer small, "
    "reversible steps. Never call open_export_dialog unless the user explicitly "
    "asks to export/render the video - it opens a dialog for the user to confirm, "
    "it does not render silently. When you finish making changes, briefly summarize "
    "what you did in plain language."
)


def _extract_text(message):
    """Pull the plain-text parts out of a Bedrock Converse message."""
    parts = []
    for block in (message or {}).get("content", []) or []:
        if isinstance(block, dict) and "text" in block:
            parts.append(block["text"])
    return "\n".join(parts).strip()


class BedrockAgentWorker(QObject):
    """Runs the tool-use conversation loop. Lives on a background QThread."""

    turn_finished = pyqtSignal(str)
    tool_call_started = pyqtSignal(str, str)
    tool_call_finished = pyqtSignal(str, str)
    error_occurred = pyqtSignal(str)

    def __init__(self, agent_bridge):
        super().__init__()
        self.agent_bridge = agent_bridge
        self.messages = []

    @pyqtSlot()
    def reset_conversation(self):
        self.messages = []

    @pyqtSlot(str)
    def send_message(self, user_text):
        log.info("AI agent: send_message received on worker thread")
        try:
            self._run_turn(user_text)
        except aws_credentials.AwsCredentialsError as ex:
            log.warning("AI agent: credentials error: %s", ex)
            self.error_occurred.emit(str(ex))
        except Exception as ex:
            log.error("Bedrock agent turn failed", exc_info=True)
            self.error_occurred.emit(str(ex))

    def _run_turn(self, user_text):
        log.info("AI agent: turn starting (message length=%d)", len(user_text or ""))
        settings = aws_credentials.get_aws_settings()
        if not settings["enabled"]:
            log.warning("AI agent: disabled in settings, aborting turn")
            self.error_occurred.emit(
                "The AI Video Editing Agent is disabled. Enable it in "
                "Preferences > AI Agent and configure your AWS credentials first."
            )
            return

        model_id = str(get_app().get_settings().get("bedrock-model-id") or "").strip() or DEFAULT_MODEL_ID
        log.info("AI agent: using model_id=%s auth_mode=%s region=%s", model_id, settings.get("auth_mode"), settings.get("region"))

        session = aws_credentials.build_boto3_session(settings)
        client = session.client("bedrock-runtime")

        self.messages.append({"role": "user", "content": [{"text": user_text}]})
        tool_config = agent_tools.to_bedrock_tool_config()
        system_prompts = [{"text": SYSTEM_PROMPT}]

        for iteration in range(MAX_TOOL_ITERATIONS):
            log.info("AI agent: calling bedrock-runtime.converse (iteration %d)", iteration + 1)
            response = client.converse(
                modelId=model_id,
                system=system_prompts,
                messages=self.messages,
                toolConfig=tool_config,
            )
            output_message = response["output"]["message"]
            self.messages.append(output_message)
            stop_reason = response.get("stopReason")
            log.info("AI agent: converse returned stopReason=%s", stop_reason)

            if stop_reason != "tool_use":
                self.turn_finished.emit(_extract_text(output_message))
                return

            tool_result_contents = []
            for block in output_message.get("content", []) or []:
                tool_use = block.get("toolUse") if isinstance(block, dict) else None
                if not tool_use:
                    continue

                name = tool_use.get("name")
                tool_input = tool_use.get("input") or {}
                use_id = tool_use.get("toolUseId")

                self.tool_call_started.emit(name, json.dumps(tool_input))
                result = self.agent_bridge.call_tool(name, tool_input)
                self.tool_call_finished.emit(name, json.dumps(result))

                is_error = isinstance(result, dict) and bool(result.get("error"))
                tool_result_contents.append({
                    "toolResult": {
                        "toolUseId": use_id,
                        "content": [{"json": result}],
                        "status": "error" if is_error else "success",
                    }
                })

            self.messages.append({"role": "user", "content": tool_result_contents})

        self.error_occurred.emit(
            "The agent used too many tool calls in a row ({}) without finishing. "
            "Stopping to avoid a runaway loop.".format(MAX_TOOL_ITERATIONS)
        )


class BedrockAgentSession(QObject):
    """Owns the background thread + worker, and exposes a simple, main-thread-safe API."""

    response_ready = pyqtSignal(str)
    tool_call_started = pyqtSignal(str, str)
    tool_call_finished = pyqtSignal(str, str)
    error_occurred = pyqtSignal(str)

    _request_send = pyqtSignal(str)
    _request_reset = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # Created here, on the main thread - AgentBridge's thread affinity
        # stays the GUI thread, which is required for its queued dispatch.
        self.agent_bridge = AgentBridge()

        self._thread = QThread()
        self._thread.setObjectName("bedrock_agent_worker")
        self._worker = BedrockAgentWorker(self.agent_bridge)
        self._worker.moveToThread(self._thread)

        self._request_send.connect(self._worker.send_message)
        self._request_reset.connect(self._worker.reset_conversation)
        self._worker.turn_finished.connect(self.response_ready)
        self._worker.tool_call_started.connect(self.tool_call_started)
        self._worker.tool_call_finished.connect(self.tool_call_finished)
        self._worker.error_occurred.connect(self.error_occurred)

        self._thread.start()

    def send_message(self, text):
        self._request_send.emit(str(text or ""))

    def reset_conversation(self):
        self._request_reset.emit()

    def shutdown(self):
        if self._thread.isRunning():
            self._thread.quit()
            self._thread.wait()
