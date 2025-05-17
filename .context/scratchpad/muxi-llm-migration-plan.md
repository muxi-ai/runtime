
## Multi-Modal Implementation Plan

This section outlines the detailed plan for implementing multi-modal support in the MUXI framework using the muxi-llm package.

### 1. Technical Requirements

1.1. **Core Functionality**:

- Support for image inputs (PNG, JPEG, WebP, etc.)
- Support for audio inputs (MP3, WAV, etc. where applicable)
- Note: This is separate from WebRTC support, which would be handled as a different feature
  - Audio inputs here refer only to file-based audio processing via LLMs
- Support for document inputs (PDF, DOCX, TXT, etc.)
  - Implementation would include document parsing before sending to LLMs
  - Content extraction would be handled by separate utilities
- Support for mixed content message construction (text + images + audio + documents)
- Support for model-specific content handling differences

1.2. **Provider & Model Support**:

- Defer completely to muxi-llm for supported providers and models
- Framework should automatically support any provider/model that muxi-llm supports
- No hard-coding of specific providers or models in the MUXI framework

### 2. Implementation Approach

#### 2.1 Messages with Multi-Modal Content

In the muxi-llm package, multi-modal content is handled through the message format structure, as seen in the ChatCompletion class. The key approach is to use a list of content items in the message structure:

```python
# Example of a multi-modal message format
messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": "What's in this image?"
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": "https://example.com/image.jpg"
                }
            }
        ]
    }
]
```

This format closely follows OpenAI's API structure for multi-modal content, and the muxi-llm package handles the appropriate conversions for different providers.

#### 2.2 Updates to Core LLM Class

Enhance the LLM class to support multi-modal messaging:

```python
# In packages/core/muxi/core/llm.py

class LLM:
    # Existing methods...

    async def chat(self, message=None, messages=None, **kwargs):
        """
        Chat with the model using either a single message or conversation history.

        Args:
            message: A single message (can be text or multi-modal content)
            messages: A list of message objects for conversation history
            **kwargs: Additional parameters for the model

        Returns:
            The model's response
        """
        # Convert our message format to muxi-llm message format
        if message is not None:
            # Handle both text and multi-modal messages
            if isinstance(message, str):
                # Simple text message
                user_message = {"role": "user", "content": message}
            elif isinstance(message, dict) and "content" in message:
                # Already in message format with content
                user_message = message
            elif isinstance(message, list):
                # List of content items (multi-modal)
                user_message = {"role": "user", "content": message}
            else:
                raise ValueError("Unsupported message format")

            if messages is None:
                messages = [user_message]
            else:
                messages = messages + [user_message]

        # Pass to muxi-llm ChatCompletion
        response = await self.client.chat.completions.acreate(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            **kwargs
        )

        return response.choices[0].message.content
```

#### 2.3 Helper Methods for Multi-Modal Content

Add helper methods to simplify creating multi-modal content:

```python
# In packages/core/muxi/core/llm.py

class LLM:
    # Existing methods...

    @staticmethod
    def text_content(text):
        """Create a text content item"""
        return {"type": "text", "text": text}

    @staticmethod
    def image_url_content(url):
        """Create an image_url content item"""
        return {"type": "image_url", "image_url": {"url": url}}

    @staticmethod
    def image_path_content(path):
        """Create an image content item from a local file"""
        import base64
        from pathlib import Path

        # Read and encode the image
        image_path = Path(path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image file not found: {path}")

        with open(image_path, "rb") as f:
            image_data = f.read()

        # Get the MIME type based on file extension
        mime_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".gif": "image/gif"
        }.get(image_path.suffix.lower(), "application/octet-stream")

        # Encode as base64
        base64_data = base64.b64encode(image_data).decode("utf-8")

        # Create the content item with data URI
        return {
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime_type};base64,{base64_data}"
            }
        }
```

#### 2.4 Agent Class Updates

Extend the Agent class to support multi-modal inputs:

```python
# In packages/core/muxi/core/agent.py

class Agent:
    # Existing methods...

    async def process_multi_modal_message(self, content_items, user_id=None):
        """
        Process a multi-modal message.

        Args:
            content_items: List of content items (text, images, etc.)
            user_id: Optional user ID for multi-user systems

        Returns:
            The agent's response
        """
        # Ensure content_items is a list
        if not isinstance(content_items, list):
            content_items = [content_items]

        # Create a message with the content items
        message = {"role": "user", "content": content_items}

        # Process with model
        response = await self.model.chat(message=message)

        # Add to memory if available
        if self.overlord and self.overlord.buffer_memory:
            # Extract text representation for memory
            text_representation = self._get_text_representation(content_items)

            # Store in memory with metadata
            await self.overlord.add_to_buffer_memory(
                text_representation,
                metadata={
                    "type": "multi_modal",
                    "content_types": [item.get("type") for item in content_items],
                    "timestamp": time.time(),
                    "agent_id": self.agent_id
                },
                agent_id=self.agent_id
            )

        return response

    def _get_text_representation(self, content_items):
        """Extract text representation from multi-modal content"""
        parts = []
        for item in content_items:
            if item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif item.get("type") == "image_url":
                parts.append("[IMAGE]")
        return "\n".join(parts) if parts else "[MULTI-MODAL CONTENT]"
```

