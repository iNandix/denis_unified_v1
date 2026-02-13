"""Advanced audio processing: noise reduction, echo cancellation, normalization."""

import numpy as np
from collections import deque
from dataclasses import dataclass
from typing import Optional, Tuple

try:
    import scipy.signal as signal
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    signal = None


@dataclass
class AudioQualityMetrics:
    """Audio quality metrics."""
    
    snr_db: float  # Signal-to-noise ratio
    clipping_ratio: float  # Ratio of clipped samples
    rms_level: float  # RMS level
    peak_level: float  # Peak level
    dynamic_range_db: float  # Dynamic range


class NoiseReduction:
    """Spectral subtraction noise reduction."""
    
    def __init__(
        self,
        sample_rate: int = 16000,
        frame_size: int = 512,
        noise_floor_db: float = -40,
    ):
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.noise_floor_db = noise_floor_db
        
        # Noise profile (learned from initial silence)
        self.noise_profile: Optional[np.ndarray] = None
        self.noise_frames = []
        self.noise_learning_frames = 10
        
        # Smoothing
        self.prev_magnitude: Optional[np.ndarray] = None
        self.smoothing_factor = 0.8
    
    def learn_noise_profile(self, audio_frame: np.ndarray) -> None:
        """Learn noise profile from silence."""
        if len(self.noise_frames) < self.noise_learning_frames:
            self.noise_frames.append(audio_frame)
            
            if len(self.noise_frames) == self.noise_learning_frames:
                # Compute average noise spectrum
                noise_stack = np.vstack(self.noise_frames)
                noise_fft = np.fft.rfft(noise_stack, axis=1)
                self.noise_profile = np.mean(np.abs(noise_fft), axis=0)
    
    def reduce_noise(self, audio_frame: np.ndarray) -> np.ndarray:
        """Apply spectral subtraction."""
        if self.noise_profile is None:
            return audio_frame
        
        # FFT
        fft = np.fft.rfft(audio_frame)
        magnitude = np.abs(fft)
        phase = np.angle(fft)
        
        # Spectral subtraction
        clean_magnitude = magnitude - self.noise_profile
        clean_magnitude = np.maximum(clean_magnitude, magnitude * 0.1)  # Floor
        
        # Smooth
        if self.prev_magnitude is not None:
            clean_magnitude = (
                self.smoothing_factor * self.prev_magnitude
                + (1 - self.smoothing_factor) * clean_magnitude
            )
        self.prev_magnitude = clean_magnitude
        
        # Reconstruct
        clean_fft = clean_magnitude * np.exp(1j * phase)
        clean_audio = np.fft.irfft(clean_fft, len(audio_frame))
        
        return clean_audio


class EchoCancellation:
    """Adaptive echo cancellation using LMS algorithm."""
    
    def __init__(
        self,
        filter_length: int = 512,
        step_size: float = 0.01,
    ):
        self.filter_length = filter_length
        self.step_size = step_size
        
        # Adaptive filter coefficients
        self.w = np.zeros(filter_length)
        
        # Reference signal buffer (far-end/speaker output)
        self.reference_buffer = deque(maxlen=filter_length)
    
    def update_reference(self, reference_signal: np.ndarray) -> None:
        """Update reference signal (what was played)."""
        for sample in reference_signal:
            self.reference_buffer.append(sample)
    
    def cancel_echo(self, microphone_signal: np.ndarray) -> np.ndarray:
        """Cancel echo from microphone signal."""
        if len(self.reference_buffer) < self.filter_length:
            return microphone_signal
        
        output = np.zeros_like(microphone_signal)
        
        for i, mic_sample in enumerate(microphone_signal):
            # Get reference window
            ref_window = np.array(list(self.reference_buffer))
            
            # Estimate echo
            echo_estimate = np.dot(self.w, ref_window)
            
            # Error signal (desired output)
            error = mic_sample - echo_estimate
            output[i] = error
            
            # Update filter (LMS)
            self.w += self.step_size * error * ref_window
            
            # Update buffer
            if i < len(microphone_signal) - 1:
                self.reference_buffer.append(microphone_signal[i + 1])
        
        return output


