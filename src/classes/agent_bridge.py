"""
 @file
 @brief Executes AI-agent tool calls safely on the Qt GUI thread.

 The Bedrock agent conversation loop runs on a background QThread (see
 classes.bedrock_client), but every tool it calls needs to touch the
 project data (classes.query / classes.updates) and, in a couple of cases,
 Qt widgets - both of which must only be accessed from the main/GUI thread.

 AgentBridge marshals each tool call onto the main thread via a queued
 Qt signal and blocks the calling (background) thread until the result is
 ready, using the same pattern as qt_api's internal callback bridge.

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
import os
import threading
import uuid

from qt_api import QObject, Qt, pyqtSignal, QUrl

from classes.app import get_app
from classes.logger import log
from classes.query import Clip, File, Track


class AgentBridge(QObject):
    """Dispatches AI-agent tool calls onto the Qt GUI thread.

    Must be constructed on the main thread (it is never moved to another
    thread), so queued signals delivered to it always execute there.
    """

    _execute_requested = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self._execute_requested.connect(self._run_on_main_thread, Qt.QueuedConnection)

    def call_tool(self, name, tool_input, timeout=60.0):
        """Thread-safe entry point. Callable from any thread; blocks the
        calling thread until the tool has finished executing on the GUI thread."""
        done = threading.Event()
        result_box = {}

        def _invoke():
            try:
                result_box["value"] = self._execute(name, tool_input)
            except Exception as ex:  # Defensive: never let the GUI thread crash
                log.error("Unhandled error executing agent tool '%s'", name, exc_info=True)
                result_box["value"] = {"error": str(ex)}
            finally:
                done.set()

        self._execute_requested.emit(_invoke)
        if not done.wait(timeout):
            return {"error": "Tool '{}' timed out after {:.0f}s".format(name, timeout)}
        return result_box.get("value") or {"error": "Tool '{}' produced no result".format(name)}

    def _run_on_main_thread(self, fn):
        fn()

    def _execute(self, name, tool_input):
        handler = getattr(self, "_tool_" + str(name), None)
        if handler is None:
            return {"error": "Unknown tool: {}".format(name)}
        try:
            return handler(**(tool_input or {})) or {}
        except TypeError as ex:
            return {"error": "Invalid arguments for '{}': {}".format(name, ex)}
        except Exception as ex:
            log.error("Agent tool '%s' failed", name, exc_info=True)
            return {"error": str(ex)}

    # ------------------------------------------------------------------
    # Tool implementations (each name here must match a TOOL_DEFINITIONS
    # entry in classes.agent_tools)
    # ------------------------------------------------------------------

    def _tool_get_project_info(self):
        project = get_app().project
        fps = project.get("fps") or {}
        return {
            "width": project.get("width"),
            "height": project.get("height"),
            "fps_num": fps.get("num"),
            "fps_den": fps.get("den"),
            "sample_rate": project.get("sample_rate"),
            "channels": project.get("channels"),
            "num_files": len(project.get("files") or []),
            "num_clips": len(project.get("clips") or []),
            "num_tracks": len(project.get("layers") or []),
            "project_path": project.current_filepath or "",
        }

    def _tool_list_files(self):
        files = []
        for f in File.filter():
            d = f.data
            files.append({
                "id": f.id,
                "name": d.get("name") or os.path.basename(d.get("path", "")),
                "path": d.get("path"),
                "media_type": d.get("media_type"),
                "duration": d.get("duration"),
            })
        return {"files": files}

    def _tool_list_tracks(self):
        tracks = []
        for t in Track.filter():
            d = t.data
            tracks.append({
                "id": t.id,
                "number": d.get("number"),
                "label": d.get("label"),
                "lock": d.get("lock"),
            })
        tracks.sort(key=lambda x: x["number"] if x["number"] is not None else 0)
        return {"tracks": tracks}

    def _tool_list_clips(self, layer=None):
        kwargs = {}
        if layer is not None:
            kwargs["layer"] = int(layer)
        clips = []
        for c in Clip.filter(**kwargs):
            d = c.data
            clips.append({
                "id": c.id,
                "title": c.title(),
                "file_id": d.get("file_id"),
                "position": d.get("position"),
                "start": d.get("start"),
                "end": d.get("end"),
                "layer": d.get("layer"),
            })
        return {"clips": clips}

    def _tool_import_file(self, path):
        path = str(path or "").strip()
        if not path or not os.path.exists(path):
            return {"error": "File not found: {}".format(path)}

        existing = File.get(path=path)
        if existing:
            return {"file_id": existing.id, "already_imported": True}

        window = get_app().window
        window.files_model.process_urls([QUrl.fromLocalFile(path)], import_quietly=True)

        imported = File.get(path=path)
        if not imported:
            return {"error": "Failed to import file: {}".format(path)}
        return {"file_id": imported.id, "name": imported.data.get("name")}

    def _tool_add_clip(self, file_id, position, layer, start=None, end=None):
        import openshot

        file_obj = File.get(id=file_id)
        if not file_obj:
            return {"error": "Unknown file_id: {}".format(file_id)}

        file_path = file_obj.absolute_path()
        c = openshot.Clip(file_path)
        new_clip = json.loads(c.Json())
        new_clip["position"] = float(position)
        new_clip["layer"] = int(layer)
        new_clip["file_id"] = file_obj.id
        new_clip["title"] = file_obj.data.get("name", os.path.basename(file_path))
        new_clip["reader"] = file_obj.data

        duration = float(new_clip["reader"].get("duration") or 0)
        new_clip["duration"] = duration
        new_clip["start"] = float(start) if start is not None else 0.0
        new_clip["end"] = float(end) if end is not None else duration

        if new_clip["end"] <= new_clip["start"]:
            return {"error": "'end' must be greater than 'start'"}

        clip = Clip()
        clip.data = new_clip
        tid = str(uuid.uuid4())
        get_app().updates.transaction_id = tid
        try:
            clip.save()
        finally:
            get_app().updates.transaction_id = None

        return {"clip_id": clip.id}

    def _tool_move_clip(self, clip_id, position=None, layer=None):
        clip = Clip.get(id=clip_id)
        if not clip:
            return {"error": "Unknown clip_id: {}".format(clip_id)}
        if position is not None:
            clip.data["position"] = float(position)
        if layer is not None:
            clip.data["layer"] = int(layer)
        clip.save()
        return {"clip_id": clip.id, "position": clip.data.get("position"), "layer": clip.data.get("layer")}

    def _tool_trim_clip(self, clip_id, start=None, end=None):
        clip = Clip.get(id=clip_id)
        if not clip:
            return {"error": "Unknown clip_id: {}".format(clip_id)}

        new_start = float(start) if start is not None else float(clip.data.get("start", 0.0))
        new_end = float(end) if end is not None else float(clip.data.get("end", 0.0))
        if new_end <= new_start:
            return {"error": "'end' must be greater than 'start'"}

        clip.data["start"] = new_start
        clip.data["end"] = new_end
        clip.save()
        return {"clip_id": clip.id, "start": new_start, "end": new_end}

    def _tool_delete_clip(self, clip_id):
        clip = Clip.get(id=clip_id)
        if not clip:
            return {"error": "Unknown clip_id: {}".format(clip_id)}
        clip.delete()
        return {"deleted": clip_id}

    def _tool_add_track(self, label=None):
        all_tracks = get_app().project.get("layers") or []
        if all_tracks:
            track_number = max(int(t.get("number", 0)) for t in all_tracks) + 1000000
        else:
            track_number = 1000000

        track = Track()
        track.data = {"number": track_number, "y": 0, "label": str(label or ""), "lock": False}
        track.save()
        return {"track_id": track.id, "number": track_number}

    def _tool_list_available_effects(self):
        import openshot

        raw = json.loads(openshot.EffectInfo.Json())
        effects = [
            {
                "class_name": e.get("class_name"),
                "name": e.get("name"),
                "description": e.get("description", ""),
            }
            for e in raw
        ]
        return {"effects": effects}

    def _tool_add_effect(self, clip_id, effect_name):
        import openshot

        clip = Clip.get(id=clip_id)
        if not clip:
            return {"error": "Unknown clip_id: {}".format(clip_id)}

        effect = openshot.EffectInfo().CreateEffect(str(effect_name or ""))
        if effect is None:
            return {"error": "Unknown effect_name: {}".format(effect_name)}

        effect_id = get_app().project.generate_id()
        effect.Id(effect_id)
        effect_json = json.loads(effect.Json())
        clip.data.setdefault("effects", []).append(effect_json)
        clip.save()
        return {"clip_id": clip.id, "effect_id": effect_id, "effect_name": effect_name}

    def _tool_remove_effect(self, clip_id, effect_id):
        clip = Clip.get(id=clip_id)
        if not clip:
            return {"error": "Unknown clip_id: {}".format(clip_id)}

        effects = clip.data.get("effects", [])
        new_effects = [e for e in effects if e.get("id") != effect_id]
        if len(new_effects) == len(effects):
            return {"error": "Unknown effect_id: {}".format(effect_id)}

        clip.data["effects"] = new_effects
        clip.save()
        return {"clip_id": clip.id, "removed_effect_id": effect_id}

    def _tool_undo_last_action(self):
        get_app().updates.undo()
        get_app().window.refreshFrameSignal.emit()
        return {"status": "undone"}

    def _tool_redo_last_action(self):
        get_app().updates.redo()
        get_app().window.refreshFrameSignal.emit()
        return {"status": "redone"}

    def _tool_open_export_dialog(self):
        get_app().window.actionExportVideo_trigger()
        return {"status": "export_dialog_closed"}
