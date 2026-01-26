# MUXI "Her" Vision
## Building a True Personal AI Companion

**Version:** 1.0  
**Date:** January 2026  
**Author:** Ran Aroussi

---

## Executive Summary

This document outlines the vision for transforming MUXI into a "Her"-style personal AI companion—an ambient, always-available intelligence that transcends the traditional app paradigm. Rather than being confined to a chat window, MUXI becomes an omnipresent assistant that speaks, listens, sees context, and acts across all devices and environments.

The goal: **talk to your AI like a person, not a product.**

---

## The Problem with Current AI Assistants

Today's AI assistants are fundamentally limited:

| Assistant | Limitation |
|-----------|------------|
| Siri/Google/Alexa | Reactive only, no memory, can't see context, limited actions |
| ChatGPT/Claude apps | Trapped in a chat window, no device integration, no ambient presence |
| Copilots | Useful but siloed to specific apps |

None of them feel like the AI companion depicted in "Her"—an intelligence that's simply *there*, understanding context, anticipating needs, and communicating naturally.

---

## The Vision

MUXI becomes a single intelligent layer spanning all your devices and environments:

```
┌─────────────────────────────────────────────────────────────┐
│                          MUXI                               │
│            (one agent, everywhere, knows everything)        │
└─────────────────────────────────────────────────────────────┘
         │              │              │              │
         ▼              ▼              ▼              ▼
    ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐
    │ Mobile  │   │ Desktop │   │  Home   │   │ Wearable│
    │ (MMA)   │   │  (MDA)  │   │  (MHA)  │   │ (Ring/  │
    │         │   │         │   │         │   │  Watch) │
    └─────────┘   └─────────┘   └─────────┘   └─────────┘
```

**Key principles:**

1. **Voice-first, screen-optional** — Speak naturally, get spoken responses
2. **Context-aware** — Knows what you're looking at, where you are, what you're doing
3. **Proactive** — Doesn't just respond; initiates when relevant
4. **Ambient** — Present in the environment, not trapped in a device
5. **Unified** — One agent, one memory, one relationship—across everything

---

## Why Android First

iOS is architecturally hostile to this vision. Android enables it.

### The Technical Reality

| Capability | iOS | Android |
|------------|-----|---------|
| Speak proactively without user action | ❌ Requires hacks | ✅ Native |
| Duck music, speak, resume automatically | ⚠️ Limited | ✅ Native |
| Control any media playback | ⚠️ Apple Music only | ✅ MediaSession API |
| Read screen content | ❌ Impossible | ✅ Accessibility Service |
| Auto-open apps from background | ❌ Blocked | ⚠️ With notification |
| Perform actions in other apps | ❌ Impossible | ✅ Accessibility Service |
| Read all notifications | ❌ Blocked | ✅ Notification Listener |
| Persistent background service | ❌ Killed aggressively | ✅ Foreground service |

### What This Enables

With Android's Accessibility Service, MUXI can:

- **See what you see** — Read any app's screen content
- **Know your context** — Which app is open, what you're looking at
- **Take actions** — Tap buttons, fill forms, navigate apps
- **Aggregate messages** — Read WhatsApp, Telegram, SMS, email—all of them
- **Control media** — Play, pause, skip on Spotify, YouTube, anything

This isn't a workaround. This is the correct architecture for an AI companion.

### The "Her" Gap Analysis

| "Her" Capability | iOS | Android |
|------------------|-----|---------|
| Samantha speaks unprompted | ❌ | ✅ |
| Samantha knows what Theodore is looking at | ❌ | ✅ |
| Samantha controls his environment | ❌ | ✅ |
| Seamless voice conversation | ⚠️ Hacky | ✅ |
| Ambient presence (room speakers) | ⚠️ Limited | ✅ |

**Verdict:** Android is the only viable platform for the "Her" experience today.

---

## Hardware Stack

### Primary Device: Clicks Communicator

The Clicks Communicator is purpose-built for this use case:

- **4.03" screen** — "Designed for doing, not doomscrolling"
- **Physical keyboard** — Text-first when voice isn't appropriate
- **Dedicated voice button** — Hold to speak, instant MUXI access
- **Signal LED** — Customizable per-app; MUXI gets its own color
- **Android 16** — Full Accessibility Service support
- **Pocketable form factor** — A tool, not an attention sink

The small screen and keyboard create **intentional friction** for doomscrolling while optimizing for communication.

### Voice Input: Pebble Ring

- Captures voice input via tap or gesture
- Routes to MUXI via Bluetooth → Clicks
- Enables truly hands-free interaction
- Ships March 2026

### Audio Output: Context-Aware Routing

