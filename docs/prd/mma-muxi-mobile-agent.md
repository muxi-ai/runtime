# MMA (MUXI Mobile Agent) - Product Requirements Document

**Version:** 1.0  
**Date:** January 2026  
**Author:** Ran Aroussi  
**Status:** Draft

---

## Document Purpose

This PRD defines the requirements for MMA (MUXI Mobile Agent), the Android application that serves as the primary mobile interface for the MUXI "Her" experience. This document covers MVP scope, technical requirements, and phased delivery.

---

## Product Overview

### What is MMA?

MMA is an Android application that transforms a smartphone into a voice-first AI companion interface. It enables natural, conversational interaction with MUXI while providing deep system integration for context awareness, notification management, and cross-device synchronization.

### Target Device

**Primary:** Clicks Communicator (Android 16)  
**Secondary:** Any Android 13+ device with Accessibility Service support

### Core Value Proposition

- Talk to MUXI naturally, get spoken responses
- MUXI sees what you see (screen context)
- MUXI hears what you hear (notifications)
- MUXI acts on your behalf (app control)
- Seamless sync with desktop (MDA) and home (MHA)

---

## User Personas

### Primary: Ran (Power User / Developer)

- Wants "Her"-style AI interaction
- Values privacy and control
- Willing to grant extensive permissions for functionality
- Uses multiple devices (Clicks, Mac, home speakers)
- Wants to minimize screen time while maximizing productivity

### Secondary: Early Adopter

- Tech-savvy user interested in AI assistants
- Frustrated with Siri/Google/Alexa limitations
- Wants proactive, context-aware AI
- Comfortable with Android power-user features

---

## Requirements

### Functional Requirements

#### FR1: Voice Input

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR1.1 | Accept voice input via Pebble Ring | P0 | Requires Pebble SDK integration |
| FR1.2 | Accept voice input via hardware side button | P0 | Clicks Communicator dedicated button |
| FR1.3 | Accept voice input via on-screen button | P1 | Fallback for non-Clicks devices |
| FR1.4 | Support wake word activation | P2 | "Hey MUXI" or custom phrase |
| FR1.5 | Stream audio to MUXI backend in real-time | P0 | Low latency requirement |
| FR1.6 | Support push-to-talk and voice activity detection | P0 | User preference |

#### FR2: Voice Output

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR2.1 | Play TTS responses from MUXI | P0 | Backend provides audio or text |
| FR2.2 | Duck active media during MUXI speech | P0 | Music quiets, MUXI speaks, music resumes |
| FR2.3 | Route audio to connected Bluetooth device | P0 | AirPods, earbuds, etc. |
| FR2.4 | Route audio to phone speaker when no BT | P0 | Fallback |
| FR2.5 | Support audio routing to home speakers via MHA | P1 | When at home |
| FR2.6 | Queue responses when audio output unavailable | P2 | Deliver when appropriate |

#### FR3: Screen Context (Accessibility Service)

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR3.1 | Capture current screen content | P0 | Text from any app |
| FR3.2 | Identify current foreground app | P0 | Package name + app name |
| FR3.3 | Extract structured data where possible | P1 | Sender, subject, etc. from emails |
| FR3.4 | Send context to MUXI with voice queries | P0 | "What's this?" needs context |
| FR3.5 | Perform UI actions on MUXI's behalf | P1 | Tap, scroll, type |
| FR3.6 | Respect user-defined exclusion list | P1 | Don't read banking apps, etc. |

#### FR4: Notification Management

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR4.1 | Read all incoming notifications | P0 | Via NotificationListenerService |
| FR4.2 | Aggregate notifications by app/sender | P1 | Group for summarization |
| FR4.3 | Provide notification summary on demand | P0 | "What did I miss?" |
| FR4.4 | Triage notifications by importance | P1 | MUXI decides what's urgent |
| FR4.5 | Proactively alert for high-priority items | P1 | Configurable thresholds |
| FR4.6 | Mark notifications as read via MUXI | P2 | "Mark as read" |

