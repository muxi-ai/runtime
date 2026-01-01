---
name: av-chat
description: Audio/Video chat interface for processing media files as primary conversation input
status: backlog
created: 2025-09-03T20:41:27Z
---

# PRD: A/V Chat

## Executive Summary

The A/V Chat feature introduces a dedicated interface (`overlord.avchat()`) for handling audio and video files as primary conversation inputs in the MUXI Runtime. This feature enables seamless processing of voice messages, video clips, and other media-first interactions commonly used in modern messaging platforms like Telegram, WhatsApp, and Discord. By automatically transcribing audio and analyzing video content, the system transforms media into actionable prompts while maintaining the clean separation of concerns in the runtime architecture.

## Problem Statement

### What problem are we solving?

Currently, the MUXI Runtime's `chat()` interface expects text messages as primary input. When users send voice messages or video clips through messaging platforms, SDKs must handle complex media processing logic, including:
- Detecting media types and formats
- Deciding how to process media files
- Constructing appropriate prompts for transcription
- Managing the flow between media processing and chat response

This creates several issues:
1. **SDK Complexity**: Each SDK must implement its own media handling logic
2. **Inconsistent Behavior**: Different SDKs may handle media differently
3. **Poor User Experience**: Voice messages may fail silently or require explicit commands
4. **Architectural Confusion**: Mixing media detection logic with text chat violates separation of concerns

### Why is this important now?

- **Market Expectation**: 70% of messaging platform users regularly use voice messages
- **Platform Growth**: Telegram alone processes over 1 billion voice messages daily
- **User Accessibility**: Voice input is critical for accessibility and mobile-first users
- **Competitive Advantage**: Native media support differentiates MUXI from text-only AI systems

## User Stories

### Primary User Personas

#### 1. End User - Mobile Messenger
**Profile**: Sarah, 28, uses Telegram for daily communication
**Story**: As a mobile user, I want to send voice messages to the AI assistant and receive intelligent responses, so that I can interact naturally without typing.
**Acceptance Criteria**:
- Voice message is automatically transcribed
- AI understands and responds to the transcribed content
- Response time is under 3 seconds for messages under 60 seconds
- Original voice message context is preserved

#### 2. SDK Developer - Platform Integration
**Profile**: Alex, 35, developing WhatsApp Business integration
**Story**: As an SDK developer, I want a clear API for handling voice and video messages, so that I can easily integrate media processing without complex logic.
**Acceptance Criteria**:
- Single method call for media processing
- Clear documentation and examples
- Consistent behavior across media types
- Error handling for unsupported formats

#### 3. Formation Developer - AI Application Builder
**Profile**: Jordan, 31, building customer service formations
**Story**: As a formation developer, I want my agents to seamlessly handle audio and video inputs, so that users can interact naturally with my AI application.
**Acceptance Criteria**:
- Agents receive transcribed/analyzed content transparently
- Media metadata is available if needed
- Works with existing agent capabilities
- No special configuration required

### Detailed User Journeys

#### Journey 1: Voice Message Response
1. User sends voice message via Telegram
2. SDK receives voice message update
3. SDK calls `overlord.avchat()` with audio file
4. Runtime transcribes audio using configured model
5. Runtime processes transcription as conversation prompt
6. Agent generates appropriate response
7. Response returned to user via Telegram

#### Journey 2: Video Analysis Request
1. User sends video clip for analysis
2. SDK extracts video file and metadata
3. SDK calls `overlord.avchat()` with video file
4. Runtime analyzes video frames and transcribes audio
5. Runtime creates comprehensive prompt from analysis
6. Agent processes and responds with insights
7. Formatted response delivered to user

## Requirements

### Functional Requirements

#### Core Features
1. **New `avchat()` Method**
   - Accepts all `chat()` parameters except `message`
   - Requires `files` parameter with media content
   - Auto-generates appropriate prompts based on media type
   - Returns same response types as `chat()`

