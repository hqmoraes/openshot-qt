"""
 @file
 @brief AI Video Agent dock panel: a simple chat UI wired to the Bedrock agent.

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

import html

from qt_api import (
    Qt, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QLabel, QSizePolicy,
)

from classes.app import get_app
from classes.logger import log


class AIChatPanel(QWidget):
    """Dockable chat panel for the AI Video Editing Agent."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.session = None

        _ = get_app()._tr

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.chat_log = QTextEdit(self)
        self.chat_log.setReadOnly(True)
        self.chat_log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.chat_log, 1)

        input_row = QHBoxLayout()
        self.input_line = QLineEdit(self)
        self.input_line.setPlaceholderText(_("Ask the AI agent to edit your project..."))
        self.input_line.returnPressed.connect(self.send_clicked)
        input_row.addWidget(self.input_line, 1)

        self.send_btn = QPushButton(_("Send"), self)
        self.send_btn.clicked.connect(self.send_clicked)
        input_row.addWidget(self.send_btn)

        layout.addLayout(input_row)

        bottom_row = QHBoxLayout()
        self.status_label = QLabel("", self)
        self.status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bottom_row.addWidget(self.status_label, 1)

        self.clear_btn = QPushButton(_("New Conversation"), self)
        self.clear_btn.clicked.connect(self.clear_conversation)
        bottom_row.addWidget(self.clear_btn)

        layout.addLayout(bottom_row)

        self._append_system_message(
            _("Configure AWS credentials in Preferences > AI Agent, then ask me to "
              "edit your project (e.g. \"add intro.mp4 to the timeline at 0 seconds\").")
        )

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def ensure_session(self):
        if self.session is None:
            from classes.bedrock_client import BedrockAgentSession
            self.session = BedrockAgentSession(self)
            self.session.response_ready.connect(self._on_response)
            self.session.tool_call_started.connect(self._on_tool_call_started)
            self.session.error_occurred.connect(self._on_error)
        return self.session

    def shutdown(self):
        if self.session:
            self.session.shutdown()
            self.session = None

    def clear_conversation(self):
        if self.session:
            self.session.reset_conversation()
        self.chat_log.clear()
        _ = get_app()._tr
        self._append_system_message(_("Started a new conversation."))

    # ------------------------------------------------------------------
    # UI actions
    # ------------------------------------------------------------------

    def send_clicked(self):
        _ = get_app()._tr
        text = self.input_line.text().strip()
        if not text:
            return

        settings = get_app().get_settings()
        if not settings.get("aws-agent-enabled"):
            self._append_system_message(
                _("The AI Video Editing Agent is disabled. Enable it in Preferences > AI Agent first.")
            )
            return

        self.input_line.clear()
        self._append_user_message(text)
        self._set_busy(True)
        try:
            self.ensure_session().send_message(text)
        except Exception as ex:
            log.error("Failed to send message to AI agent", exc_info=True)
            self._append_system_message(_("Error: {}").format(ex))
            self._set_busy(False)

    # ------------------------------------------------------------------
    # Session signal handlers
    # ------------------------------------------------------------------

    def _on_response(self, text):
        self._append_agent_message(text or "")
        self._set_busy(False)

    def _on_tool_call_started(self, name, _input_json):
        _ = get_app()._tr
        self.status_label.setText(_("Using tool: {}").format(name))

    def _on_error(self, message):
        _ = get_app()._tr
        self._append_system_message(_("Error: {}").format(message))
        self._set_busy(False)

    # ------------------------------------------------------------------
    # Chat log helpers
    # ------------------------------------------------------------------

    def _set_busy(self, busy):
        _ = get_app()._tr
        self.send_btn.setEnabled(not busy)
        self.input_line.setEnabled(not busy)
        self.status_label.setText(_("Thinking...") if busy else "")

    def _append_user_message(self, text):
        self.chat_log.append(
            "<div style='margin:4px 0;'><b>{}</b> {}</div>".format(
                get_app()._tr("You:"), html.escape(text)
            )
        )

    def _append_agent_message(self, text):
        formatted = html.escape(text).replace("\n", "<br/>")
        self.chat_log.append(
            "<div style='margin:4px 0;'><b>{}</b> {}</div>".format(
                get_app()._tr("Agent:"), formatted
            )
        )

    def _append_system_message(self, text):
        self.chat_log.append(
            "<div style='margin:4px 0; color: gray;'><i>{}</i></div>".format(html.escape(text))
        )
