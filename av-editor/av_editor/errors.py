"""Custom exceptions for av-editor."""


class AVEditorError(Exception):
    """Base exception for av-editor errors."""


class ConfigError(AVEditorError):
    """Raised when the config file is invalid."""


class FFmpegError(AVEditorError):
    """Raised when an ffmpeg/ffprobe command fails."""
