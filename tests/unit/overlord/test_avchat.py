"""Unit tests for Overlord.avchat() method."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestAVChat:
    """Test suite for the avchat() method."""

    @pytest.fixture
    def mock_overlord(self):
        """Create a mock Overlord instance."""
        # Mock all dependencies at import level
        with patch('muxi.formation.overlord.overlord.ObservabilityManager') as mock_obs, \
             patch('muxi.formation.workflow.manager.WorkflowManager') as mock_wm, \
             patch('muxi.formation.persona.manager.PersonaManager') as mock_pm, \
             patch('muxi.formation.workflow.request_analyzer.RequestAnalyzer') as mock_ra, \
             patch('muxi.formation.workflow.task_decomposer.TaskDecomposer') as mock_td, \
             patch('muxi.formation.workflow.workflow_executor.WorkflowExecutor') as mock_we, \
             patch('muxi.formation.workflow.approval_manager.ApprovalManager') as mock_am, \
             patch('muxi.formation.workflow.progress_tracker.ProgressTracker') as mock_pt, \
             patch('muxi.formation.overlord.clarification.UnifiedClarificationSystem') as mock_cs, \
             patch('muxi.formation.overlord.intent_detector.IntentDetector') as mock_id, \
             patch('muxi.formation.workflow.sops.SOPCoordinator') as mock_sop, \
             patch('muxi.formation.resilience.resilient_executor.ResilientWorkflowExecutor') as mock_rwe:
            
            from muxi.formation.overlord.overlord import Overlord
            
            # Create mocked instances
            mock_obs.return_value = MagicMock()
            
            overlord = Overlord(
                formation_config={'id': 'test'},
                observability=mock_obs.return_value
            )
            # Mock the chat method
            overlord.chat = AsyncMock(return_value="Mocked response")
            return overlord

    @pytest.mark.asyncio
    async def test_audio_file_prompt_generation(self, mock_overlord):
        """Test that audio files generate correct prompts."""
        audio_files = [{
            'content': 'base64_audio',
            'content_type': 'audio/mp3',
            'filename': 'test.mp3'
        }]
        
        await mock_overlord.avchat(files=audio_files, user_id="test")
        
        mock_overlord.chat.assert_called_once()
        call_args = mock_overlord.chat.call_args[1]
        assert call_args['message'] == "Please transcribe this audio and respond to what was said."
        assert call_args['files'] == audio_files

    @pytest.mark.asyncio
    async def test_video_file_prompt_generation(self, mock_overlord):
        """Test that video files generate correct prompts."""
        video_files = [{
            'content': 'base64_video',
            'content_type': 'video/mp4',
            'filename': 'test.mp4'
        }]
        
        await mock_overlord.avchat(files=video_files)
        
        call_args = mock_overlord.chat.call_args[1]
        expected_prompt = "Please analyze this video, transcribe any speech, and respond appropriately to the content."
        assert call_args['message'] == expected_prompt

    @pytest.mark.asyncio
    async def test_custom_prompt_template(self, mock_overlord):
        """Test that custom prompt templates are used."""
        files = [{'content': 'data', 'content_type': 'audio/wav', 'filename': 'audio.wav'}]
        custom_prompt = "Summarize the key points"
        
        await mock_overlord.avchat(files=files, prompt_template=custom_prompt)
        
        call_args = mock_overlord.chat.call_args[1]
        assert call_args['message'] == custom_prompt

    @pytest.mark.asyncio
    async def test_mixed_media_prioritizes_video(self, mock_overlord):
        """Test that video prompt is used when both audio and video are present."""
        mixed_files = [
            {'content': 'audio', 'content_type': 'audio/mp3', 'filename': 'audio.mp3'},
            {'content': 'video', 'content_type': 'video/quicktime', 'filename': 'video.mov'}
        ]
        
        await mock_overlord.avchat(files=mixed_files)
        
        call_args = mock_overlord.chat.call_args[1]
        assert "video" in call_args['message'].lower()

    @pytest.mark.asyncio
    async def test_non_media_files_fallback(self, mock_overlord):
        """Test that non-media files use the fallback prompt."""
        doc_files = [{
            'content': 'pdf_content',
            'content_type': 'application/pdf',
            'filename': 'document.pdf'
        }]
        
        await mock_overlord.avchat(files=doc_files)
        
        call_args = mock_overlord.chat.call_args[1]
        assert call_args['message'] == "Please analyze these files and respond appropriately."

    @pytest.mark.asyncio
    async def test_empty_files_raises_error(self, mock_overlord):
        """Test that empty files list raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            await mock_overlord.avchat(files=[])
        
        assert str(exc_info.value) == "files parameter is required for avchat()"

    @pytest.mark.asyncio
    async def test_no_files_raises_error(self, mock_overlord):
        """Test that None files raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            await mock_overlord.avchat(files=None)
        
        assert "files parameter is required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_all_parameters_passed_through(self, mock_overlord):
        """Test that all parameters are correctly passed to chat()."""
        files = [{'content': 'audio', 'content_type': 'audio/mp3', 'filename': 'test.mp3'}]
        
        await mock_overlord.avchat(
            files=files,
            agent_name='test-agent',
            user_id='user123',
            session_id='session456',
            use_async=True,
            webhook_url='https://example.com/webhook',
            threshold_seconds=10.0,
            stream=True
        )
        
        call_args = mock_overlord.chat.call_args[1]
        assert call_args['agent_name'] == 'test-agent'
        assert call_args['user_id'] == 'user123'
        assert call_args['session_id'] == 'session456'
        assert call_args['use_async'] is True
        assert call_args['webhook_url'] == 'https://example.com/webhook'
        assert call_args['threshold_seconds'] == 10.0
        assert call_args['stream'] is True

    @pytest.mark.asyncio
    async def test_return_value_passthrough(self, mock_overlord):
        """Test that return values are passed through correctly."""
        files = [{'content': 'audio', 'content_type': 'audio/mp3', 'filename': 'test.mp3'}]
        
        # Test string response
        mock_overlord.chat.return_value = "String response"
        result = await mock_overlord.avchat(files=files)
        assert result == "String response"
        
        # Test dict response
        mock_overlord.chat.return_value = {"type": "response", "content": "test"}
        result = await mock_overlord.avchat(files=files)
        assert result == {"type": "response", "content": "test"}

    @pytest.mark.asyncio
    async def test_multiple_audio_formats(self, mock_overlord):
        """Test various audio format detection."""
        audio_formats = [
            ('audio/mp3', 'test.mp3'),
            ('audio/m4a', 'test.m4a'),
            ('audio/wav', 'test.wav'),
            ('audio/ogg', 'test.ogg'),
            ('audio/mpeg', 'test.mpeg')
        ]
        
        for content_type, filename in audio_formats:
            mock_overlord.chat.reset_mock()
            files = [{
                'content': 'audio_data',
                'content_type': content_type,
                'filename': filename
            }]
            
            await mock_overlord.avchat(files=files)
            
            call_args = mock_overlord.chat.call_args[1]
            assert call_args['message'] == "Please transcribe this audio and respond to what was said."

    @pytest.mark.asyncio
    async def test_multiple_video_formats(self, mock_overlord):
        """Test various video format detection."""
        video_formats = [
            ('video/mp4', 'test.mp4'),
            ('video/quicktime', 'test.mov'),
            ('video/webm', 'test.webm'),
            ('video/x-msvideo', 'test.avi')
        ]
        
        for content_type, filename in video_formats:
            mock_overlord.chat.reset_mock()
            files = [{
                'content': 'video_data',
                'content_type': content_type,
                'filename': filename
            }]
            
            await mock_overlord.avchat(files=files)
            
            call_args = mock_overlord.chat.call_args[1]
            expected_prompt = "Please analyze this video, transcribe any speech, and respond appropriately to the content."
            assert call_args['message'] == expected_prompt