#### FR5: Location & Geofencing

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR5.1 | Track user location (coarse) | P0 | For geofence triggers |
| FR5.2 | Register geofences for reminders | P0 | Enter/exit triggers |
| FR5.3 | Support named locations | P1 | "Office," "Home," "Gym" |
| FR5.4 | Learn locations over time | P2 | Auto-detect frequent places |
| FR5.5 | Report location to MUXI for context | P1 | "Where am I?" |
| FR5.6 | Detect room within home (WiFi fingerprint) | P2 | For MHA audio routing |

#### FR6: Media Control

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR6.1 | Play/pause active media | P0 | Via MediaSession API |
| FR6.2 | Skip track forward/backward | P0 | |
| FR6.3 | Report currently playing track | P1 | "What's playing?" |
| FR6.4 | Control volume | P1 | |
| FR6.5 | Support Spotify, YouTube Music, etc. | P0 | Any MediaSession-compatible app |

#### FR7: Sync with MDA

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR7.1 | Sync clipboard bidirectionally | P0 | Copy on Mac, paste on phone |
| FR7.2 | Sync reminders bidirectionally | P0 | Unified reminder list |
| FR7.3 | Transfer files on demand | P1 | "Send this to my Mac" |
| FR7.4 | Share current context with MDA | P2 | MDA knows what phone is showing |
| FR7.5 | Receive notifications from MDA | P2 | Mac notifications on phone |

#### FR8: Reminders

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR8.1 | Create time-based reminders | P0 | "Remind me at 5pm" |
| FR8.2 | Create location-based reminders | P0 | "Remind me when I leave" |
| FR8.3 | Create context-based reminders | P2 | "Remind me when I'm free" |
| FR8.4 | List pending reminders | P0 | "What are my reminders?" |
| FR8.5 | Complete/dismiss reminders | P0 | |
| FR8.6 | Sync with Apple Reminders via MDA | P1 | Bridge to Apple ecosystem |

#### FR9: Persistent Service

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR9.1 | Run as foreground service | P0 | Required for always-on |
| FR9.2 | Show persistent notification | P0 | Android requirement |
| FR9.3 | Survive app kills and restarts | P0 | Auto-restart |
| FR9.4 | Minimize battery impact | P1 | Optimize wake locks |
| FR9.5 | Respect battery saver mode | P2 | Graceful degradation |

#### FR10: Android Auto Integration

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR10.1 | Expose MUXI as Android Auto voice service | P1 | Car microphone → MUXI |
| FR10.2 | Route TTS to car speakers when connected | P1 | Automatic routing |
| FR10.3 | Support hands-free message reading | P1 | "Read my messages" |
| FR10.4 | Support hands-free message replies | P1 | "Reply to Sarah..." |
| FR10.5 | Deep link to navigation apps | P1 | "Navigate to..." opens Maps/Waze |
| FR10.6 | Detect Android Auto connection state | P0 | For audio routing logic |
| FR10.7 | Support calendar/reminder queries | P2 | "What's my day look like?" |

#### FR11: Glasses Camera Integration

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR11.1 | Connect to glasses module via BLE | P1 | ESP32-S3 based clip-on |
| FR11.2 | Receive camera frames on demand | P1 | "What am I looking at?" |
| FR11.3 | Receive periodic low-res context frames | P2 | Ambient awareness |
| FR11.4 | Receive wake word trigger from glasses | P1 | "Hey MUXI" detected on device |
| FR11.5 | Stream glasses mic audio when ACTIVE | P1 | For conversation mode |
| FR11.6 | Send commands to glasses (capture, stream) | P1 | Control from MMA |
| FR11.7 | Handle glasses disconnect gracefully | P1 | Fall back to ring-only mode |

