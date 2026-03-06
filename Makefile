.PHONY: help
.DEFAULT_GOAL := help

help: ## Show this help message
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# Variables
RECORDINGS_DIR := recordings
TIMESTAMP := $(shell date '+%Y-%m-%d_%H-%M-%S')
TARGET_DIR := $(RECORDINGS_DIR)/$(TIMESTAMP)
POLL_INTERVAL ?= 0.1
SNAPSHOT_INTERVAL ?= 10
POSTPROC_DIR ?=
WHISPER_MODEL ?= large-v2
WHISPER_DEVICE ?= auto
WHISPER_COMPUTE ?= auto

# Teams chat capture with diarization
teams-chat-diarize: ## Capture Teams chat with diarization to recordings/<YYYY-MM-DD_HH-MM-SS>
	@echo "Creating target directory: $(TARGET_DIR)"
	mkdir -p "$(TARGET_DIR)"
	@echo "Starting Teams chat capture with diarization..."
	# Use uv run to use local audio-detect with Teams tracking
	uv run audio-detect record --output-dir "$(TARGET_DIR)" --sample-rate 16000 --bit-depth 16 --interval $(POLL_INTERVAL) --snapshot-interval $(SNAPSHOT_INTERVAL)
	@echo "Teams chat with diarization saved to: $(TARGET_DIR)"

# Generic dated capture
dated-capture: ## Generic dated capture to recordings/<YYYY-MM-DD_HH-MM-SS>
	@echo "Creating target directory: $(TARGET_DIR)"
	mkdir -p "$(TARGET_DIR)"
	@echo "Starting dated capture..."
	# Placeholder for actual capture command
	# Example: audio-detect capture --output "$(TARGET_DIR)"
	@echo "Capture will be saved to: $(TARGET_DIR)"

# Post-process a recording directory into audformat DB
postprocess: ## Run diarized ASR + audformat export (usage: make postprocess POSTPROC_DIR=recordings/<timestamp>)
	@if [ -z "$(POSTPROC_DIR)" ]; then \
		echo "POSTPROC_DIR is required, e.g. make postprocess POSTPROC_DIR=$(RECORDINGS_DIR)/2026-03-06_10-07-44"; \
		exit 2; \
	fi
	uv run python - <<'PY'
from audio_detect.postprocess import RecordingPostProcessor

processor = RecordingPostProcessor(
    recording_dir="$(POSTPROC_DIR)",
    model_size="$(WHISPER_MODEL)",
    device="$(WHISPER_DEVICE)",
    compute_type="$(WHISPER_COMPUTE)",
)
path = processor.run()
print(f"audformat DB written to {path}")
PY

# List recordings
list: ## List all recordings
	@if [ -d "$(RECORDINGS_DIR)" ]; then \
		echo "Available recordings:"; \
		ls -la "$(RECORDINGS_DIR)"; \
	else \
		echo "No recordings directory found"; \
	fi

# Clean old recordings (keep last 5)
clean: ## Remove old recordings, keep last 5
	@if [ -d "$(RECORDINGS_DIR)" ]; then \
		cd "$(RECORDINGS_DIR)" && \
		ls -1t | tail -n +6 | xargs -r rm -rf && \
		echo "Cleaned old recordings, keeping last 5"; \
	else \
		echo "No recordings directory found"; \
	fi
