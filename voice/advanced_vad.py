"""Advanced Voice Activity Detection with silence detection and speaker diarization."""

import asyncio
import numpy as np
import time
from collections import deque
from dataclasses import dataclass
from typing import List, Optional, Tuple

try:
    import webrtcvad
    WEBRTC_AVAILABLE = True
except ImportError:
    WEBRTC_AVAILABLE = False
    webrtcvad = None


@dataclass
class VADSegment:
    """Voice activity segment."""
    
    start_ms: int
    end_ms: int
    is_speech: bool
    confidence: float
    audio_data: Optional[bytes] = None


@dataclass
class SpeakerSegment:
    """Speaker diarization segment."""
    
    start_ms: int
    end_ms: int
    speaker_id: int
    confidence: float


class AdvancedVAD:
    """Advanced Voice Activity Detection with multiple strategies."""
    
    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        aggressiveness: int = 2,
    ):
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.frame_size = int(sample_rate * frame_duration_ms / 1000)
        
        # WebRTC VAD
        self.vad = None
        if WEBRTC_AVAILABLE:
            self.vad = webrtcvad.Vad(aggressiveness)
        
        # Energy-based VAD parameters
        self.energy_threshold = 0.01
        self.zero_crossing_threshold = 0.1
        
        # Smoothing
        self.speech_buffer = deque(maxlen=10)
        self.min_speech_frames = 3
        self.min_silence_frames = 5
        
        # State
        self.current_segment_start = None
        self.frames_since_speech = 0
        self.frames_since_silence = 0
    
    def detect_speech_energy(self, audio_frame: np.ndarray) -> bool:
        """Energy-based speech detection."""
        # RMS energy
        energy = np.sqrt(np.mean(audio_frame ** 2))
        
        # Zero crossing rate
        zero_crossings = np.sum(np.abs(np.diff(np.sign(audio_frame)))) / len(audio_frame)
        
        is_speech = (
            energy > self.energy_threshold
            and zero_crossing_threshold > self.zero_crossing_threshold
        )
        
        return is_speech
    
    def detect_speech_webrtc(self, audio_bytes: bytes) -> bool:
        """WebRTC VAD detection."""
        if not self.vad:
            return False
        
        try:
            return self.vad.is_speech(audio_bytes, self.sample_rate)
        except Exception:
            return False
    
    def detect_speech_hybrid(
        self,
        audio_frame: np.ndarray,
        audio_bytes: bytes,
    ) -> Tuple[bool, float]:
        """Hybrid detection with confidence score."""
        # WebRTC detection
        webrtc_speech = self.detect_speech_webrtc(audio_bytes)
        
        # Energy detection
        energy_speech = self.detect_speech_energy(audio_frame)
        
        # Combine with voting
        votes = [webrtc_speech, energy_speech]
        speech_votes = sum(votes)
        
        is_speech = speech_votes >= 1  # At least one detector
        confidence = speech_votes / len(votes)
        
        return is_speech, confidence
    
    def process_frame(
        self,
        audio_frame: np.ndarray,
        audio_bytes: bytes,
        timestamp_ms: int,
    ) -> Optional[VADSegment]:
        """Process audio frame and return segment if complete."""
        is_speech, confidence = self.detect_speech_hybrid(audio_frame, audio_bytes)
        
        # Smooth with buffer
        self.speech_buffer.append(is_speech)
        smoothed_speech = sum(self.speech_buffer) > len(self.speech_buffer) / 2
        
        # State machine
        if smoothed_speech:
            self.frames_since_speech += 1
            self.frames_since_silence = 0
            
            if self.current_segment_start is None:
                if self.frames_since_speech >= self.min_speech_frames:
                    # Start new speech segment
                    self.current_segment_start = (
                        timestamp_ms - self.frames_since_speech * self.frame_duration_ms
                    )
        else:
            self.frames_since_silence += 1
            self.frames_since_speech = 0
            
            if self.current_segment_start is not None:
                if self.frames_since_silence >= self.min_silence_frames:
                    # End speech segment
                    segment = VADSegment(
                        start_ms=self.current_segment_start,
                        end_ms=timestamp_ms,
                        is_speech=True,
                        confidence=confidence,
                    )
                    self.current_segment_start = None
                    return segment
        
        return None
    
    def finalize(self, timestamp_ms: int) -> Optional[VADSegment]:
        """Finalize any pending segment."""
        if self.current_segment_start is not None:
            segment = VADSegment(
                start_ms=self.current_segment_start,
                end_ms=timestamp_ms,
                is_speech=True,
                confidence=0.8,
            )
            self.current_segment_start = None
            return segment
        return None


class SilenceDetector:
    """Detects extended silence periods for conversation management."""
    
    def __init__(
        self,
        silence_threshold_ms: int = 2000,
        energy_threshold: float = 0.005,
    ):
        self.silence_threshold_ms = silence_threshold_ms
        self.energy_threshold = energy_threshold
        self.silence_start = None
        self.last_speech_time = time.time()
    
    def process_frame(
        self,
        audio_frame: np.ndarray,
        timestamp_ms: int,
    ) -> Tuple[bool, int]:
        """
        Process frame and return (is_extended_silence, silence_duration_ms).
        """
        energy = np.sqrt(np.mean(audio_frame ** 2))
        
        if energy < self.energy_threshold:
            # Silence
            if self.silence_start is None:
                self.silence_start = timestamp_ms
            
            silence_duration = timestamp_ms - self.silence_start
            is_extended = silence_duration >= self.silence_threshold_ms
            
            return is_extended, silence_duration
        else:
            # Speech detected
            self.silence_start = None
            self.last_speech_time = time.time()
            return False, 0
    
    def get_time_since_speech(self) -> float:
        """Get seconds since last speech."""
        return time.time() - self.last_speech_time