```
┌─────────────────────────────────────────────────────────┐
│                  Audio Routing Logic                    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│   Is Ran connected to Android Auto?                     │
│       YES → Route to car speakers                       │
│       NO  ↓                                             │
│                                                         │
│   Is Ran wearing AirPods/earbuds?                       │
│       YES → Route to earbuds                            │
│       NO  ↓                                             │
│                                                         │
│   Is Ran at home?                                       │
│       YES → Route to room speaker (location-aware)      │
│       NO  ↓                                             │
│                                                         │
│   Default → Phone speaker or queue for later            │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Home Environment: Echo Dots

Existing Echo Dot network repurposed as MUXI output devices:

- 10 speakers throughout the home
- Location awareness via phone position
- MUXI speaks from the room you're in
- No earbuds needed at home—MUXI is ambient

### Quick Glances: Pebble Watch

- Brief notifications from MUXI
- Doesn't require pulling out phone
- Complements the ring for input/output

### Vision Input: Glasses Camera Add-on

A clip-on camera module that attaches to your existing glasses (including prescription varifocals). No need to buy new frames when your prescription changes.

**Requirements:**
- Camera (MUXI sees what you see)
- Microphone (wake word + conversation mode)
- Optional: bone conduction speaker for mobile audio
- No screen (intentional - avoid attention traps)
- Clips to any frame

**Open Source Options:**

| Option | Price | Components | Notes |
|--------|-------|------------|-------|
| **DIY OpenGlass/Omi style** | ~$25-50 | ESP32-S3 Sense + 3D printed mount + battery | Cheapest, full control, clips to any glasses |
| **Omi Glass Dev Kit** | ~$89 | Pre-built ESP32-S3 module, camera, mic | Ready to go, open source firmware |
| **Brilliant Labs Monocle** | ~$99 | Clip-on with camera, mic, Bluetooth | MicroPython programmable, clips to any frame |
| **Seeed Studio XIAO ESP32S3 Sense** | ~$15 | Just the board - camera + mic built in | Smallest option, needs mount + battery |

**DIY Build (Recommended for flexibility):**
```
Components:
• Seeed XIAO ESP32S3 Sense ($15) - has camera + mic built in
• EEMB LP502030 battery ($8) - 250mAh, tiny
• 3D printed mount (free STL files available)
• Optional: bone conduction module (~$15)

Total: ~$25-40
Time: 1-2 hours assembly
```

**Integration with MMA:**
```
Glasses Module (ESP32)
        │
        │ BLE
        ▼
┌─────────────────┐
│      MMA        │
│    (Clicks)     │
│                 │
│ • Receives frames (periodic or on-demand)
│ • Receives wake word trigger
│ • Streams to MUXI backend
│ • Controls conversation state
└─────────────────┘
```

The glasses module runs minimal firmware:
- Wake word detection (local, e.g., "Hey MUXI")
- BLE connection to phone
- Camera frame capture on request
- Mic streaming when in ACTIVE state

### In the Car: Android Auto

The car is the ideal "Her" environment - hands occupied, eyes on road, pure voice.

**Integration approach:**
- MMA exposes MUXI as an Android Auto-compatible voice service
- Car's microphone → MUXI
- MUXI responses → Car speakers
- Full context still available (notifications, calendar, messages)

**Car-specific capabilities:**
- "What's on my calendar when I arrive?"
- "Read my messages"
- "Reply to Sarah: Running 10 minutes late"
- "Remind me to grab the dry cleaning when I get home"
- Navigation via deep links to Google Maps / Waze

**Why this matters:**
- 30-60 minutes of captive attention daily (commute)
- No screen interaction needed or wanted
- Natural voice conversation while driving
- MUXI becomes the car's AI, not just the phone's

---

## System Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         MUXI Backend                            │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │   Agent     │  │   Memory    │  │   Skills    │              │
│  │   Core      │  │   System    │  │   Engine    │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │   Voice     │  │   Context   │  │   Device    │              │
│  │   Pipeline  │  │   Manager   │  │   Sync      │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
          │                   │                   │
          ▼                   ▼                   ▼
   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
   │     MMA     │     │     MDA     │     │     MHA     │
   │   Mobile    │     │   Desktop   │     │    Home     │
   │    Agent    │     │    Agent    │     │    Agent    │
   └─────────────┘     └─────────────┘     └─────────────┘
```

### MMA (MUXI Mobile Agent)

The primary portable interface, running on the Clicks Communicator.

