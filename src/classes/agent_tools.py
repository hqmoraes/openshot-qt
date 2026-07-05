"""
 @file
 @brief Tool schemas exposed to the Bedrock AI video-editing agent.

 Each entry describes one action the agent can perform on the current
 OpenShot project (list media, add/move/trim clips, add effects, etc).
 The actual execution of these tools happens in classes.agent_bridge.AgentBridge -
 this module only defines the names/descriptions/input schemas advertised
 to the language model (Bedrock Converse API "toolConfig" format).

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

TOOL_DEFINITIONS = [
    {
        "name": "get_project_info",
        "description": "Get metadata about the currently open project: resolution, fps, "
                       "sample rate, channels, and counts of files/clips/tracks.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_files",
        "description": "List all media files that have been imported into the project.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_tracks",
        "description": "List all timeline tracks (layers), including their number, label, and lock state. "
                       "Higher 'number' values are drawn above lower ones.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_clips",
        "description": "List clips currently on the timeline, optionally filtered to a single track/layer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "layer": {"type": "integer", "description": "Optional track/layer number to filter by."},
            },
            "required": [],
        },
    },
    {
        "name": "import_file",
        "description": "Import a local media file (video, audio, or image) into the project's file bin, "
                       "so it can subsequently be added to the timeline with add_clip.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute local file path to import."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "add_clip",
        "description": "Add a previously-imported file to the timeline as a new clip.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "The id of an imported file (see list_files)."},
                "position": {"type": "number", "description": "Position on the timeline, in seconds."},
                "layer": {"type": "integer", "description": "Track/layer number to place the clip on (see list_tracks)."},
                "start": {"type": "number", "description": "Optional trim-in point within the source media, in seconds."},
                "end": {"type": "number", "description": "Optional trim-out point within the source media, in seconds."},
            },
            "required": ["file_id", "position", "layer"],
        },
    },
    {
        "name": "move_clip",
        "description": "Move an existing clip to a new position and/or track.",
        "input_schema": {
            "type": "object",
            "properties": {
                "clip_id": {"type": "string", "description": "The id of the clip to move (see list_clips)."},
                "position": {"type": "number", "description": "New position on the timeline, in seconds."},
                "layer": {"type": "integer", "description": "New track/layer number."},
            },
            "required": ["clip_id"],
        },
    },
    {
        "name": "trim_clip",
        "description": "Change the in/out trim points of an existing clip (i.e. cut its start/end).",
        "input_schema": {
            "type": "object",
            "properties": {
                "clip_id": {"type": "string", "description": "The id of the clip to trim (see list_clips)."},
                "start": {"type": "number", "description": "New trim-in point within the source media, in seconds."},
                "end": {"type": "number", "description": "New trim-out point within the source media, in seconds."},
            },
            "required": ["clip_id"],
        },
    },
    {
        "name": "delete_clip",
        "description": "Remove a clip from the timeline.",
        "input_schema": {
            "type": "object",
            "properties": {
                "clip_id": {"type": "string", "description": "The id of the clip to delete (see list_clips)."},
            },
            "required": ["clip_id"],
        },
    },
    {
        "name": "add_track",
        "description": "Add a new, empty track/layer above all existing tracks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "label": {"type": "string", "description": "Optional display label for the new track."},
            },
            "required": [],
        },
    },
    {
        "name": "list_available_effects",
        "description": "List every effect class the agent can attach to a clip via add_effect "
                       "(e.g. Blur, Brightness, Caption, Crop, Saturation, etc.).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "add_effect",
        "description": "Attach a named effect to a clip (see list_available_effects for valid names).",
        "input_schema": {
            "type": "object",
            "properties": {
                "clip_id": {"type": "string", "description": "The id of the clip to modify (see list_clips)."},
                "effect_name": {"type": "string", "description": "The effect's class_name, e.g. 'Blur' or 'Caption'."},
            },
            "required": ["clip_id", "effect_name"],
        },
    },
    {
        "name": "remove_effect",
        "description": "Remove a previously-attached effect from a clip.",
        "input_schema": {
            "type": "object",
            "properties": {
                "clip_id": {"type": "string", "description": "The id of the clip to modify (see list_clips)."},
                "effect_id": {"type": "string", "description": "The id of the effect to remove."},
            },
            "required": ["clip_id", "effect_id"],
        },
    },
    {
        "name": "undo_last_action",
        "description": "Undo the most recent project change (equivalent to Ctrl+Z).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "redo_last_action",
        "description": "Redo the most recently undone project change (equivalent to Ctrl+Shift+Z).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "open_export_dialog",
        "description": "Open the Export Video dialog so the user can review settings and start rendering. "
                       "This tool never renders silently - the user must confirm the export themselves.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


def to_bedrock_tool_config():
    """Return the tool list in Amazon Bedrock Converse API 'toolConfig' format."""
    return {
        "tools": [
            {
                "toolSpec": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "inputSchema": {"json": tool["input_schema"]},
                }
            }
            for tool in TOOL_DEFINITIONS
        ]
    }