class SimpleSpeakerDiarization:
    """Simple speaker diarization based on audio features."""
    
    def __init__(self, num_speakers: int = 2):
        self.num_speakers = num_speakers
        self.speaker_profiles: List[np.ndarray] = []
        self.current_speaker = 0
    
    def extract_features(self, audio_frame: np.ndarray) -> np.ndarray:
        """Extract simple audio features for speaker identification."""
        # Pitch (fundamental frequency approximation)
        fft = np.fft.rfft(audio_frame)
        freqs = np.fft.rfftfreq(len(audio_frame), 1 / 16000)
        magnitude = np.abs(fft)
        
        # Find dominant frequency (pitch)
        pitch_idx = np.argmax(magnitude[10:]) + 10  # Skip DC and low freqs
        pitch = freqs[pitch_idx]
        
        # Energy
        energy = np.sqrt(np.mean(audio_frame ** 2))
        
        # Zero crossing rate
        zcr = np.sum(np.abs(np.diff(np.sign(audio_frame)))) / len(audio_frame)
        
        # Spectral centroid
        spectral_centroid = np.sum(freqs * magnitude) / np.sum(magnitude)
        
        return np.array([pitch, energy, zcr, spectral_centroid])
    
    def identify_speaker(
        self,
        audio_frame: np.ndarray,
    ) -> Tuple[int, float]:
        """Identify speaker from audio frame."""
        features = self.extract_features(audio_frame)
        
        if len(self.speaker_profiles) == 0:
            # First speaker
            self.speaker_profiles.append(features)
            self.current_speaker = 0
            return 0, 1.0
        
        # Compare with existing profiles
        distances = []
        for profile in self.speaker_profiles:
            # Euclidean distance
            dist = np.linalg.norm(features - profile)
            distances.append(dist)
        
        min_dist = min(distances)
        speaker_id = distances.index(min_dist)
        
        # Threshold for new speaker
        if min_dist > 50 and len(self.speaker_profiles) < self.num_speakers:
            # New speaker
            speaker_id = len(self.speaker_profiles)
            self.speaker_profiles.append(features)
        else:
            # Update profile (EMA)
            self.speaker_profiles[speaker_id] = (
                0.9 * self.speaker_profiles[speaker_id] + 0.1 * features
            )
        
        confidence = 1.0 / (1.0 + min_dist / 10)  # Normalize
        
        return speaker_id, confidence
    
    def process_segment(
        self,
        audio_data: np.ndarray,
        start_ms: int,
        end_ms: int,
    ) -> SpeakerSegment:
        """Process audio segment and identify speaker."""
        # Use middle portion for identification
        mid_start = len(audio_data) // 3
        mid_end = 2 * len(audio_data) // 3
        mid_audio = audio_data[mid_start:mid_end]
        
        speaker_id, confidence = self.identify_speaker(mid_audio)
        
        return SpeakerSegment(
            start_ms=start_ms,
            end_ms=end_ms,
            speaker_id=speaker_id,
            confidence=confidence,
        )


class VoiceActivityManager:
    """Manages all voice activity detection features."""
    
    def __init__(self):
        self.vad = AdvancedVAD()
        self.silence_detector = SilenceDetector()
        self.diarization = SimpleSpeakerDiarization()
        
        self.segments: List[VADSegment] = []
        self.speaker_segments: List[SpeakerSegment] = []
    
    async def process_audio_stream(
        self,
        audio_stream: asyncio.Queue,
    ) -> asyncio.Queue:
        """Process audio stream and output VAD segments."""
        output_queue = asyncio.Queue()
        
        timestamp_ms = 0
        
        while True:
            try:
                audio_chunk = await asyncio.wait_for(
                    audio_stream.get(),
                    timeout=1.0,
                )
                
                if audio_chunk is None:  # End marker
                    # Finalize
                    final_segment = self.vad.finalize(timestamp_ms)
                    if final_segment:
                        await output_queue.put(final_segment)
                    await output_queue.put(None)
                    break
                
                # Convert to numpy
                audio_array = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0
                
                # Process VAD
                segment = self.vad.process_frame(
                    audio_array,
                    audio_chunk,
                    timestamp_ms,
                )
                
                if segment:
                    # Add speaker info
                    speaker_seg = self.diarization.process_segment(
                        audio_array,
                        segment.start_ms,
                        segment.end_ms,
                    )
                    
                    await output_queue.put({
                        "vad_segment": segment,
                        "speaker_segment": speaker_seg,
                    })
                
                # Check silence
                is_silence, duration = self.silence_detector.process_frame(
                    audio_array,
                    timestamp_ms,
                )
                
                if is_silence:
                    await output_queue.put({
                        "type": "extended_silence",
                        "duration_ms": duration,
                    })
                
                timestamp_ms += self.vad.frame_duration_ms
                
            except asyncio.TimeoutError:
                break
        
        return output_queue
