# Claude Instructions for Audio Stream Transcriber

## Important References

1. **Project Documentation**: Read `AGENTS.md` for comprehensive project context, architecture, and implementation details
2. **Global Configuration**: Follow any guidelines in `~/.claude/CLAUDE.md` for general preferences and conventions

## Project-Specific Guidelines

When working on this project:

- **Always read AGENTS.md first** to understand the system architecture and component relationships
- Follow the patterns established in the existing codebase
- Maintain thread-safe implementations for audio processing
- Ensure proper cleanup of temporary files and resources
- Test audio capture and transcription functionality after changes
- Use environment variables for configuration (see .env.example)

## Key Principles

- Real-time performance is critical - avoid blocking operations
- Audio quality and latency are primary concerns
- Keep error handling comprehensive and graceful
- Document any changes to the data flow or component interactions