#### FR12: Conversation State Management

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR12.1 | Support DORMANT and ACTIVE states | P0 | Core conversation model |
| FR12.2 | Enter ACTIVE on ring tap | P0 | Primary trigger |
| FR12.3 | Enter ACTIVE on wake word (via glasses) | P1 | Hands-free trigger |
| FR12.4 | Keep mic hot while MUXI is speaking | P0 | Enable interruption |
| FR12.5 | Keep mic hot for 10 sec after MUXI stops | P0 | Allow natural follow-up |
| FR12.6 | Return to DORMANT after 10 sec silence | P0 | Auto-exit conversation |
| FR12.7 | Allow interruption of MUXI speech | P0 | MUXI stops, listens |
| FR12.8 | Re-enter ACTIVE via ring/wake word anytime | P0 | Resume conversation |

---

### Non-Functional Requirements

#### NFR1: Performance

| ID | Requirement | Target |
|----|-------------|--------|
| NFR1.1 | Voice input to MUXI response latency | < 2 seconds |
| NFR1.2 | Screen context capture latency | < 500ms |
| NFR1.3 | Notification processing latency | < 1 second |
| NFR1.4 | Geofence trigger latency | < 30 seconds |
| NFR1.5 | App startup time | < 3 seconds |

#### NFR2: Battery

| ID | Requirement | Target |
|----|-------------|--------|
| NFR2.1 | Background battery usage | < 5% per day |
| NFR2.2 | Active usage battery | Comparable to other voice assistants |

#### NFR3: Privacy & Security

| ID | Requirement | Notes |
|----|-------------|-------|
| NFR3.1 | All network traffic encrypted | TLS 1.3 minimum |
| NFR3.2 | Local storage encrypted | Android Keystore |
| NFR3.3 | No data collection beyond functionality | Privacy-first |
| NFR3.4 | User audit log of MUXI access | What did MUXI see/do? |
| NFR3.5 | Granular permission controls | User can disable features |

#### NFR4: Reliability

| ID | Requirement | Target |
|----|-------------|--------|
| NFR4.1 | Service uptime | 99.9% (while device is on) |
| NFR4.2 | Crash rate | < 0.1% of sessions |
| NFR4.3 | Graceful offline handling | Queue and retry |

---

## Technical Architecture

### High-Level Architecture

```
┌────────────────────────────────────────────────────────────┐
│                         MMA App                            │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                    UI Layer                          │  │
│  │  • Minimal UI (settings, permissions, status)        │  │
│  │  • Voice activation button                           │  │
│  │  • Notification shade controls                       │  │
│  └──────────────────────────────────────────────────────┘  │
│                            │                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                 Service Layer                        │  │
│  │                                                      │  │
│  │  ┌─────────────┐ ┌───────────────┐ ┌──────────────┐  │  │
│  │  │   Voice     │ │ Accessibility │ │ Notification │  │  │
│  │  │   Service   │ │    Service    │ │   Listener   │  │  │
│  │  └─────────────┘ └───────────────┘ └──────────────┘  │  │
│  │                                                      │  │
│  │  ┌─────────────┐ ┌───────────────┐ ┌──────────────┐  │  │
│  │  │  Location   │ │     Media     │ │     Sync     │  │  │
│  │  │   Service   │ │   Controller  │ │    Service   │  │  │
│  │  └─────────────┘ └───────────────┘ └──────────────┘  │  │
│  │                                                      │  │
│  └──────────────────────────────────────────────────────┘  │
│                            │                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                 Core Layer                           │  │
│  │                                                      │  │
│  │  ┌─────────────┐ ┌───────────────┐ ┌──────────────┐  │  │
│  │  │   MUXI      │ │     Local     │ │    Audio     │  │  │
│  │  │   Client    │ │    Storage    │ │    Router    │  │  │
│  │  └─────────────┘ └───────────────┘ └──────────────┘  │  │
│  │                                                      │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                            │
└────────────────────────────────────────────────────────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │  MUXI Backend   │
                   └─────────────────┘
```

### Component Details

#### Voice Service