class AudioNormalizer:
    """Dynamic range compression and normalization."""
    
    def __init__(
        self,
        target_level_db: float = -20,
        threshold_db: float = -30,
        ratio: float = 4.0,
        attack_ms: float = 5,
        release_ms: float = 50,
        sample_rate: int = 16000,
    ):
        self.target_level_db = target_level_db
        self.threshold_db = threshold_db
        self.ratio = ratio
        
        # Attack/release coefficients
        self.attack_coef = np.exp(-1 / (sample_rate * attack_ms / 1000))
        self.release_coef = np.exp(-1 / (sample_rate * release_ms / 1000))
        
        # State
        self.envelope = 0.0
    
    def db_to_linear(self, db: float) -> float:
        """Convert dB to linear scale."""
        return 10 ** (db / 20)
    
    def linear_to_db(self, linear: float) -> float:
        """Convert linear to dB."""
        return 20 * np.log10(max(linear, 1e-10))
    
    def compress(self, audio_frame: np.ndarray) -> np.ndarray:
        """Apply dynamic range compression."""
        output = np.zeros_like(audio_frame)
        
        threshold_linear = self.db_to_linear(self.threshold_db)
        
        for i, sample in enumerate(audio_frame):
            # Envelope follower
            abs_sample = abs(sample)
            if abs_sample > self.envelope:
                self.envelope = (
                    self.attack_coef * self.envelope
                    + (1 - self.attack_coef) * abs_sample
                )
            else:
                self.envelope = (
                    self.release_coef * self.envelope
                    + (1 - self.release_coef) * abs_sample
                )
            
            # Compute gain reduction
            if self.envelope > threshold_linear:
                # Above threshold: compress
                envelope_db = self.linear_to_db(self.envelope)
                excess_db = envelope_db - self.threshold_db
                gain_reduction_db = excess_db * (1 - 1 / self.ratio)
                gain = self.db_to_linear(-gain_reduction_db)
            else:
                gain = 1.0
            
            output[i] = sample * gain
        
        return output
    
    def normalize(self, audio_frame: np.ndarray) -> np.ndarray:
        """Normalize to target level."""
        # Measure current level
        rms = np.sqrt(np.mean(audio_frame ** 2))
        current_db = self.linear_to_db(rms)
        
        # Calculate gain
        gain_db = self.target_level_db - current_db
        gain = self.db_to_linear(gain_db)
        
        # Limit gain to prevent excessive amplification
        gain = min(gain, 10.0)  # Max +20dB
        
        return audio_frame * gain


class AudioQualityAnalyzer:
    """Analyzes audio quality metrics."""
    
    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
    
    def analyze(self, audio_frame: np.ndarray) -> AudioQualityMetrics:
        """Compute audio quality metrics."""
        # RMS level
        rms = np.sqrt(np.mean(audio_frame ** 2))
        rms_db = 20 * np.log10(max(rms, 1e-10))
        
        # Peak level
        peak = np.max(np.abs(audio_frame))
        peak_db = 20 * np.log10(max(peak, 1e-10))
        
        # Dynamic range
        dynamic_range_db = peak_db - rms_db
        
        # Clipping detection
        clipping_threshold = 0.99
        clipped_samples = np.sum(np.abs(audio_frame) > clipping_threshold)
        clipping_ratio = clipped_samples / len(audio_frame)
        
        # SNR estimation (simple)
        # Assume noise is in quietest 10% of samples
        sorted_abs = np.sort(np.abs(audio_frame))
        noise_samples = sorted_abs[:len(sorted_abs) // 10]
        noise_level = np.mean(noise_samples)
        signal_level = rms
        snr = signal_level / max(noise_level, 1e-10)
        snr_db = 20 * np.log10(snr)
        
        return AudioQualityMetrics(
            snr_db=snr_db,
            clipping_ratio=clipping_ratio,
            rms_level=rms,
            peak_level=peak,
            dynamic_range_db=dynamic_range_db,
        )


class AudioProcessor:
    """Complete audio processing pipeline."""
    
    def __init__(
        self,
        sample_rate: int = 16000,
        enable_noise_reduction: bool = True,
        enable_echo_cancellation: bool = False,
        enable_normalization: bool = True,
    ):
        self.sample_rate = sample_rate
        
        # Components
        self.noise_reducer = NoiseReduction(sample_rate) if enable_noise_reduction else None
        self.echo_canceller = EchoCancellation() if enable_echo_cancellation else None
        self.normalizer = AudioNormalizer(sample_rate) if enable_normalization else None
        self.quality_analyzer = AudioQualityAnalyzer(sample_rate)
        
        # State
        self.frames_processed = 0
        self.noise_learning_complete = False
    
    def process_frame(
        self,
        audio_frame: np.ndarray,
        reference_signal: Optional[np.ndarray] = None,
    ) -> Tuple[np.ndarray, AudioQualityMetrics]:
        """Process audio frame through pipeline."""
        processed = audio_frame.copy()
        
        # 1. Learn noise profile (first few frames)
        if self.noise_reducer and not self.noise_learning_complete:
            if self.frames_processed < 10:
                # Assume first frames are silence/noise
                energy = np.sqrt(np.mean(processed ** 2))
                if energy < 0.01:  # Low energy = noise
                    self.noise_reducer.learn_noise_profile(processed)
            else:
                self.noise_learning_complete = True
        
        # 2. Noise reduction
        if self.noise_reducer and self.noise_learning_complete:
            processed = self.noise_reducer.reduce_noise(processed)
        
        # 3. Echo cancellation
        if self.echo_canceller and reference_signal is not None:
            self.echo_canceller.update_reference(reference_signal)
            processed = self.echo_canceller.cancel_echo(processed)
        
        # 4. Compression
        if self.normalizer:
            processed = self.normalizer.compress(processed)
        
        # 5. Normalization
        if self.normalizer:
            processed = self.normalizer.normalize(processed)
        
        # 6. Quality analysis
        quality = self.quality_analyzer.analyze(processed)
        
        self.frames_processed += 1
        
        return processed, quality
    
    def reset(self) -> None:
        """Reset processor state."""
        self.frames_processed = 0
        self.noise_learning_complete = False
        if self.noise_reducer:
            self.noise_reducer.noise_profile = None
            self.noise_reducer.noise_frames = []