```
┌─────────────────────────────────────────────────────┐
│                         MMA                         │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │   Voice     │  │   Screen    │  │   Notify    │  │
│  │   Service   │  │   Reader    │  │   Listener  │  │
│  │             │  │             │  │             │  │
│  │ • Pebble    │  │ • A11y API  │  │ • All apps  │  │
│  │   Ring      │  │ • Context   │  │ • Triage    │  │
│  │ • Side btn  │  │   capture   │  │ • Aggregate │  │
│  │ • Wake word │  │ • Actions   │  │ • Summarize │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  │
│                                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │   Audio     │  │   Location  │  │   Sync      │  │
│  │   Output    │  │   Service   │  │   Engine    │  │
│  │             │  │             │  │             │  │
│  │ • TTS       │  │ • Geofence  │  │ • MDA link  │  │
│  │ • Duck/speak│  │ • Room      │  │ • Clipboard │  │
│  │ • Route     │  │   detect    │  │ • Files     │  │
│  │   selection │  │ • Reminders │  │ • Reminders │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  │
│                                                     │
└─────────────────────────────────────────────────────┘
```

**Key capabilities:**

- Always-on foreground service
- Voice input via Pebble Ring or hardware button
- Screen context via Accessibility Service
- Notification aggregation and triage
- Location-based reminders via Geofencing API
- Audio routing (earbuds vs. phone speaker)
- Bidirectional sync with MDA

### MDA (MUXI Desktop Agent)

The desktop companion, running on macOS.

```
┌─────────────────────────────────────────────────────┐
│                         MDA                         │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │   System    │  │   App       │  │   Sync      │  │
│  │   Control   │  │   Bridge    │  │   Engine    │  │
│  │             │  │             │  │             │  │
│  │ • Clipboard │  │ • Notes     │  │ • MMA link  │  │
│  │ • Files     │  │ • Reminders │  │ • Clipboard │  │
│  │ • Apps      │  │ • Calendar  │  │ • Files     │  │
│  │ • Scripts   │  │ • Mail      │  │ • State     │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  │
│                                                     │
└─────────────────────────────────────────────────────┘
```

**Key capabilities:**

- Persistent daemon
- Apple ecosystem bridge (Notes, Reminders, Calendar)
- Clipboard sync with MMA
- File transfer coordination
- AppleScript/Shortcuts execution
- Local audio output when at desk

### MHA (MUXI Home Agent)

The ambient home presence, coordinating room-based audio.

```
┌───────────────────────────────────────────────────────┐
│                         MHA                           │
├───────────────────────────────────────────────────────┤
│                                                       │
│  ┌─────────────────────────────────────────────────┐  │
│  │              Home Hub (Mac Mini)                │  │
│  │                                                 │  │
│  │  • Location tracking (via MMA position)         │  │
│  │  • Audio routing to Echo Dots                   │  │
│  │  • Home automation integration                  │  │
│  │  • Local processing when possible               │  │
│  └─────────────────────────────────────────────────┘  │
│                                                       │
│         │              │              │               │
│         ▼              ▼              ▼               │
│    ┌─────────┐   ┌─────────┐   ┌─────────┐            │
│    │ Office  │   │ Kitchen │   │ Bedroom │   ...      │
│    │ Echo    │   │ Echo    │   │ Echo    │            │
│    └─────────┘   └─────────┘   └─────────┘            │
│                                                       │
└───────────────────────────────────────────────────────┘
```

**Key capabilities:**

- Receives location updates from MMA
- Routes MUXI audio to appropriate room speaker
- Integrates with existing Echo Dot network
- Optional: home automation triggers

---

## Interaction Flows

### Flow 1: Voice Query (Mobile)

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│ Pebble  │────▶│  MMA    │────▶│  MUXI   │────▶│  MMA    │
│  Ring   │     │         │     │ Backend │     │         │
│         │     │ Voice   │     │         │     │  TTS    │
│  Tap +  │     │ capture │     │ Process │     │ Output  │
│  Speak  │     │         │     │         │     │         │
└─────────┘     └─────────┘     └─────────┘     └─────────┘
                                                     │
                                                     ▼
                                               ┌─────────┐
                                               │ AirPods │
                                               │   or    │
                                               │ Speaker │
                                               └─────────┘