**Responsibilities:**
- Capture audio from microphone
- Integrate with Pebble Ring SDK
- Handle hardware button events (Clicks side button)
- Stream audio to MUXI backend
- Receive and play TTS responses

**Key Classes:**
```
VoiceService (Foreground Service)
├── AudioCaptureManager
├── PebbleRingIntegration
├── HardwareButtonHandler
├── MuxiAudioClient (WebSocket)
└── TTSPlayer
```

#### Accessibility Service

**Responsibilities:**
- Capture screen content from any app
- Extract text, structure, and metadata
- Perform UI actions (tap, scroll, type)
- Maintain app exclusion list

**Key Classes:**
```
MuxiAccessibilityService (AccessibilityService)
├── ScreenContentExtractor
├── AppContextResolver
├── UIActionExecutor
└── PrivacyFilter
```

#### Notification Listener

**Responsibilities:**
- Receive all notifications
- Parse and categorize by app/sender
- Aggregate and summarize
- Track read/unread state

**Key Classes:**
```
MuxiNotificationListener (NotificationListenerService)
├── NotificationParser
├── NotificationAggregator
├── PriorityClassifier
└── NotificationStore
```

#### Location Service

**Responsibilities:**
- Track device location
- Manage geofences
- Detect room within home
- Report location to MUXI

**Key Classes:**
```
LocationService
├── GeofenceManager
├── LocationTracker
├── RoomDetector (WiFi fingerprinting)
└── PlaceResolver
```

#### Media Controller

**Responsibilities:**
- Control media playback
- Query now playing
- Volume management

**Key Classes:**
```
MediaController
├── MediaSessionManager
├── PlaybackController
└── VolumeManager
```

#### Glasses Service

**Responsibilities:**
- BLE connection to glasses module
- Receive camera frames
- Receive wake word triggers
- Stream mic audio in ACTIVE state
- Manage conversation state

**Key Classes:**
```
GlassesService
├── BleConnectionManager
├── FrameReceiver
├── WakeWordHandler
├── ConversationStateManager
│   ├── DORMANT state
│   ├── ACTIVE state
│   └── 10-second timeout logic
└── GlassesMicStreamer
```

#### Conversation State Manager

**Responsibilities:**
- Track DORMANT/ACTIVE states
- Handle state transitions
- Manage mic hot window (10 sec after MUXI speaks)
- Coordinate between ring, glasses, and voice services

**State Machine:**
```
┌───────────────────────────────────────────────────────┐
│                                                       │
│  DORMANT ◄───────────────────────────────────────┐    │
│     │                                            │    │
│     │ Ring tap OR wake word                      │    │
│     ▼                                            │    │
│  ACTIVE                                          │    │
│     │                                            │    │
│     │ • Mic hot (can interrupt MUXI)             │    │
│     │ • 10 sec window after MUXI stops           │    │
│     │                                            │    │
│     └─────── 10 sec silence ─────────────────────┘    │
│                                                       │
└───────────────────────────────────────────────────────┘
```

#### Sync Service

**Responsibilities:**
- Bidirectional sync with MDA
- Clipboard sync
- Reminder sync
- File transfer

**Key Classes:**
```
SyncService
├── ClipboardSync
├── ReminderSync
├── FileTransfer
└── MdaClient
```

### Data Flow: Voice Query with Context

```
1. User taps Pebble Ring
           │
           ▼
2. VoiceService captures audio
           │
           ▼
3. AccessibilityService captures screen context
   {
     app: "Gmail",
     screen_text: "From: john@example.com...",
     structured: { sender: "john@example.com", subject: "Q1 Budget" }
   }
           │
           ▼
4. MuxiClient sends to backend
   {
     audio: <stream>,
     context: { app, screen_text, location, notifications },
     user_id: "ran"
   }
           │
           ▼
5. MUXI Backend processes, returns response
   {
     text: "This email from John is about...",
     audio: <tts_stream>,
     actions: []
   }
           │
           ▼
6. TTSPlayer plays response
   - Ducks active media
   - Plays MUXI response
   - Restores media volume
```

