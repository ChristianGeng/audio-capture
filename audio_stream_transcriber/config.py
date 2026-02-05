"""Configuration management for audio streaming transcriber."""

import os
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""
    
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    audio_files_path: Path = Field(
        default=Path("/home/cgeng/work/myfiles/audio-capture"),
        env="AUDIO_FILES_PATH"
    )
    chunk_duration_seconds: float = Field(default=5.0, env="CHUNK_DURATION_SECONDS")
    overlap_seconds: float = Field(default=1.0, env="OVERLAP_SECONDS")
    sample_rate: int = Field(default=16000, env="SAMPLE_RATE")
    channels: int = Field(default=1, env="CHANNELS")
    
    # Audio device settings
    pulse_device: str = Field(
        default="alsa_output.usb-Razer_Razer_Kraken_V3_X_000000000001-00.analog-stereo.monitor",
        env="PULSE_DEVICE"
    )
    
    # MCP server settings
    mcp_server_port: int = Field(default=8000, env="MCP_SERVER_PORT")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


def get_settings() -> Settings:
    """Get application settings."""
    return Settings()