#### 2.5 Overlord Updates

Add support for multi-modal message processing in the Overlord class:

```python
# In packages/core/muxi/core/overlord.py

class Overlord:
    # Existing methods...

    async def process_multi_modal_message(self, agent_id, content_items):
        """
        Process a multi-modal message using a specific agent.

        Args:
            agent_id: The ID of the agent to use
            content_items: List of content items (text, images, etc.)

        Returns:
            The agent's response
        """
        # Get the agent
        if agent_id not in self.agents:
            raise ValueError(f"No agent with ID '{agent_id}' exists")

        agent = self.agents[agent_id]

        # Process the multi-modal message
        return await agent.process_multi_modal_message(content_items)

    async def chat_with_image(self, text, image_path, agent_id=None):
        """
        Convenience method for text + image chat.

        Args:
            text: Text message
            image_path: Path to image file
            agent_id: Optional agent ID (uses routing if None)

        Returns:
            The agent's response
        """
        # Create content items
        content_items = [
            self.model.text_content(text),
            self.model.image_path_content(image_path)
        ]

        # Select agent if not specified
        if agent_id is None:
            # Extract text for routing (image can't be used for routing)
            agent_id = await self.select_agent_for_message(text)

        # Process the message
        return await self.process_multi_modal_message(agent_id, content_items)
```

### 3. Document Support Implementation

For document support, we'll use the File handling functionality in muxi-llm:

```python
# In packages/core/muxi/core/llm.py

class LLM:
    # Existing methods...

    async def upload_document(self, file_path, purpose="assistants"):
        """
        Upload a document file to the LLM provider.

        Args:
            file_path: Path to the document file (PDF, DOCX, TXT, etc.)
            purpose: Purpose of the file (default: "assistants")

        Returns:
            File object from the provider
        """
        from muxi_llm.files import File

        # Extract provider from model string
        provider = self.model.split('/')[0]

        # Upload the file
        return await File.aupload(
            file=file_path,
            purpose=purpose,
            provider=provider
        )

    async def chat_with_document(self, message, file_id, **kwargs):
        """
        Chat with the model using a document reference.

        Args:
            message: User message text
            file_id: ID of the previously uploaded document file
            **kwargs: Additional parameters for the model

        Returns:
            The model's response
        """
        # Create message with file reference
        messages = [
            {
                "role": "user",
                "content": message,
                "file_ids": [file_id]
            }
        ]

        # Process with the model
        return await self.chat(messages=messages, **kwargs)
```

### 4. Testing Plan

#### 4.1 Unit Tests

Create comprehensive unit tests for multi-modal functionality:

```python
# In tests/test_multi_modal.py

import unittest
from muxi.core.llm import LLM

class TestMultiModalSupport(unittest.TestCase):
    def setUp(self):
        self.model = LLM(model="openai/gpt-4o")

    def test_content_creation(self):
        """Test creation of different content types"""
        text = self.model.text_content("Hello")
        self.assertEqual(text["type"], "text")
        self.assertEqual(text["text"], "Hello")

        image = self.model.image_url_content("https://example.com/image.jpg")
        self.assertEqual(image["type"], "image_url")
        self.assertEqual(image["image_url"]["url"], "https://example.com/image.jpg")

    async def test_chat_with_image(self):
        """Test chat with image input"""
        content = [
            self.model.text_content("What's in this image?"),
            self.model.image_path_content("test_files/test_image.jpg")
        ]
        response = await self.model.chat(message={"role": "user", "content": content})
        self.assertIsNotNone(response)
```

#### 4.2 Integration Tests

Test the full system with multi-modal inputs:

```python
# In tests/test_integration_multi_modal.py

import unittest
from muxi.core.overlord import Overlord
from muxi.core.llm import LLM

class TestMultiModalIntegration(unittest.TestCase):
    async def setUp(self):
        self.model = LLM(model="openai/gpt-4o")
        self.overlord = Overlord()
        self.agent = self.overlord.create_agent(
            agent_id="test_agent",
            model=self.model
        )

    async def test_agent_image_processing(self):
        """Test agent processing an image"""
        content = [
            self.model.text_content("Describe this image"),
            self.model.image_path_content("test_files/test_image.jpg")
        ]
        response = await self.agent.process_multi_modal_message(content)
        self.assertIsNotNone(response)

    async def test_overlord_convenience_method(self):
        """Test the overlord's chat_with_image method"""
        response = await self.overlord.chat_with_image(
            "What's in this image?",
            "test_files/test_image.jpg",
            agent_id="test_agent"
        )
        self.assertIsNotNone(response)
```