---

## Permissions Required

| Permission | Purpose | User Explanation |
|------------|---------|------------------|
| `RECORD_AUDIO` | Voice input | "Talk to MUXI" |
| `FOREGROUND_SERVICE` | Always-on service | "MUXI stays ready" |
| `BIND_ACCESSIBILITY_SERVICE` | Screen reading | "MUXI sees what you see" |
| `BIND_NOTIFICATION_LISTENER_SERVICE` | Notification access | "MUXI reads your notifications" |
| `ACCESS_FINE_LOCATION` | Geofencing | "Location-based reminders" |
| `ACCESS_BACKGROUND_LOCATION` | Geofence triggers | "Reminders work when app closed" |
| `BLUETOOTH_CONNECT` | Pebble Ring, AirPods | "Connect to your devices" |
| `INTERNET` | MUXI backend | "MUXI needs internet" |
| `POST_NOTIFICATIONS` | Service notification | "Required for background service" |
| `RECEIVE_BOOT_COMPLETED` | Auto-start | "MUXI starts with your phone" |

---

## User Interface

### Design Principles

1. **Minimal by default** — The app is not the experience; MUXI is
2. **Voice-first** — UI is for configuration, not daily use
3. **Status at a glance** — Persistent notification shows MUXI is ready
4. **Settings when needed** — Easy access to permissions and preferences

### Screens

#### Home Screen
- MUXI status indicator (listening / processing / speaking)
- Large voice activation button (fallback)
- Quick settings toggle (mute, pause, etc.)
- Recent interactions (collapsed by default)

