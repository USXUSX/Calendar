"""Latest-only Chat handoff. CAL owns context and adoption; Chat owns candidate."""
import copy
import json
import os
import tempfile
from pathlib import Path

from .errors import ConflictError, DomainError, ValidationError
from .trip_detail import build_trip_detail_view
from scripts.validate_trip import validation_stage_errors


class ChatExchangeMixin:
    def _chat_path(self, trip_id, filename):
        self._trip_path(trip_id)  # Same stable ID and traversal gate as formal Trip.
        directory = self.trip_root / "chat" / trip_id
        path = directory / filename
        if any(p.is_symlink() for p in (directory.parent, directory, path)):
            raise ValidationError("Chat共有ファイルのsymlinkは使えません。")
        return path

    def _write_chat_context(self, trip_id, effective):
        with self._read() as connection:
            version = connection.execute("SELECT version FROM trips WHERE id = ?", (trip_id,)).fetchone()["version"]
            instructions = [dict(row) for row in connection.execute(
                "SELECT id, instruction FROM ai_instructions WHERE trip_id = ? AND state = 'pending' ORDER BY created_at, id",
                (trip_id,))]
        value = {"trip_id": trip_id,
                 "current_revision": {"trip_version": version, "trip_hash": self._digest(self._trip_path(trip_id).read_bytes())},
                 "effective_revision": {"trip_version": version, "effective_hash": self._digest(self._canonical_json(effective))},
                 "trip": effective, "instructions": instructions}
        path = self._chat_path(trip_id, "context.json")
        payload = self._canonical_json(value)
        try:
            if path.exists() and path.read_bytes() == payload:
                return value
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".context-", delete=False) as handle:
                    temporary = Path(handle.name)
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        except OSError as error:
            raise ValidationError("CALの状態は保存済みですが、Chat contextを更新できません。共有先を確認して再読込してください。") from error
        return value

    def get_chat_context(self, trip_id):
        # Serialize publication with CAL writers so an older reader cannot replace
        # a newer context or combine an old effective Trip with a new version.
        with self._command() as connection:
            connection.execute("BEGIN IMMEDIATE")
            effective = self.get_effective_trip(trip_id)
            return self._write_chat_context(trip_id, effective)

    def add_chat_instruction(self, instruction_id, trip_id, instruction):
        # Chat instructions do not enqueue an API/AFM worker.
        from .service import _now
        self._require_text(instruction_id, "instruction_id")
        self._require_text(instruction, "instruction")
        self._registered_trip(trip_id)
        with self._command() as connection:
            timestamp = _now()
            connection.execute(
                "INSERT INTO ai_instructions (id, trip_id, instruction, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (instruction_id, trip_id, instruction, timestamp, timestamp))
        self.get_chat_context(trip_id)
        return {"status": "pending", "instruction_id": instruction_id}

    @staticmethod
    def _complete_chat_instructions(connection, trip_id, instruction_ids, timestamp):
        for identity in instruction_ids:
            connection.execute("UPDATE ai_instructions SET state = 'applied', updated_at = ? WHERE id = ? AND trip_id = ?",
                               (timestamp, identity, trip_id))
            connection.execute("UPDATE generation_requests SET state = 'completed', updated_at = ? WHERE instruction_id = ?",
                               (timestamp, identity))

    def _read_chat_envelope(self, trip_id):
        path = self._chat_path(trip_id, "candidate.json")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as error:
            raise ValidationError("candidate.jsonを読めません。ChatでJSONを修正してください。") from error

    def review_chat_candidate(self, trip_id):
        context = self.get_chat_context(trip_id)
        return {**self._review_chat_candidate(trip_id, context), "instructions": context["instructions"]}

    def _review_chat_candidate(self, trip_id, context):
        if not self._chat_path(trip_id, "candidate.json").exists():
            return {"status": "absent", "ready": False, "instructions": context["instructions"]}
        try:
            envelope = self._read_chat_envelope(trip_id)
            if not isinstance(envelope, dict) or set(envelope) != {"trip_id", "base_revision", "handled_instruction_ids", "trip"}:
                raise ValidationError("candidate Envelopeの項目を確認してください。")
            if envelope["trip_id"] != trip_id:
                raise ValidationError("candidateのtrip_idが一致しません。")
            if envelope["base_revision"] != context["effective_revision"]:
                return {"status": "stale", "ready": False, "message": "最新contextからChatでcandidateを再作成してください。"}
            if not isinstance(envelope["handled_instruction_ids"], list):
                raise ValidationError("handled_instruction_idsは配列にしてください。")
            handled = self._instruction_ids(envelope["handled_instruction_ids"])
            pending = {item["id"] for item in context["instructions"]}
            if not set(handled) <= pending:
                raise ValidationError("処理済み指示は現在の未処理指示から指定してください。")
            stage, errors = validation_stage_errors(envelope["trip"], self._trip_schema)
            if errors:
                return {"status": "invalid", "ready": False, "stage": stage, "errors": errors}
            candidate, _ = self._validated_candidate(trip_id, envelope["trip"])
            # Check the common Todo/reference constraints against the complete new base.
            # Overrides are absorbed only inside the adoption transaction, never here.
            with self._read() as connection:
                for row in connection.execute("SELECT trip_item_id FROM todos WHERE trip_id = ? AND trip_item_id IS NOT NULL", (trip_id,)):
                    if not self._item_matches(candidate, row["trip_item_id"]):
                        raise ConflictError("Todoが参照する予定は削除できません。")
            changes = _changes(context["trip"], candidate)
            view = build_trip_detail_view(candidate)
            for day in view["days"]:
                for entry in day["entries"]:
                    entry["direct_edit_paths"] = {}
                    entry["ai_local_update_target"] = None
            return {"status": "ready", "ready": True, "message": "Chatからの変更あり",
                    "candidate": copy.deepcopy(envelope), "view": view, "changes": changes,
                    "handled_instructions": [item for item in context["instructions"] if item["id"] in handled]}
        except DomainError as error:
            return {"status": "invalid", "ready": False, "message": str(error)}

    def _finish_chat_candidate(self, trip_id, envelope_digest):
        path = self._chat_path(trip_id, "candidate.json")
        if not path.exists():
            return
        try:
            envelope = self._read_chat_envelope(trip_id)
            if self._digest(self._canonical_json(envelope)) == envelope_digest:
                path.unlink()
        except (DomainError, KeyError, TypeError):
            pass  # A new or incomplete Chat file is not the adopted candidate.

    def adopt_chat_candidate(self, trip_id, candidate, *, confirmed=False):
        if confirmed is not True:
            raise ValidationError("Chat candidateの内容確認が必要です。")
        recovered = self.recover_trip_adoption(trip_id)
        if recovered is not None and recovered["status"] == "adopted":
            return recovered
        review = self.review_chat_candidate(trip_id)
        if not review["ready"]:
            raise ConflictError(review.get("message", "candidateを修正して再確認してください。"))
        if candidate != review["candidate"]:
            raise ConflictError("確認後にcandidateが変更されました。再読込して確認してください。")
        context = self.get_chat_context(trip_id)
        result = self._adopt_candidate_atomically(
            trip_id, candidate["trip"], context["current_revision"]["trip_version"],
            context["current_revision"]["trip_hash"], kind="chat", chat_envelope=candidate)
        self.get_chat_context(trip_id)
        return result


def _changes(before, after, label="旅程"):
    """Concise field changes, matching stable-ID collections instead of list offsets."""
    labels = {"title": "名称", "summary": "コメント", "details": "詳細", "days": "日程",
              "scheduleItems": "予定", "places": "場所", "transports": "移動", "bookings": "予約",
              "routeSummary": "代表エリア", "time": "時刻", "start": "開始", "end": "終了",
              "action": "予定内容", "address": "住所", "location": "座標", "urls": "URL",
              "selection": "採用場所", "candidatePlaceIds": "場所候補", "dateRange": "旅行期間",
              "preparation": "準備", "rioPlan": "Rio", "status": "状態", "searchQuery": "検索条件"}
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        return [change for key in sorted(set(before) | set(after))
                for change in _changes(before.get(key), after.get(key), label + " / " + labels.get(key, key))]
    if isinstance(before, list) and isinstance(after, list) and before + after and all(
            isinstance(item, dict) and "id" in item for item in before + after):
        old = {item["id"]: item for item in before}
        new = {item["id"]: item for item in after}
        changes = []
        for identity in dict.fromkeys([*old, *new]):
            item = new.get(identity, old.get(identity))
            name = item.get("action") or item.get("name") or item.get("date") or item.get("title") or identity
            changes.extend(_changes(old.get(identity), new.get(identity), label + " / " + name))
        if list(old) != list(new) and set(old) == set(new):
            changes.append({"field": label + " / 並び順", "before": list(old), "after": list(new)})
        return changes
    return [{"field": label, "before": before, "after": after}]
