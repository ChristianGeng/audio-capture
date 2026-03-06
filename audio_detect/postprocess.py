"""Post-processing utilities for diarized recordings."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
import json
import logging
from pathlib import Path
import shutil
from typing import Any

import audformat
import audeer
from faster_whisper import WhisperModel
import pandas as pd


logger = logging.getLogger(__name__)


@dataclass
class SpeakerInterval:
    """Structured representation of a speaker activity interval."""

    email: str
    name: str
    start_sec: float
    end_sec: float


@dataclass
class TranscriptSegment:
    """Light-weight container for ASR output."""

    start_sec: float
    end_sec: float
    text: str
    avg_logprob: float
    speaker_email: str | None = None
    speaker_name: str | None = None


def parse_timestamp(timestamp: str) -> datetime:
    """Return timezone-aware datetime from ISO strings."""

    normalized = timestamp.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


class RecordingPostProcessor:
    """Run diarized ASR and export the result as an audformat database."""

    def __init__(
        self,
        recording_dir: str,
        model_size: str = "large-v2",
        language: str | None = None,
        device: str = "auto",
        compute_type: str = "auto",
        beam_size: int = 5,
        output_dir: str | None = None,
    ) -> None:
        self.recording_dir = audeer.path(recording_dir)
        self.model_size = model_size
        self.language = language
        self.device = device
        self.compute_type = compute_type
        self.beam_size = beam_size
        self.output_dir = (
            audeer.path(output_dir)
            if output_dir
            else audeer.path(self.recording_dir, "audformat-db")
        )

    def run(self) -> Path:
        """Execute the complete post-processing pipeline."""

        meta = self._load_meta()
        audio_file = audeer.path(self.recording_dir, meta["audio_file"])
        events_file = audeer.path(self.recording_dir, meta["events_file"])

        start_dt = parse_timestamp(meta["start_time"])
        end_dt = parse_timestamp(meta.get("end_time", meta["start_time"]))

        speaker_intervals = self._build_speaker_intervals(
            events_file,
            start_dt,
            end_dt,
        )

        asr_segments = self._run_asr(audio_file)
        annotated_segments = self._attach_speakers(asr_segments, speaker_intervals)

        db_root = self._write_audformat_db(
            audio_file,
            meta,
            annotated_segments,
        )
        logger.info("audformat database created at %s", db_root)
        return Path(db_root)

    def _load_meta(self) -> dict[str, Any]:
        meta_path = audeer.path(self.recording_dir, "meta.json")
        with open(meta_path, encoding="utf-8") as handle:
            return json.load(handle)

    def _build_speaker_intervals(
        self,
        events_path: str,
        start_dt: datetime,
        end_dt: datetime,
    ) -> list[SpeakerInterval]:
        intervals: list[SpeakerInterval] = []
        active: dict[str, dict[str, Any]] = {}
        with open(events_path, encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                event = json.loads(line)
                if event.get("type") == "speaker_start":
                    active[event["email"]] = {
                        "start": parse_timestamp(event["ts"]),
                        "name": event.get("name", event["email"]),
                    }
                elif event.get("type") == "speaker_stop":
                    start_info = active.pop(event["email"], None)
                    if not start_info:
                        continue
                    intervals.append(
                        SpeakerInterval(
                            email=event["email"],
                            name=start_info["name"],
                            start_sec=(start_info["start"] - start_dt).total_seconds(),
                            end_sec=(parse_timestamp(event["ts"]) - start_dt).total_seconds(),
                        )
                    )

        end_seconds = (end_dt - start_dt).total_seconds()
        for email, payload in active.items():
            intervals.append(
                SpeakerInterval(
                    email=email,
                    name=payload["name"],
                    start_sec=(payload["start"] - start_dt).total_seconds(),
                    end_sec=end_seconds,
                )
            )

        return intervals

    def _run_asr(self, audio_file: str) -> list[TranscriptSegment]:
        model = WhisperModel(
            self.model_size,
            device=self.device,
            compute_type=self.compute_type,
        )
        segments: list[TranscriptSegment] = []
        generator, _ = model.transcribe(
            audio_file,
            language=self.language,
            beam_size=self.beam_size,
            vad_filter=True,
        )
        for segment in generator:
            segments.append(
                TranscriptSegment(
                    start_sec=segment.start,
                    end_sec=segment.end,
                    text=segment.text.strip(),
                    avg_logprob=segment.avg_logprob,
                )
            )
        return segments

    def _attach_speakers(
        self,
        segments: list[TranscriptSegment],
        intervals: list[SpeakerInterval],
    ) -> list[TranscriptSegment]:
        for segment in segments:
            segment.speaker_email, segment.speaker_name = self._find_speaker(
                segment.start_sec,
                segment.end_sec,
                intervals,
            )
        return segments

    @staticmethod
    def _find_speaker(
        start: float,
        end: float,
        intervals: Iterable[SpeakerInterval],
    ) -> tuple[str | None, str | None]:
        best_overlap = 0.0
        chosen_email: str | None = None
        chosen_name: str | None = None
        for interval in intervals:
            overlap = min(end, interval.end_sec) - max(start, interval.start_sec)
            if overlap > best_overlap and overlap > 0:
                best_overlap = overlap
                chosen_email = interval.email
                chosen_name = interval.name
        return chosen_email, chosen_name

    def _write_audformat_db(
        self,
        audio_file: str,
        meta: dict[str, Any],
        segments: list[TranscriptSegment],
    ) -> str:
        db_root = Path(audeer.mkdir(self.output_dir))
        source_audio = Path(audio_file)
        target_audio = db_root / source_audio.name
        if source_audio.resolve() != target_audio.resolve():
            shutil.copy2(source_audio, target_audio)
        rel_audio = source_audio.name

        db = audformat.Database(
            name=f"teams-recording-{Path(self.recording_dir).name}",
            source="audio-capture",
            description="Diarized Teams meeting with ASR transcript",
        )
        db.media["recording"] = audformat.Media(kind="file")
        db.files["recording"] = rel_audio

        index = audformat.segmented_index(
            file=[rel_audio for _ in segments],
            start=pd.to_timedelta([s.start_sec for s in segments], unit="s"),
            end=pd.to_timedelta([s.end_sec for s in segments], unit="s"),
        )

        table = audformat.Table(index)
        table["speaker_email"] = audformat.Column()
        table["speaker_name"] = audformat.Column()
        table["text"] = audformat.Column()
        table["avg_logprob"] = audformat.Column(unit="logprob")

        table["speaker_email"].values[:] = [
            segment.speaker_email or "unknown" for segment in segments
        ]
        table["speaker_name"].values[:] = [
            segment.speaker_name or "Unknown" for segment in segments
        ]
        table["text"].values[:] = [segment.text for segment in segments]
        table["avg_logprob"].values[:] = [
            segment.avg_logprob for segment in segments
        ]

        db["transcript"] = table
        db.save(db_root)

        meta_copy = meta.copy()
        meta_copy["audformat_root"] = db_root
        with open(
            audeer.path(db_root, "postprocess_meta.json"),
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(meta_copy, handle, indent=2)
        return db_root