### 5. Example Creation

#### 5.1 Basic Image Example

Create an example showing basic image input:

```python
# examples/image_input.py

import asyncio
import os
from dotenv import load_dotenv
from muxi.core.overlord import Overlord
from muxi.core.llm import LLM, set_llm_api_key

# Load environment variables
load_dotenv()

# Set API key
set_llm_api_key(os.getenv("OPENAI_API_KEY", ""), "openai")

async def main():
    # Create model and overlord
    model = LLM(model="openai/gpt-4o")
    overlord = Overlord()

    # Create vision-capable agent
    agent = overlord.create_agent(
        agent_id="vision_agent",
        model=model,
        system_message="You are a helpful assistant that can analyze images."
    )

    # Create content items
    content_items = [
        model.text_content("What's in this image?"),
        model.image_path_content("examples/assets/sample_image.jpg")
    ]

    # Process multi-modal message
    response = await agent.process_multi_modal_message(content_items)

    # Print response
    print(f"Agent response: {response}")

if __name__ == "__main__":
    asyncio.run(main())
```

#### 5.2 Document Processing Example

Create an example with document processing:

```python
# examples/document_processing.py

import asyncio
import os
from dotenv import load_dotenv
from muxi.core.overlord import Overlord
from muxi.core.llm import LLM, set_llm_api_key

# Load environment variables
load_dotenv()

# Set API key
set_llm_api_key(os.getenv("OPENAI_API_KEY", ""), "openai")

async def main():
    # Create model and overlord
    model = LLM(model="openai/gpt-4o")
    overlord = Overlord()

    # Create document-capable agent
    agent = overlord.create_agent(
        agent_id="document_agent",
        model=model,
        system_message="You are a helpful assistant that can analyze documents."
    )

    # Upload document
    print("Uploading document...")
    file_obj = await model.upload_document("examples/assets/sample_document.pdf")
    file_id = file_obj.id
    print(f"Document uploaded with ID: {file_id}")

    # Process with document
    response = await model.chat_with_document(
        "Summarize the main points of this document",
        file_id
    )

    # Print response
    print(f"Agent response: {response}")

if __name__ == "__main__":
    asyncio.run(main())
```

### 6. Documentation

Create comprehensive documentation for the multi-modal features:

```markdown
# Multi-Modal Support in MUXI Framework

This guide explains how to use multi-modal capabilities in the MUXI Framework.

## Supported Content Types

- **Text**: Regular text inputs
- **Images**: JPEG, PNG, WebP formats
- **Documents**: PDF, DOCX, TXT (via file upload)

## Basic Usage

### Creating Content Items

```python
# With an LLM instance
model = LLM(model="openai/gpt-4o")

# Text content
text_content = model.text_content("Describe this image")

# Image content (multiple methods)
image_url_content = model.image_url_content("https://example.com/image.jpg")
image_path_content = model.image_path_content("/path/to/image.jpg")
```

### Using with Chat

```python
# Create content items list
content_items = [
    model.text_content("What's in this image?"),
    model.image_path_content("image.jpg")
]

# Chat with multi-modal content
response = await model.chat(message={"role": "user", "content": content_items})
```

### Using with Agents

```python
# Process with agent
response = await agent.process_multi_modal_message(content_items)
```

### Convenience Methods

```python
# Using Overlord's helper method for image chat
response = await overlord.chat_with_image(
    "Analyze this image",
    "image.jpg",
    agent_id="vision_agent"
)
```

### Document Processing

```python
# Upload a document
file_obj = await model.upload_document("document.pdf")

# Chat with reference to the document
response = await model.chat_with_document(
    "Summarize this document",
    file_obj.id
)
```


### 7. Implementation Steps

- Implement LLM class updates for multi-modal support
- Implement Agent and Overlord multi-modal methods
- Implement document handling capabilities
- Create unit and integration tests
- Develop example applications
- Write documentation

### 8. Dependencies

- Access to multi-modal capable API keys for testing (OpenAI)
- Sample image and document files for examples and tests
- Fully functional muxi-llm package with multi-modal capabilities

### 9. Compatibility Considerations

- Ensure backward compatibility for text-only use cases
- Handle graceful degradation for models without multi-modal support
- Implement proper error handling for unsupported content types
- Provide clear error messages when a provider doesn't support multi-modal inputs

## Next Steps

While the migration is nearly complete, here are some remaining and future tasks:

1. Implement and test multi-modal capabilities
2. Enhance error handling and retry logic for API calls
3. Add more examples showcasing multi-modal capabilities
4. Consider implementing model caching mechanisms
5. Explore fine-tuning support through the unified interface

## Conclusion

The migration to the unified MUXI LLM package is mostly complete. The core LLM integration and API key handling are working, and all tests are passing. Multi-modal support still needs to be implemented and tested, but the framework is now much more consistent with the unified provider/model format.
