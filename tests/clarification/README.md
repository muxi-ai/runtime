# Real-World Clarification Testing Scenarios

## 🎉 Status: ALL TESTS PASSING!

**Overall: 7/7 categories passed** 🎉 **ALL SCENARIOS PASSED!**
**Category 1:** ✅ PASSED
**Category 2:** ✅ PASSED
**Category 3:** ✅ PASSED
**Category 4:** ✅ PASSED
**Category 5:** ✅ PASSED
**Category 6:** ✅ PASSED
**Category 8:** ✅ PASSED


## Overview

Comprehensive test suite for intelligent parameter collection system using **real OpenAI API calls** for authentic decision-making testing. These tests validate the clarification system across 8 major categories of user interactions.

## Key Features

✅ **Real LLM Decision Making** - Uses actual OpenAI GPT-4 calls, no mocking of intelligence
✅ **Authentic Scenarios** - Based on real user interaction patterns
✅ **Comprehensive Coverage** - 8 categories covering 20+ detailed scenarios
✅ **Performance Validation** - Includes success criteria and quality metrics

## Test Categories

### Category 1: MCP Tool Parameter Collection (`test_cat1_mcp_tools.py`)
Tests intelligent parameter collection for MCP tools:
- **Restaurant booking** with missing location, time, party size
- **Flight booking** using user context to minimize questions
- **Wedding planning** with complex multi-parameter workflows
- **Parameter validation** and retry logic

### Category 2: Overlord Clarification & Intent Understanding (`test_cat2_overlord.py`)
Tests ambiguous request resolution and intent routing:
- **Ambiguous Python help** - learning vs debugging vs setup
- **Multi-domain requests** - "start a tech company" routing
- **Context-dependent references** - "Can you do that again?"

### Category 3: Proactive Brainstorming & Collaborative Sessions (`test_cat3_brainstorming.py`)
Tests explicit collaborative questioning modes:
- **Mobile app brainstorming** through strategic questions
- **Career change exploration** via structured interviews
- **Novel planning** through creative collaboration
- **Proactive mode detection** from user requests

### Category 4: Data-First Planning Workflows (`test_cat4_data_planning.py`)
Tests planning that starts with data gathering:
- **Travel planning** with weather and pricing data synthesis
- **Investment research** with market analysis before strategy
- **Business location analysis** with demographic research

### Category 5: Multi-Step Workflows & Dependencies (`test_cat5_multi_step.py`)
Tests complex processes with dependencies:
- **Home buying process** with budget → location → search flow
- **Graduate school applications** with timeline dependencies
- **Progress tracking** across multiple sessions

### Category 6: Error Recovery & Adaptation (`test_cat6_error_recovery.py`)
Tests graceful handling of failures and changes:
- **Failed tool execution** - restaurant fully booked recovery
- **User changes mind** - Paris → Rome flight destination switch
- **Invalid parameters** with helpful corrections
- **Timeout recovery** when external APIs fail

### Category 8: Multilingual & Cultural Scenarios (`test_cat8_multilingual.py`)
Tests language and cultural awareness:
- **Spanish travel planning** with continued Spanish conversation
- **Tokyo business dinner** with cultural etiquette guidance
- **French career consultation** maintaining language
- **Chinese investment planning** with cultural context

## Quick Start

### Run Quick API Test
```bash
python run_real_world_tests.py --quick
```

### Run Single Category
```bash
python run_real_world_tests.py --category 1
```

### Run All Scenarios
```bash
python run_real_world_tests.py
```

### Run Individual Test
```bash
python -m pytest test_cat1_mcp_tools.py::TestMCPToolParameterCollection::test_restaurant_booking_missing_params -v -s
```

## Example Test Output

```
🤖 Analysis: {"missing": ["location", "time", "party_size"], "confidence": 0.95}
🤖 Question: "Could you please tell me the location where you would like the restaurant booking?"
✅ PASSED
```

## Success Criteria

Each test validates:

**For MCP Tool Scenarios:**
- ✅ Correctly identifies missing parameters
- ✅ Asks natural, contextual questions
- ✅ Successfully fills parameters from user responses
- ✅ Executes tools with complete, valid parameters

**For Overlord Clarification:**
- ✅ Recognizes ambiguous or unclear intents
- ✅ Routes to appropriate agents after clarification
- ✅ Maintains context across agent handoffs

**For Brainstorming Scenarios:**
- ✅ Enters proactive questioning mode when requested
- ✅ Asks strategic, goal-oriented questions
- ✅ Builds comprehensive understanding through conversation

**For Data-First Planning:**
- ✅ Identifies implicit planning workflows
- ✅ Gathers relevant data before asking user preferences
- ✅ Synthesizes data into decision-relevant insights
- ✅ Continues planning conversation with context

## Performance Targets

- **Response Time:** < 3 seconds for clarification questions
- **Success Rate:** > 90% task completion after clarification
- **User Satisfaction:** > 4.5/5 rating for conversation naturalness
- **Context Utilization:** > 70% of available context used appropriately

## Technical Details

### Real LLM Integration
```python
class RealOpenAILLM:
    def __init__(self, api_key: str):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key=api_key)

    async def chat(self, messages, **kwargs):
        response = await self.client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.3,
            max_tokens=800
        )
        return response.choices[0].message.content
```

### Test Structure
- Each category has dedicated test class
- Real OpenAI API calls for decision-making
- Mock MCP tools and data sources
- Comprehensive assertions validating LLM responses
- Print statements showing actual LLM outputs

## Dependencies

- `pytest` - Test framework
- `openai` - OpenAI API client
- Real OpenAI API key (provided in test fixtures)

## Architecture Integration

These tests validate the intelligent clarification system described in the implementation plan:
- **Phase 1-3:** Core intelligent parameter collection ✅
- **Phase 4:** Explicit turn-taking & proactive clarification ✅
- **Phase 4B:** Planning workflow detection & continuity ✅
- **Phase 5:** Privacy-focused configuration system ✅

The system features multilingual support, comprehensive test coverage, proper file organization, privacy-by-default configuration, and non-breaking integration with existing Agent architecture.

## Contributing

When adding new scenarios:
1. Use real LLM calls for decision-making
2. Mock external tools/APIs but not intelligence
3. Include comprehensive assertions
4. Add print statements showing LLM responses
5. Follow naming convention: `test_scenario_X_Y_description`