#### Settings Screen
- Permission status and management
- Audio routing preferences
- Wake word configuration
- App exclusion list (don't read these apps)
- Location/place management
- MDA connection status
- Debug/logs (hidden by default)

#### Onboarding Flow
1. Welcome + value prop
2. Permission grants (one at a time, explain each)
3. MDA pairing (optional)
4. Voice test
5. Ready

### Persistent Notification

```
┌─────────────────────────────────────────┐
│ 🟢 MUXI                                 │
│ Listening • Tap to open                 │
│                                         │
│ [Mute]  [Pause]  [Settings]             │
└─────────────────────────────────────────┘
```

---

## Phased Delivery

### Phase 1: Core Voice Loop (Weeks 1-4)

**Goal:** Basic voice conversation with MUXI works

**Deliverables:**
- [ ] Foreground service architecture
- [ ] Voice capture and streaming to backend
- [ ] TTS playback with media ducking
- [ ] Basic UI (status, voice button)
- [ ] Persistent notification

**Success Criteria:**
- Can have voice conversation with MUXI
- Service survives app kills
- Audio routes to Bluetooth when connected

### Phase 2: Context Awareness (Weeks 5-8)

**Goal:** MUXI knows what you're looking at

**Deliverables:**
- [ ] Accessibility Service implementation
- [ ] Screen content extraction
- [ ] Context sent with voice queries
- [ ] App exclusion list
- [ ] Notification Listener implementation
- [ ] Notification aggregation and summary

**Success Criteria:**
- "What's this?" works with screen context
- "What did I miss?" summarizes notifications
- Privacy exclusions respected

### Phase 3: Location & Reminders (Weeks 9-10)

**Goal:** Location-based reminders work

**Deliverables:**
- [ ] Geofencing implementation
- [ ] Named places
- [ ] Reminder creation and triggering
- [ ] Location reporting to MUXI

**Success Criteria:**
- "Remind me when I leave" works
- Geofences trigger reliably

### Phase 4: Integration (Weeks 11-12)

**Goal:** Full ecosystem integration

**Deliverables:**
- [ ] Pebble Ring SDK integration
- [ ] MDA sync (clipboard, reminders)
- [ ] Media control
- [ ] Home room detection (WiFi fingerprinting)

**Success Criteria:**
- Ring input works
- Clipboard syncs with Mac
- "Play music" controls Spotify

### Phase 5: Polish (Weeks 13-14)

**Goal:** Production-ready

**Deliverables:**
- [ ] Onboarding flow
- [ ] Battery optimization
- [ ] Error handling and recovery
- [ ] Audit logging
- [ ] Documentation

**Success Criteria:**
- < 5% battery per day
- Graceful error recovery
- User understands all permissions

---

## Dependencies

### External

| Dependency | Status | Risk |
|------------|--------|------|
| MUXI Backend voice endpoint | Exists | Low |
| Pebble Ring SDK | Ships March 2026 | Medium - may need stubbing |
| Clicks Communicator | Ships Q1-Q2 2026 | Medium - develop on other Android |
| MDA | In development | Low - sync can be added later |

### Internal

| Dependency | Owner | Notes |
|------------|-------|-------|
| MUXI voice streaming protocol | Backend team | WebSocket spec needed |
| MUXI context format | Backend team | JSON schema for screen context |
| TTS provider | Backend team | ElevenLabs? On-device? |

---

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Pebble Ring SDK delayed | Can't integrate ring input | Medium | Clicks side button as primary, ring as enhancement |
| Battery drain too high | Poor UX | Medium | Aggressive optimization, user controls |
| Accessibility Service rejected by Play Store | Can't distribute normally | Low | Sideload, or justify legitimate use case |
| Clicks delayed | No target device | Medium | Develop on Pixel, adapt later |
| MUXI latency too high | Poor voice UX | Medium | Local caching, optimistic UI |

---

## Open Questions

1. **Wake word:** Build custom or use existing engine (Porcupine, etc.)?
2. **TTS:** Backend-generated or on-device?
3. **Offline mode:** What works without internet?
4. **Multi-user:** Will this ever support multiple users on one device?
5. **Play Store:** Submit to store or sideload only?

---

## Appendix A: Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Kotlin |
| Min SDK | Android 13 (API 33) |
| Target SDK | Android 16 (API 36) |
| Architecture | MVVM + Clean Architecture |
| DI | Hilt |
| Networking | OkHttp + WebSocket |
| Local Storage | Room + DataStore |
| Audio | Android AudioRecord + MediaPlayer |
| Location | Google Play Services Location |
| Background | WorkManager + Foreground Service |

---

## Appendix B: API Contracts

### MUXI Voice Endpoint

**WebSocket:** `wss://api.muxi.ai/v1/voice`

**Client → Server (Audio)**
```json
{
  "type": "audio",
  "data": "<base64 audio chunk>",
  "format": "pcm_16khz_mono"
}
```

**Client → Server (Context)**
```json
{
  "type": "context",
  "screen": {
    "app": "com.google.android.gm",
    "app_name": "Gmail",
    "text": "From: john@example.com\nSubject: Q1 Budget...",
    "structured": {
      "type": "email",
      "sender": "john@example.com",
      "subject": "Q1 Budget Review"
    }
  },
  "location": {
    "lat": 51.5074,
    "lng": -0.1278,
    "place": "Office"
  },
  "notifications_pending": 12
}
```

**Server → Client (Response)**
```json
{
  "type": "response",
  "text": "This email from John discusses...",
  "audio": "<base64 tts audio>",
  "actions": [
    {
      "type": "open_url",
      "url": "https://..."
    }
  ]
}
```

---

## Appendix C: Accessibility Service Events

Events to capture:
- `TYPE_WINDOW_STATE_CHANGED` — App/screen changes
- `TYPE_WINDOW_CONTENT_CHANGED` — Content updates
- `TYPE_VIEW_TEXT_CHANGED` — Text input changes

Node traversal strategy:
1. Get root node of active window
2. Recursively traverse children
3. Extract text from `TextView`, `EditText`, etc.
4. Build structured representation where possible

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | Jan 2026 | Ran Aroussi | Initial draft |