```

### Flow 2: Context-Aware Response

```
┌─────────────────────────────────────────────────────────┐
│ User is looking at an email on Clicks                   │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ MMA Accessibility Service captures:                     │
│ • App: Gmail                                            │
│ • Sender: john@example.com                              │
│ • Subject: Q1 Budget Review                             │
│ • Body: [first 500 chars]                               │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ User: "What's this about?"                              │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ MUXI receives:                                          │
│ • Voice transcript                                      │
│ • Screen context                                        │
│ • Current app                                           │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ MUXI responds with summary, speaks via TTS              │
└─────────────────────────────────────────────────────────┘
```

### Flow 3: Location-Based Reminder

```
┌─────────────────────────────────────────────────────────┐
│ User: "Remind me to buy milk when I leave the office"   │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ MUXI:                                                   │
│ • Parses intent                                         │
│ • Identifies "office" location (learned)                │
│ • Creates reminder with EXIT geofence                   │
│ • Syncs to MDA → Apple Reminders (optional)             │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ MMA:                                                    │
│ • Registers geofence via Android API                    │
│ • Monitors in background                                │
└─────────────────────────────────────────────────────────┘
                         │
            [User leaves office]
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ MMA:                                                    │
│ • Geofence triggers                                     │
│ • Notifies MUXI                                         │
│ • MUXI speaks: "Don't forget to buy milk"               │
└─────────────────────────────────────────────────────────┘
```

### Flow 4: Home Ambient Interaction

```
┌─────────────────────────────────────────────────────────┐
│ User walks into kitchen                                 │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ MMA detects location change:                            │
│ • WiFi fingerprint: Kitchen                             │
│ • Updates MUXI: "Ran is in kitchen"                     │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ User: "What's on my calendar today?"                    │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ MUXI:                                                   │
│ • Processes query                                       │
│ • Knows user is at home, in kitchen                     │
│ • Routes response to MHA                                │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ MHA:                                                    │
│ • Receives audio                                        │
│ • Routes to Kitchen Echo Dot                            │
│ • MUXI speaks from the room speaker                     │
└─────────────────────────────────────────────────────────┘
```

### Flow 5: Cross-Device Continuity

```
┌─────────────────────────────────────────────────────────┐
│ User copies text on Mac                                 │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ MDA:                                                    │
│ • Detects clipboard change                              │
│ • Syncs to MUXI backend                                 │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ User (on Clicks): "Paste what I just copied"            │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ MMA:                                                    │
│ • Receives clipboard content from MUXI                  │
│ • Pastes via Accessibility Service                      │
└─────────────────────────────────────────────────────────┘
```

---

## What This Replaces

### Apple Continuity → MUXI Continuity

| Apple Feature | MUXI Replacement |
|---------------|------------------|
| Universal Clipboard | MDA ↔ MMA sync via MUXI |
| AirDrop | "MUXI, send this to my Mac" |
| Handoff | MUXI knows context on all devices |
| iMessage on Mac | WhatsApp/Signal + MUXI aggregation |
| Phone calls on Mac | MUXI routes calls, audio to any device |
| Apple Reminders | MUXI reminders with geofencing, synced to Apple via MDA |

### Siri/Google/Alexa → MUXI

| Legacy Assistant | MUXI Advantage |
|------------------|----------------|
| Reactive only | Proactive—initiates when relevant |
| No memory | Full conversation history and context |
| Can't see screen | Reads any app via Accessibility |
| Limited actions | Controls any app via Accessibility |
| Siloed to ecosystem | Works across Android, Mac, home |

---

## Privacy & Security Considerations

This architecture grants MUXI significant access. Safeguards:

1. **Local processing where possible** — Voice transcription, wake word detection
2. **User-controlled permissions** — Granular control over what MUXI can see/do
3. **Encrypted sync** — All MMA ↔ MDA ↔ Backend communication encrypted
4. **On-device option** — Future: run MUXI models locally for sensitive operations
5. **Audit log** — User can review what MUXI has accessed

---

## Success Metrics

How do we know if this is working?

1. **Screen time reduction** — Less time staring at phones
2. **Voice interaction ratio** — More voice, less touch
3. **Proactive value** — MUXI-initiated interactions that users find helpful
4. **Cross-device fluidity** — Seamless context switching without friction
5. **Doomscroll elimination** — Clicks form factor + MUXI makes mindless scrolling painful

---

## Timeline

```
January 2026 ─────────────────────────────────────────────────►

     │                    │                    │
     ▼                    ▼                    ▼
   Now                 March               Q2 2026
                       2026
                       
 • Architecture       • Pebble Ring        • Clicks ships
   finalized            ships              • Full stack
 • MMA development    • Ring               • integration
   begins               integration        • Home audio
 • MDA v1             • MHA                  routing
                        development        • Public beta
```

---

## Conclusion

This isn't about switching from iPhone to Android. It's about transcending the device paradigm entirely.

The phone becomes a compute node. The earbuds become optional. The screen becomes secondary. **MUXI becomes the interface.**

When this works, you won't think about which device to use. You'll just talk to MUXI, and things will happen.

That's the "Her" vision. That's what we're building.