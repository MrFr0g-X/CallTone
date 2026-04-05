"""
Audio emotion detection using nvidia/Audio2Emotion-v3.0 model or alternatives.

This module provides emotion detection for audio segments extracted from 
speaker diarization results.

Supports:
- NVIDIA Audio2Emotion-v3.0 (ONNX-based, works offline)
- HuggingFace wav2vec2 emotion models (open-source fallback)
"""

import os
import warnings
import numpy as np
import torch
import torchaudio
from pathlib import Path
from typing import List, Dict, Tuple, Optional


class Audio2EmotionDetector:
    """
    Detector for audio-based emotion recognition.
    
    Supports multiple backends:
    1. NVIDIA Audio2Emotion-v3.0 (ONNX runtime)
    2. HuggingFace Wav2Vec2 emotion models
    """
    
    def __init__(
        self, 
        model_dir: str = None, 
        device: str = None,
        backend: str = "auto"
    ):
        """
        Initialize the emotion detector.
        
        Args:
            model_dir: Path to model directory
            device: Device to run on ('cuda' or 'cpu'). Auto-detects if None.
            backend: "onnx", "huggingface", or "auto" (default)
        """
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.backend = backend
        self.model = None
        self.processor = None
        self.onnx_session = None
        
        # Emotion labels for NVIDIA model
        self.emotion_labels = [
            "anger", "disgust", "fear", "joy", "neutral", "sadness"
        ]
        
        # Try to load ONNX model (NVIDIA)
        if backend == "auto" or backend == "onnx":
            try:
                self._load_onnx_model(model_dir)
                self.backend = "onnx"
                return
            except Exception as e:
                if backend == "onnx":
                    raise
                warnings.warn(f"Could not load ONNX model: {e}. Falling back to HuggingFace...")
        
        # Fallback to HuggingFace model
        if backend == "auto" or backend == "huggingface":
            try:
                self._load_huggingface_model()
                self.backend = "huggingface"
                return
            except Exception as e:
                if backend == "huggingface":
                    raise
                warnings.warn(f"Could not load HuggingFace model: {e}")
        
        raise RuntimeError(
            "Could not load any emotion detection model. "
            "Please run setup.sh to install dependencies."
        )
    
    def _load_onnx_model(self, model_dir: str = None):
        """Load NVIDIA Audio2Emotion ONNX model."""
        if model_dir is None:
            model_dir = os.path.join(
                os.path.dirname(__file__),
                "models",
                "Audio2Emotion-v3.0"
            )

        self.model_dir = Path(model_dir)

        if not self.model_dir.exists():
            raise FileNotFoundError(
                f"Model directory not found: {self.model_dir}\n"
                f"Please download the model first using download_model.py"
            )

        # Look for ONNX file
        onnx_file = self.model_dir / "network.onnx"
        if not onnx_file.exists():
            raise FileNotFoundError(
                f"ONNX model file not found: {onnx_file}\n"
                f"Expected network.onnx in {self.model_dir}"
            )

        print(f"Loading Audio2Emotion ONNX model from {self.model_dir}")
        print(f"Using device: {self.device}")

        try:
            import onnxruntime as ort

            # Full graph optimization + memory reuse
            opts = ort.SessionOptions()
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            opts.enable_mem_pattern = True
            opts.enable_cpu_mem_arena = False  # use GPU arena instead

            if self.device == 'cuda':
                cuda_opts = {
                    'device_id': 0,
                    'arena_extend_strategy': 'kNextPowerOfTwo',
                    'cudnn_conv_algo_search': 'EXHAUSTIVE',
                    'do_copy_in_default_stream': True,
                }
                providers = [('CUDAExecutionProvider', cuda_opts), 'CPUExecutionProvider']
            else:
                providers = ['CPUExecutionProvider']

            self.onnx_session = ort.InferenceSession(
                str(onnx_file), sess_options=opts, providers=providers
            )

            # Warm-up: run a dummy batch so CUDA kernels are compiled before real data
            if self.device == 'cuda':
                dummy = np.zeros((1, 10000), dtype=np.float32)
                self.onnx_session.run(None, {self.onnx_session.get_inputs()[0].name: dummy})

            # Get input/output names
            self.input_name = self.onnx_session.get_inputs()[0].name
            self.output_name = self.onnx_session.get_outputs()[0].name

            # Per-file audio cache: {(path, sample_rate): np.ndarray}
            self._audio_cache: dict = {}

            print("✓ Audio2Emotion ONNX model loaded successfully")
            print(f"  Model file: {onnx_file.name} ({onnx_file.stat().st_size / 1024**3:.2f} GB)")
            print(f"  Provider:   {self.onnx_session.get_providers()[0]}")
            print(f"  Emotions: {', '.join(self.emotion_labels)}")

        except ImportError:
            raise ImportError(
                "onnxruntime not installed. Install with:\n"
                "  conda run -n calltone pip install onnxruntime-gpu  # for GPU\n"
                "  conda run -n calltone pip install onnxruntime      # for CPU"
            )
    
    def _load_huggingface_model(self):
        """Load HuggingFace wav2vec2 emotion model as fallback."""
        print("Loading HuggingFace emotion model")
        print(f"Using device: {self.device}")
        
        try:
            from transformers import Wav2Vec2ForSequenceClassification, Wav2Vec2Processor
            
            # Check for local model first (for offline operation)
            local_model_path = Path(__file__).parent / "models" / "wav2vec2-emotion"
            
            if local_model_path.exists():
                print(f"  Loading from local cache: {local_model_path}")
                model_name_or_path = str(local_model_path)
            else:
                # Download from HuggingFace (requires internet)
                model_name_or_path = "ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition"
                print(f"  Downloading from HuggingFace: {model_name_or_path}")
                print("  (This will be cached for future offline use)")
            
            self.processor = Wav2Vec2Processor.from_pretrained(model_name_or_path, local_files_only=local_model_path.exists())
            self.model = Wav2Vec2ForSequenceClassification.from_pretrained(model_name_or_path, local_files_only=local_model_path.exists())
            self.model.to(self.device)
            self.model.eval()
            
            # Update emotion labels for this model
            self.emotion_labels = [
                "angry", "calm", "disgust", "fearful", "happy", "neutral", "sad", "surprised"
            ]
            
            print("✓ HuggingFace emotion model loaded successfully")
            print(f"  Emotions: {', '.join(self.emotion_labels)}")
            
        except ImportError:
            raise ImportError(
                "transformers not installed. Install with:\n"
                "  conda run -n calltone pip install transformers"
            )
    
    def _load_audio_cached(self, audio_path: str, sample_rate: int = 16000) -> np.ndarray:
        """
        Load, mono-convert, resample and cache a full audio file.
        Subsequent calls with the same path return the cached array instantly.
        """
        cache_key = (audio_path, sample_rate)
        if cache_key in self._audio_cache:
            return self._audio_cache[cache_key]

        waveform, sr = torchaudio.load(audio_path)
        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)
        if sr != sample_rate:
            waveform = torchaudio.transforms.Resample(sr, sample_rate)(waveform)

        audio_np = waveform.squeeze().numpy().astype(np.float32)
        self._audio_cache[cache_key] = audio_np
        return audio_np

    @staticmethod
    def _pad_to_chunk(signal: np.ndarray, chunk_size: int = 10000) -> np.ndarray:
        """Pad signal so its length is a multiple of chunk_size (min chunk_size)."""
        n = len(signal)
        if n < chunk_size:
            return np.pad(signal, (0, chunk_size - n))
        remainder = n % chunk_size
        if remainder:
            return np.pad(signal, (0, chunk_size - remainder))
        return signal

    def process_audio_segment(
        self,
        audio_path: str,
        start_time: float,
        end_time: float,
        sample_rate: int = 16000
    ) -> Dict[str, any]:
        """
        Process a single audio segment and detect emotions.
        Uses the in-memory audio cache so the file is only read once per path.
        """
        audio_np = self._load_audio_cached(audio_path, sample_rate)
        start_sample = int(start_time * sample_rate)
        end_sample   = int(end_time   * sample_rate)
        segment_np = audio_np[start_sample:end_sample]

        if self.backend == "onnx":
            return self._process_onnx_array(segment_np, sample_rate)
        else:
            segment_tensor = torch.from_numpy(segment_np).unsqueeze(0)
            return self._process_huggingface(segment_tensor, sample_rate)

    def _process_onnx_array(self, signal: np.ndarray, sample_rate: int) -> Dict:
        """Run ONNX inference on a single pre-extracted numpy array."""
        signal = signal / (np.max(np.abs(signal)) + 1e-7)
        signal = self._pad_to_chunk(signal)
        batch  = signal[np.newaxis, :]          # [1, T]
        logits = self.onnx_session.run([self.output_name], {self.input_name: batch})[0]
        return self._logits_to_result(logits[0], len(signal) / sample_rate)

    def process_audio_segments_batch(
        self,
        audio_path: str,
        segments: List[Dict],
        sample_rate: int = 16000,
    ) -> List[Dict]:
        """
        GPU-optimised batch path: one ONNX call for ALL segments.

        Load the audio file once, slice every segment, pad to a uniform length,
        stack into a single [N, T] tensor and run a single forward pass.
        Falls back to the HuggingFace per-segment path when backend != 'onnx'.
        """
        if self.backend != "onnx":
            return self.process_diarization_segments(audio_path, segments)

        print(f"  Loading audio and preparing {len(segments)} segments for batch inference...")
        audio_np = self._load_audio_cached(audio_path, sample_rate)

        # Slice + normalise + pad each segment
        arrays: List[np.ndarray] = []
        durations: List[float] = []
        for seg in segments:
            start = int(seg['start'] * sample_rate)
            end   = int(seg['end']   * sample_rate)
            s = audio_np[start:end]
            s = s / (np.max(np.abs(s)) + 1e-7)
            s = self._pad_to_chunk(s)
            arrays.append(s)
            durations.append(len(s) / sample_rate)

        # Pad to uniform length across the batch
        max_len = max(len(a) for a in arrays)
        # Round up to next multiple of 10,000
        if max_len % 10000:
            max_len += 10000 - max_len % 10000

        batch = np.zeros((len(arrays), max_len), dtype=np.float32)
        for i, a in enumerate(arrays):
            batch[i, :len(a)] = a

        # Single GPU forward pass
        logits_batch = self.onnx_session.run(
            [self.output_name], {self.input_name: batch}
        )[0]   # [N, num_emotions]

        # Decode each result
        enriched: List[Dict] = []
        for i, seg in enumerate(segments):
            result = self._logits_to_result(logits_batch[i], durations[i])
            enriched_seg = seg.copy()
            enriched_seg['audio_emotion']            = result['emotion']
            enriched_seg['audio_emotion_confidence'] = result['confidence']
            enriched_seg['audio_emotion_scores']     = result['all_scores']
            enriched.append(enriched_seg)

        return enriched

    def _logits_to_result(self, logits: np.ndarray, duration: float) -> Dict:
        """Convert raw logits (1-D array) into an emotion result dict."""
        probs     = torch.softmax(torch.from_numpy(logits.astype(np.float32)), dim=-1)
        top_prob, top_idx = torch.max(probs, dim=-1)
        scores = {
            label: float(probs[j])
            for j, label in enumerate(self.emotion_labels)
            if j < probs.shape[-1]
        }
        emotion = (
            self.emotion_labels[top_idx.item()]
            if top_idx.item() < len(self.emotion_labels)
            else f"emotion_{top_idx.item()}"
        )
        return {"emotion": emotion, "confidence": float(top_prob), "all_scores": scores, "segment_duration": duration}

    def _process_onnx(self, segment: torch.Tensor, sample_rate: int) -> Dict:
        """Legacy single-segment ONNX path (kept for compatibility)."""
        return self._process_onnx_array(segment.squeeze().cpu().numpy(), sample_rate)
    
    def _process_huggingface(self, segment: torch.Tensor, sample_rate: int) -> Dict:
        """Process with HuggingFace model."""
        with torch.no_grad():
            # Prepare input
            inputs = self.processor(
                segment.squeeze().numpy(),
                sampling_rate=sample_rate,
                return_tensors="pt",
                padding=True
            )
            
            # Move to device
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            # Get predictions
            outputs = self.model(**inputs)
            logits = outputs.logits
            probs = torch.softmax(logits, dim=-1)
            
            # Get top emotion
            top_prob, top_idx = torch.max(probs, dim=-1)
            
            # Get all emotion scores
            emotion_scores = {}
            for idx, label in enumerate(self.emotion_labels):
                if idx < probs.shape[-1]:
                    emotion_scores[label] = float(probs[0, idx].cpu())
            
            # Determine top emotion
            if top_idx.item() < len(self.emotion_labels):
                top_emotion = self.emotion_labels[top_idx.item()]
            else:
                top_emotion = f"emotion_{top_idx.item()}"
            
            return {
                "emotion": top_emotion,
                "confidence": float(top_prob.cpu()),
                "all_scores": emotion_scores,
                "segment_duration": len(segment[0]) / sample_rate
            }
    
    def process_diarization_segments(
        self,
        audio_path: str,
        segments: List[Dict]
    ) -> List[Dict]:
        """
        Process all segments via the GPU batch path when ONNX is active,
        otherwise fall back to per-segment inference.
        """
        print(f"\nProcessing {len(segments)} segments for emotion detection...")

        if self.backend == "onnx":
            try:
                enriched = self.process_audio_segments_batch(audio_path, segments)
                print(f"\n✓ Emotion detection complete for {len(enriched)} segments")
                return enriched
            except Exception as e:
                print(f"\n  Batch inference failed ({e}), falling back to per-segment mode...")

        # Per-segment fallback (HuggingFace or ONNX batch failure)
        enriched_segments = []
        for i, segment in enumerate(segments, 1):
            print(f"  [{i}/{len(segments)}] {segment['speaker']} "
                  f"[{segment['start']:.1f}s → {segment['end']:.1f}s]", end="\r")
            try:
                emotion_result = self.process_audio_segment(
                    audio_path, segment['start'], segment['end']
                )
                enriched_segment = segment.copy()
                enriched_segment['audio_emotion']            = emotion_result['emotion']
                enriched_segment['audio_emotion_confidence'] = emotion_result['confidence']
                enriched_segment['audio_emotion_scores']     = emotion_result['all_scores']
                enriched_segments.append(enriched_segment)
            except Exception as e:
                print(f"\n  Warning: Failed to process segment {i}: {e}")
                enriched_segments.append(segment.copy())

        print(f"\n✓ Emotion detection complete for {len(enriched_segments)} segments")
        return enriched_segments


def detect_emotions_for_transcript(
    audio_path: str,
    segments: List[Dict],
    model_dir: str = None
) -> List[Dict]:
    """
    Convenience function to detect emotions for all segments.
    
    Args:
        audio_path: Path to audio file
        segments: List of diarization segments
        model_dir: Optional custom model directory
        
    Returns:
        Segments with emotion information added
    """
    detector = Audio2EmotionDetector(model_dir=model_dir)
    return detector.process_diarization_segments(audio_path, segments)


if __name__ == "__main__":
    # Test the emotion detector
    print("Audio2Emotion Detector Test")
    print("=" * 60)
    
    detector = Audio2EmotionDetector()
    print("\nModel loaded successfully!")
    print(f"Supported emotions: {', '.join(detector.emotion_labels)}")