2. **Media Type Detection**
   - Automatic detection based on MIME types
   - Support for audio/* and video/* content types
   - Graceful fallback for unknown media types

3. **Audio Processing**
   - Transcription using configured audio model (e.g., Whisper)
   - Support for common formats: MP3, M4A, OGG, WAV, WEBM
   - Automatic language detection
   - Optional speaker diarization for multi-speaker audio

4. **Video Processing**
   - Frame analysis using vision model
   - Audio track transcription if present
   - Combined analysis of visual and audio content
   - Support for common formats: MP4, MOV, AVI, WEBM

5. **Prompt Generation**
   - Intelligent prompt templates based on media type
   - Optional custom prompt template parameter
   - Context-aware prompt enhancement

#### User Interactions and Flows

1. **Simple Voice Message**
   ```python
   response = await overlord.avchat(
       files=[voice_file],
       user_id="user123"
   )
   ```

2. **Video with Analysis Request**
   ```python
   response = await overlord.avchat(
       files=[video_file],
       prompt_template="Analyze this video for safety violations",
       user_id="user123"
   )
   ```

3. **Multi-File Processing**
   ```python
   response = await overlord.avchat(
       files=[audio_file1, audio_file2],
       user_id="user123"
   )
   ```

### Non-Functional Requirements

#### Performance
- Audio transcription: < 2 seconds for 60-second clips
- Video analysis: < 5 seconds for 30-second videos
- Support files up to 25MB initially
- Concurrent request handling without blocking

#### Security
- Validate file types before processing
- Sanitize file content to prevent injection attacks
- Respect user privacy - no permanent media storage
- Encrypted transmission of media content

#### Scalability
- Handle 1000+ concurrent media processing requests
- Efficient memory usage for large files
- Queue management for heavy load periods
- Graceful degradation under extreme load

## Success Criteria

### Key Metrics
1. **Adoption Rate**: 50% of voice messages use `avchat()` within 3 months
2. **Processing Success Rate**: >95% successful transcription/analysis
3. **Response Time**: P95 < 3 seconds for audio, < 5 seconds for video
4. **User Satisfaction**: >4.5/5 rating for voice message interactions

### KPIs
- Daily active media messages processed
- Average processing time by media type
- Error rate by format and size
- SDK adoption rate of new API

## Constraints & Assumptions

### Technical Constraints
- Requires configured audio/video models in formation
- Limited by underlying model capabilities
- File size limits based on available memory
- Network bandwidth for media transmission

### Assumptions
- Audio/video models are properly configured
- SDKs can extract media from platform messages
- Users have adequate network for media upload
- Transcription models support user languages

### Timeline Constraints
- MVP implementation: 2 weeks
- SDK integration guides: 1 week
- Testing and optimization: 1 week
- Total timeline: 4 weeks

## Out of Scope

The following items are explicitly NOT included in this phase:

1. **Real-time streaming** - No live audio/video streaming support
2. **Media generation** - No audio/video response generation
3. **Media editing** - No transcription editing or correction UI
4. **Custom models** - No training of custom transcription models
5. **Media storage** - No permanent storage of media files
6. **Platform-specific features** - No platform-specific media handling
7. **Group chat media** - Focus on single-user interactions only

## Dependencies

### External Dependencies
1. **OpenAI Whisper API** - For audio transcription
2. **Vision-capable LLMs** - For video frame analysis
3. **OneLLM Framework** - For model abstraction
4. **Platform SDKs** - For media extraction and delivery

### Internal Dependencies
1. **Formation System** - Must support audio/video model configuration
2. **Chat Orchestrator** - Must route `avchat()` calls appropriately
3. **Document Processing** - Reuse multimodal processing pipeline
4. **Memory Systems** - Store transcribed content in conversation context

## Risk Mitigation

### Identified Risks
1. **Model Availability**: Audio/video models may be unavailable
   - Mitigation: Graceful fallback with clear error messages

2. **Large File Processing**: Memory issues with large media files
   - Mitigation: Streaming processing, file size limits

3. **Format Compatibility**: Unsupported media formats
   - Mitigation: Clear format documentation, conversion utilities

4. **Privacy Concerns**: Sensitive audio/video content
   - Mitigation: No permanent storage, clear privacy policy

## Implementation Recommendations

1. **Phase 1**: Core `avchat()` implementation with audio support
2. **Phase 2**: Video processing capabilities
3. **Phase 3**: Advanced features (custom templates, multi-file)
4. **Phase 4**: Performance optimization and caching

## Appendix

### Supported Media Formats
- **Audio**: MP3, M4A, OGG, WAV, WEBM, AAC, FLAC
- **Video**: MP4, MOV, AVI, WEBM, MKV

### Example Integration Code

```python
# Telegram SDK Integration
async def handle_voice_message(update, context):
    voice = update.message.voice
    file = await voice.get_file()
    audio_bytes = await file.download_as_bytearray()
    
    response = await overlord.avchat(
        files=[{
            'filename': f'voice_{voice.file_id}.ogg',
            'content': audio_bytes,
            'content_type': 'audio/ogg',
            'size': voice.file_size
        }],
        user_id=update.effective_user.id,
        session_id=str(update.effective_chat.id)
    )
    
    await update.message.reply_text(response.content)
```